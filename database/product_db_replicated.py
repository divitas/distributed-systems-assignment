"""
Product Database Server - PA3 Replicated version using Raft (PySyncObj)

Each replica:
  - Runs a gRPC server (for frontend communication)
  - Participates in Raft consensus via PySyncObj for state machine replication
  - WRITE ops go through Raft; READ ops served locally

Usage:
  python product_db_replicated.py --node-id 0
  python product_db_replicated.py --node-id 1
  ...

Requires: pip install pysyncobj
"""

import grpc
import sqlite3
import threading
import json
import sys
import os
import argparse
import time
from concurrent import futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.constants import *
from shared.utils import generate_item_id, calculate_search_score

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))
import product_pb2
import product_pb2_grpc

from pysyncobj import SyncObj, SyncObjConf, replicated


class ProductRaftState(SyncObj):
    """
    Raft-replicated state machine for the product database.
    All write operations are replicated methods.
    """

    def __init__(self, self_addr, partners, db_path):
        cfg = SyncObjConf(
            autoTick=True,
            appendEntriesUseBatch=True,
            dynamicMembershipChange=False,
            connectionTimeout=5.0,
            raftMinTimeout=1.5,
            raftMaxTimeout=3.0,
        )
        super(ProductRaftState, self).__init__(self_addr, partners, cfg)
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        from database.init_db import init_product_database
        init_product_database(self.db_path)

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    @replicated
    def raft_register_item(self, seller_id, name, category, keywords_json, condition, price, quantity):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE category_counters SET last_id = last_id + 1 WHERE category = ?',
                (category,)
            )
            cursor.execute(
                'SELECT last_id FROM category_counters WHERE category = ?', (category,)
            )
            sequence = cursor.fetchone()[0]
            item_id = generate_item_id(category, sequence)
            cursor.execute('''
                INSERT INTO items (item_id, seller_id, name, category, keywords, condition, price, quantity, thumbs_up, thumbs_down)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (item_id, seller_id, name, category, keywords_json, condition, price, quantity))
            conn.commit()
            return {'status': 1, 'item_id': item_id}
        except Exception as e:
            return {'status': 0, 'message': str(e)}
        finally:
            conn.close()

    @replicated
    def raft_update_price(self, item_id, seller_id, new_price):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT seller_id FROM items WHERE item_id = ?', (item_id,))
            result = cursor.fetchone()
            if not result:
                return {'status': 0, 'message': 'Item not found'}
            if str(result[0]) != str(seller_id):
                return {'status': 0, 'message': "You don't own this item"}
            cursor.execute(
                'UPDATE items SET price = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?',
                (new_price, item_id)
            )
            conn.commit()
            return {'status': 1}
        finally:
            conn.close()

    @replicated
    def raft_update_quantity(self, item_id, seller_id, quantity_to_remove):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT seller_id, quantity FROM items WHERE item_id = ?', (item_id,))
            result = cursor.fetchone()
            if not result:
                return {'status': 0, 'message': 'Item not found'}
            if str(result[0]) != str(seller_id):
                return {'status': 0, 'message': "You don't own this item"}
            new_quantity = result[1] - quantity_to_remove
            if new_quantity < 0:
                return {'status': 0, 'message': f'Cannot remove {quantity_to_remove} units. Only {result[1]} available.'}
            cursor.execute(
                'UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?',
                (new_quantity, item_id)
            )
            conn.commit()
            return {'status': 1, 'remaining': new_quantity}
        finally:
            conn.close()

    @replicated
    def raft_make_purchase(self, item_id, buyer_id, quantity):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT quantity, seller_id FROM items WHERE item_id = ?', (item_id,))
            result = cursor.fetchone()
            if not result:
                return {'status': 0, 'message': 'Item not found'}
            available_quantity, seller_id = result
            if available_quantity < quantity:
                return {'status': 0, 'message': f'Only {available_quantity} units available'}
            cursor.execute(
                'UPDATE items SET quantity = quantity - ? WHERE item_id = ?',
                (quantity, item_id)
            )
            conn.commit()
            return {'status': 1, 'seller_id': str(seller_id)}
        finally:
            conn.close()

    @replicated
    def raft_provide_feedback(self, item_id, thumbs):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if thumbs == 1:
                cursor.execute('UPDATE items SET thumbs_up = thumbs_up + 1 WHERE item_id = ?', (item_id,))
            else:
                cursor.execute('UPDATE items SET thumbs_down = thumbs_down + 1 WHERE item_id = ?', (item_id,))
            if cursor.rowcount == 0:
                return {'status': 0, 'message': 'Item not found'}
            conn.commit()
            return {'status': 1}
        finally:
            conn.close()


class ReplicatedProductDBServicer(product_pb2_grpc.ProductDBServicer):
    """gRPC servicer that routes writes through Raft and reads locally."""

    def __init__(self, raft_state, db_path):
        self.raft = raft_state
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _ok(self, data=None):
        return product_pb2.DBResponse(
            status=1, message="Success", json_data=json.dumps(data or {})
        )

    def _err(self, msg):
        return product_pb2.DBResponse(status=0, message=msg, json_data="{}")

    def _wait_leader(self, timeout=10):
        """Wait until this node knows who the leader is."""
        start = time.time()
        while time.time() - start < timeout:
            leader = self.raft.getLeader()
            if leader is not None:
                return True
            time.sleep(0.2)
        return False

    # ========== WRITE operations (through Raft) ==========

    def RegisterItem(self, request, context):
        if not self._wait_leader():
            return self._err("No Raft leader available")
        keywords_json = json.dumps(list(request.keywords))
        result = self.raft.raft_register_item(
            request.seller_id, request.name, request.category,
            keywords_json, request.condition, request.price, request.quantity
        )
        if result and result.get('status') == 1:
            return self._ok({'item_id': result['item_id']})
        return self._err(result.get('message', 'Registration failed') if result else 'Raft error')

    def UpdateItemPrice(self, request, context):
        if not self._wait_leader():
            return self._err("No Raft leader available")
        result = self.raft.raft_update_price(
            request.item_id, request.seller_id, request.new_price
        )
        if result and result.get('status') == 1:
            return self._ok()
        return self._err(result.get('message', 'Update failed') if result else 'Raft error')

    def UpdateItemQuantity(self, request, context):
        if not self._wait_leader():
            return self._err("No Raft leader available")
        result = self.raft.raft_update_quantity(
            request.item_id, request.seller_id, request.quantity_to_remove
        )
        if result and result.get('status') == 1:
            return self._ok({'remaining': result.get('remaining', 0)})
        return self._err(result.get('message', 'Update failed') if result else 'Raft error')

    def MakePurchase(self, request, context):
        if not self._wait_leader():
            return self._err("No Raft leader available")
        result = self.raft.raft_make_purchase(
            request.item_id, request.buyer_id, request.quantity
        )
        if result and result.get('status') == 1:
            return self._ok({'seller_id': result.get('seller_id', '')})
        return self._err(result.get('message', 'Purchase failed') if result else 'Raft error')

    def ProvideItemFeedback(self, request, context):
        if not self._wait_leader():
            return self._err("No Raft leader available")
        result = self.raft.raft_provide_feedback(request.item_id, request.thumbs)
        if result and result.get('status') == 1:
            return self._ok()
        return self._err(result.get('message', 'Feedback failed') if result else 'Raft error')

    # ========== READ operations (local) ==========

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


def serve():
    parser = argparse.ArgumentParser(description='Product DB Replica (Raft)')
    parser.add_argument('--node-id', type=int, required=True, help='Node ID (0-4)')
    args = parser.parse_args()

    node_id = args.node_id
    replica = config.PRODUCT_DB_REPLICAS[node_id]
    grpc_port = replica['grpc_port']
    raft_port = replica['raft_port']

    # Build Raft addresses
    self_addr = f"{replica['host']}:{raft_port}"
    partners = []
    for i, r in enumerate(config.PRODUCT_DB_REPLICAS):
        if i != node_id:
            partners.append(f"{r['host']}:{r['raft_port']}")

    # Per-replica DB file
    db_path = f"data/product_node{node_id}.db"

    print(f"[Node {node_id}] Starting Raft at {self_addr}, partners: {partners}")
    raft_state = ProductRaftState(self_addr, partners, db_path)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS))
    servicer = ReplicatedProductDBServicer(raft_state, db_path)
    product_pb2_grpc.add_ProductDBServicer_to_server(servicer, server)
    server.add_insecure_port(f'0.0.0.0:{grpc_port}')
    server.start()
    print(f"[Node {node_id}] Product DB gRPC on port {grpc_port}, Raft on {raft_port}")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
