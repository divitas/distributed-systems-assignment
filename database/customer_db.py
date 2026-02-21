"""
Customer Database Server - gRPC version
"""

import grpc
import sqlite3
import threading
import time
import json
import sys
import os
from concurrent import futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.constants import *
from shared.utils import generate_session_id, get_current_timestamp, is_session_expired

# Import generated proto files
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))
import customer_pb2
import customer_pb2_grpc


class CustomerDBServicer(customer_pb2_grpc.CustomerDBServicer):
    """gRPC Servicer wrapping all existing SQLite logic"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn_lock = threading.Lock()
        self._init_database()

        # Start session cleanup thread
        self.cleanup_thread = threading.Thread(target=self._session_cleanup_worker, daemon=True)
        self.cleanup_thread.start()

    def _init_database(self):
        from database.init_db import init_customer_database
        init_customer_database(self.db_path)

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _session_cleanup_worker(self):
        while True:
            time.sleep(config.SESSION_CHECK_INTERVAL)
            try:
                self._cleanup_expired_sessions()
            except Exception as e:
                print(f"Error in session cleanup: {e}")

    def _cleanup_expired_sessions(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        current_time = get_current_timestamp()
        cutoff_time = current_time - config.SESSION_TIMEOUT
        try:
            cursor.execute('DELETE FROM seller_sessions WHERE last_activity < ?', (cutoff_time,))
            cursor.execute('DELETE FROM buyer_sessions WHERE last_activity < ?', (cutoff_time,))
            cursor.execute('''
                DELETE FROM shopping_carts 
                WHERE session_id NOT IN (SELECT session_id FROM buyer_sessions)
            ''')
            conn.commit()
        finally:
            conn.close()

    # ========== Helpers ==========

    def _ok(self, data=None):
        return customer_pb2.DBResponse(
            status=1,
            message="Success",
            json_data=json.dumps(data or {})
        )

    def _err(self, msg, status=0):
        return customer_pb2.DBResponse(status=status, message=msg, json_data="{}")

    # ========== Seller RPCs ==========

    def CreateSeller(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO sellers (username, password, seller_name) VALUES (?, ?, ?)',
                (request.username, request.password, request.seller_name)
            )
            seller_id = cursor.lastrowid
            conn.commit()
            return self._ok({'seller_id': seller_id})
        except sqlite3.IntegrityError:
            return self._err("Username already exists")
        finally:
            conn.close()

    def LoginSeller(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT seller_id, seller_name FROM sellers WHERE username = ? AND password = ?',
                (request.username, request.password)
            )
            result = cursor.fetchone()
            if result:
                seller_id, seller_name = result
                session_id = generate_session_id()
                current_time = get_current_timestamp()
                cursor.execute(
                    'INSERT INTO seller_sessions (session_id, seller_id, last_activity, created_at) VALUES (?, ?, ?, ?)',
                    (session_id, seller_id, current_time, current_time)
                )
                conn.commit()
                return self._ok({'session_id': session_id, 'seller_id': seller_id, 'seller_name': seller_name})
            else:
                return self._err("Invalid username or password")
        finally:
            conn.close()

    def LogoutSeller(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (request.session_id,))
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    def ValidateSessionSeller(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT seller_id, last_activity FROM seller_sessions WHERE session_id = ?',
                (request.session_id,)
            )
            result = cursor.fetchone()
            if result:
                seller_id, last_activity = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (request.session_id,))
                    conn.commit()
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    'UPDATE seller_sessions SET last_activity = ? WHERE session_id = ?',
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({'seller_id': seller_id})
            else:
                return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def RestoreSessionSeller(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT ss.seller_id, ss.last_activity, s.seller_name
                FROM seller_sessions ss
                JOIN sellers s ON ss.seller_id = s.seller_id
                WHERE ss.session_id = ?
            ''', (request.session_id,))
            result = cursor.fetchone()
            if result:
                seller_id, last_activity, seller_name = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (request.session_id,))
                    conn.commit()
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    'UPDATE seller_sessions SET last_activity = ? WHERE session_id = ?',
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({'session_id': request.session_id, 'seller_id': seller_id, 'seller_name': seller_name})
            else:
                return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def GetSellerRating(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT thumbs_up, thumbs_down FROM sellers WHERE seller_id = ?',
                (request.seller_id,)
            )
            result = cursor.fetchone()
            if result:
                return self._ok({'thumbs_up': result[0], 'thumbs_down': result[1]})
            else:
                return self._err("Seller not found")
        finally:
            conn.close()

    def UpdateSellerFeedback(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if request.feedback_type == FEEDBACK_THUMBS_UP:
                cursor.execute('UPDATE sellers SET thumbs_up = thumbs_up + 1 WHERE seller_id = ?', (request.seller_id,))
            else:
                cursor.execute('UPDATE sellers SET thumbs_down = thumbs_down + 1 WHERE seller_id = ?', (request.seller_id,))
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    def UpdateSellerItemsSold(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE sellers SET items_sold = items_sold + ? WHERE seller_id = ?',
                (request.quantity, request.seller_id)
            )
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    # ========== Buyer RPCs ==========

    def CreateBuyer(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO buyers (username, password, buyer_name) VALUES (?, ?, ?)',
                (request.username, request.password, request.buyer_name)
            )
            buyer_id = cursor.lastrowid
            conn.commit()
            return self._ok({'buyer_id': buyer_id})
        except sqlite3.IntegrityError:
            return self._err("Username already exists")
        finally:
            conn.close()

    def LoginBuyer(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT buyer_id, buyer_name FROM buyers WHERE username = ? AND password = ?',
                (request.username, request.password)
            )
            result = cursor.fetchone()
            if result:
                buyer_id, buyer_name = result
                session_id = generate_session_id()
                current_time = get_current_timestamp()
                cursor.execute(
                    'INSERT INTO buyer_sessions (session_id, buyer_id, last_activity, created_at) VALUES (?, ?, ?, ?)',
                    (session_id, buyer_id, current_time, current_time)
                )
                # Load saved cart
                cursor.execute('SELECT item_id, quantity FROM saved_carts WHERE buyer_id = ?', (buyer_id,))
                for item_id, quantity in cursor.fetchall():
                    cursor.execute(
                        'INSERT OR REPLACE INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, ?)',
                        (session_id, buyer_id, item_id, quantity)
                    )
                conn.commit()
                return self._ok({'session_id': session_id, 'buyer_id': buyer_id, 'buyer_name': buyer_name})
            else:
                return self._err("Invalid username or password")
        finally:
            conn.close()

    def LogoutBuyer(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (request.session_id,))
            cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (request.session_id,))
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    def ValidateSessionBuyer(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT buyer_id, last_activity FROM buyer_sessions WHERE session_id = ?',
                (request.session_id,)
            )
            result = cursor.fetchone()
            if result:
                buyer_id, last_activity = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (request.session_id,))
                    cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (request.session_id,))
                    conn.commit()
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    'UPDATE buyer_sessions SET last_activity = ? WHERE session_id = ?',
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({'buyer_id': buyer_id})
            else:
                return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def RestoreSessionBuyer(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT bs.buyer_id, bs.last_activity, b.buyer_name
                FROM buyer_sessions bs
                JOIN buyers b ON bs.buyer_id = b.buyer_id
                WHERE bs.session_id = ?
            ''', (request.session_id,))
            result = cursor.fetchone()
            if result:
                buyer_id, last_activity, buyer_name = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (request.session_id,))
                    cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (request.session_id,))
                    conn.commit()
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    'UPDATE buyer_sessions SET last_activity = ? WHERE session_id = ?',
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({'session_id': request.session_id, 'buyer_id': buyer_id, 'buyer_name': buyer_name})
            else:
                return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def GetBuyerPurchases(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT item_id, quantity, purchase_date FROM purchase_history WHERE buyer_id = ? ORDER BY purchase_date DESC',
                (request.buyer_id,)
            )
            purchases = [{'item_id': r[0], 'quantity': r[1], 'purchase_date': r[2]} for r in cursor.fetchall()]
            return self._ok({'purchases': purchases})
        finally:
            conn.close()

    def AddPurchase(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO purchase_history (buyer_id, item_id, quantity) VALUES (?, ?, ?)',
                (request.buyer_id, request.item_id, request.quantity)
            )
            cursor.execute(
                'UPDATE buyers SET items_purchased = items_purchased + ? WHERE buyer_id = ?',
                (request.quantity, request.buyer_id)
            )
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    # ========== Cart RPCs ==========

    """def GetCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?',
                (request.session_id,)
            )
            cart = [{'item_id': r[0], 'quantity': r[1]} for r in cursor.fetchall()]
            return self._ok({'cart': cart})
        finally:
            conn.close()

    def GetCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Get buyer_id from session
            cursor.execute(
                'SELECT buyer_id FROM buyer_sessions WHERE session_id = ?',
                (request.session_id,)
            )
            buyer = cursor.fetchone()
            if not buyer:
                return self._err("Invalid session")

            buyer_id = buyer[0]

            # Get session cart
            cursor.execute(
                'SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?',
                (request.session_id,)
            )
            cart = {r[0]: r[1] for r in cursor.fetchall()}

            # Merge saved cart (sum quantities)
            cursor.execute(
                'SELECT item_id, quantity FROM saved_carts WHERE buyer_id = ?',
                (buyer_id,)
            )
            for item_id, quantity in cursor.fetchall():
                cart[item_id] = cart.get(item_id, 0) + quantity

            result = [{'item_id': k, 'quantity': v} for k, v in cart.items()]
            return self._ok({'cart': result})
        finally:
            conn.close()"""

    #session cart items take priority, and saved cart only fills in items the current session hasn't touched.
    def GetCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT buyer_id FROM buyer_sessions WHERE session_id = ?',
                (request.session_id,)
            )
            buyer = cursor.fetchone()
            if not buyer:
                return self._err("Invalid session")

            buyer_id = buyer[0]

            # Get session cart
            cursor.execute(
                'SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?',
                (request.session_id,)
            )
            cart = {r[0]: r[1] for r in cursor.fetchall()}

            # Add saved cart items that aren't in session cart
            cursor.execute(
                'SELECT item_id, quantity FROM saved_carts WHERE buyer_id = ?',
                (buyer_id,)
            )
            for item_id, quantity in cursor.fetchall():
                if item_id not in cart:
                    cart[item_id] = quantity

            result = [{'item_id': k, 'quantity': v} for k, v in cart.items()]
            return self._ok({'cart': result})
        finally:
            conn.close()

    def AddToCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT quantity FROM shopping_carts WHERE session_id = ? AND item_id = ?',
                (request.session_id, request.item_id)
            )
            result = cursor.fetchone()
            if result:
                cursor.execute(
                    'UPDATE shopping_carts SET quantity = ? WHERE session_id = ? AND item_id = ?',
                    (result[0] + request.quantity, request.session_id, request.item_id)
                )
            else:
                cursor.execute(
                    'INSERT INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, ?)',
                    (request.session_id, request.buyer_id, request.item_id, request.quantity)
                )
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    def RemoveFromCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT quantity FROM shopping_carts WHERE session_id = ? AND item_id = ?',
                (request.session_id, request.item_id)
            )
            result = cursor.fetchone()
            if result:
                new_qty = result[0] - request.quantity
                if new_qty <= 0:
                    cursor.execute(
                        'DELETE FROM shopping_carts WHERE session_id = ? AND item_id = ?',
                        (request.session_id, request.item_id)
                    )
                else:
                    cursor.execute(
                        'UPDATE shopping_carts SET quantity = ? WHERE session_id = ? AND item_id = ?',
                        (new_qty, request.session_id, request.item_id)
                    )
                conn.commit()
                return self._ok()
            else:
                return self._err("Item not in cart")
        finally:
            conn.close()

    def SaveCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?',
                (request.session_id,)
            )
            cart_items = cursor.fetchall()
            cursor.execute('DELETE FROM saved_carts WHERE buyer_id = ?', (request.buyer_id,))
            for item_id, quantity in cart_items:
                cursor.execute(
                    'INSERT INTO saved_carts (buyer_id, item_id, quantity) VALUES (?, ?, ?)',
                    (request.buyer_id, item_id, quantity)
                )
            conn.commit()
            return self._ok()
        finally:
            conn.close()

    def ClearCart(self, request, context):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (request.session_id,))
            conn.commit()
            return self._ok()
        finally:
            conn.close()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS))
    customer_pb2_grpc.add_CustomerDBServicer_to_server(
        CustomerDBServicer(config.CUSTOMER_DB_FILE), server
    )
    server.add_insecure_port(f'0.0.0.0:{config.CUSTOMER_DB_PORT}')
    server.start()
    print(f"Customer Database gRPC server started on port {config.CUSTOMER_DB_PORT}")
    print(f"Database: {config.CUSTOMER_DB_FILE}")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()