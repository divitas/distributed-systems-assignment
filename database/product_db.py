"""
Product Database Server - gRPC version
"""

import grpc
import sqlite3
import threading
import json
import sys
import os
from concurrent import futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.constants import *
from shared.utils import generate_item_id, calculate_search_score

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))
import product_pb2
import product_pb2_grpc


class ProductDBServicer(product_pb2_grpc.ProductDBServicer):

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn_lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        from database.init_db import init_product_database
        init_product_database(self.db_path)

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _ok(self, data=None):
        return product_pb2.DBResponse(
            status=1,
            message="Success",
            json_data=json.dumps(data or {})
        )

    def _err(self, msg):
        return product_pb2.DBResponse(status=0, message=msg, json_data="{}")

    def RegisterItem(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE category_counters SET last_id = last_id + 1 WHERE category = ?',
                (request.category,)
            )
            cursor.execute(
                'SELECT last_id FROM category_counters WHERE category = ?',
                (request.category,)
            )
            sequence = cursor.fetchone()[0]
            item_id = generate_item_id(request.category, sequence)
            keywords_json = json.dumps(list(request.keywords))

            cursor.execute('''
                INSERT INTO items (item_id, seller_id, name, category, keywords, condition, price, quantity, thumbs_up, thumbs_down)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (item_id, request.seller_id, request.name, request.category,
                  keywords_json, request.condition, request.price, request.quantity))
            conn.commit()
            return self._ok({'item_id': item_id})
        finally:
            conn.close()

    def GetItem(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT item_id, seller_id, name, category, keywords, condition, price, quantity, thumbs_up, thumbs_down
                FROM items WHERE item_id = ?
            ''', (request.item_id,))
            result = cursor.fetchone()
            if result:
                item = {
                    'item_id': result[0], 'seller_id': result[1], 'name': result[2],
                    'category': result[3], 'keywords': json.loads(result[4]) if result[4] else [],
                    'condition': result[5], 'price': result[6], 'quantity': result[7],
                    'thumbs_up': result[8], 'thumbs_down': result[9]
                }
                return self._ok({'item': item})
            else:
                return self._err("Item not found")
        finally:
            conn.close()

    def UpdateItemPrice(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT seller_id FROM items WHERE item_id = ?', (request.item_id,))
            result = cursor.fetchone()
            if not result:
                return self._err("Item not found")
            if str(result[0]) != str(request.seller_id):
                return self._err("You don't own this item")
            cursor.execute(
                'UPDATE items SET price = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?',
                (request.new_price, request.item_id)
            )
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    def UpdateItemQuantity(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT seller_id, quantity FROM items WHERE item_id = ?', (request.item_id,))
            result = cursor.fetchone()
            if not result:
                return self._err("Item not found")
            if str(result[0]) != str(request.seller_id):
                return self._err("You don't own this item")
            new_quantity = result[1] - request.quantity_to_remove
            if new_quantity < 0:
                return self._err(f"Cannot remove {request.quantity_to_remove} units. Only {result[1]} available.")
            cursor.execute(
                'UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?',
                (new_quantity, request.item_id)
            )
            conn.commit()
            return self._ok({'remaining': new_quantity})
        finally:
            conn.close()

    def GetSellerItems(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT item_id, seller_id, name, category, keywords, condition, price, quantity, thumbs_up, thumbs_down
                FROM items WHERE seller_id = ? ORDER BY created_at DESC
            ''', (request.seller_id,))
            items = []
            for row in cursor.fetchall():
                items.append({
                    'item_id': row[0], 'seller_id': row[1], 'name': row[2],
                    'category': row[3], 'keywords': json.loads(row[4]) if row[4] else [],
                    'condition': row[5], 'price': row[6], 'quantity': row[7],
                    'thumbs_up': row[8], 'thumbs_down': row[9]
                })
            return self._ok({'items': items})
        finally:
            conn.close()

    def SearchItems(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT item_id, seller_id, name, category, keywords, condition, price, quantity, thumbs_up, thumbs_down
                FROM items WHERE category = ? AND quantity > 0
            ''', (request.category,))
            keywords = list(request.keywords)
            scored_items = []
            for row in cursor.fetchall():
                item = {
                    'item_id': row[0], 'seller_id': row[1], 'name': row[2],
                    'category': row[3], 'keywords': json.loads(row[4]) if row[4] else [],
                    'condition': row[5], 'price': row[6], 'quantity': row[7],
                    'thumbs_up': row[8], 'thumbs_down': row[9]
                }
                score = calculate_search_score(item, request.category, keywords)
                if not keywords or score > 0:
                    scored_items.append((score, item))
            scored_items.sort(key=lambda x: x[0], reverse=True)
            items = [item for _, item in scored_items[:config.MAX_SEARCH_RESULTS]]
            return self._ok({'items': items})
        finally:
            conn.close()

    def MakePurchase(self, request, context):
        """Decrease item quantity for purchase"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT quantity, seller_id FROM items WHERE item_id = ?', (request.item_id,))
            result = cursor.fetchone()
            if not result:
                return self._err("Item not found")
            available_quantity, seller_id = result
            if available_quantity < request.quantity:
                return self._err(f"Only {available_quantity} units available")
            cursor.execute(
                'UPDATE items SET quantity = quantity - ? WHERE item_id = ?',
                (request.quantity, request.item_id)
            )
            conn.commit()
            return self._ok({'seller_id': str(seller_id)})
        finally:
            conn.close()

    def ProvideItemFeedback(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if request.thumbs == 1:
                cursor.execute('UPDATE items SET thumbs_up = thumbs_up + 1 WHERE item_id = ?', (request.item_id,))
            else:
                cursor.execute('UPDATE items SET thumbs_down = thumbs_down + 1 WHERE item_id = ?', (request.item_id,))
            if cursor.rowcount == 0:
                return self._err("Item not found")
            conn.commit()
            return self._ok()
        finally:
            conn.close()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS))
    product_pb2_grpc.add_ProductDBServicer_to_server(
        ProductDBServicer(config.PRODUCT_DB_FILE), server
    )
    server.add_insecure_port(f'0.0.0.0:{config.PRODUCT_DB_PORT}')
    server.start()
    print(f"Product Database gRPC server started on port {config.PRODUCT_DB_PORT}")
    print(f"Database: {config.PRODUCT_DB_FILE}")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()