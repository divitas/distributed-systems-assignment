"""
Customer Database Server - PA3 Replicated version
Uses Rotating Sequencer Atomic Broadcast for replication over 5 nodes.

Each replica:
  - Runs a gRPC server (for frontend communication)
  - Participates in atomic broadcast (UDP) for state machine replication
  - Applies operations in globally ordered sequence to local SQLite

Usage:
  python customer_db_replicated.py --node-id 0
  python customer_db_replicated.py --node-id 1
  ...
"""

import grpc
import sqlite3
import threading
import time
import json
import sys
import os
import argparse
from concurrent import futures

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.constants import *
from shared.utils import generate_session_id, get_current_timestamp, is_session_expired

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))
import customer_pb2
import customer_pb2_grpc

from atomic_broadcast import AtomicBroadcast


class ReplicatedCustomerDBServicer(customer_pb2_grpc.CustomerDBServicer):
    """
    gRPC Servicer that replicates all WRITE operations via atomic broadcast.
    READ operations are served locally from the replica's SQLite.
    """

    def __init__(self, db_path, node_id):
        self.db_path = db_path
        self.node_id = node_id
        self.conn_lock = threading.Lock()
        self._init_database()

        # Build peer list for atomic broadcast
        peers = []
        for r in config.CUSTOMER_DB_REPLICAS:
            peers.append({
                'id': r['id'],
                'host': r['host'],
                'udp_port': r['udp_port'],
            })

        my_udp_port = config.CUSTOMER_DB_REPLICAS[node_id]['udp_port']
        self.ab = AtomicBroadcast(
            node_id=node_id,
            peers=peers,
            on_deliver_callback=self._apply_operation,
            udp_port=my_udp_port,
        )

        # Session cleanup thread
        self.cleanup_thread = threading.Thread(target=self._session_cleanup_worker, daemon=True)
        self.cleanup_thread.start()

        print(f"[Node {node_id}] Customer DB replica initialized")

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
                print(f"[Node {self.node_id}] Session cleanup error: {e}")

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

    # =========================================================================
    # Atomic broadcast: submit write op and wait for delivery
    # =========================================================================

    def _submit_and_wait(self, operation, timeout=30):
        """
        Submit a write operation to atomic broadcast, wait for delivery,
        and return the result.
        """
        done_event, req_id = self.ab.submit(operation)
        delivered = done_event.wait(timeout=timeout)
        if not delivered:
            return self._err("Operation timed out waiting for consensus")
        result = self.ab.get_result(req_id)
        return result

    # =========================================================================
    # Application callback: executed when a request is delivered in order
    # =========================================================================

    def _apply_operation(self, operation):
        """
        Apply a delivered operation to the local SQLite database.
        This is the state machine replication callback.
        Called in global sequence order by the atomic broadcast layer.
        """
        op = operation.get('op')
        data = operation.get('data', {})

        try:
            if op == 'create_seller':
                return self._do_create_seller(data)
            elif op == 'login_seller':
                return self._do_login_seller(data)
            elif op == 'logout_seller':
                return self._do_logout_seller(data)
            elif op == 'update_seller_feedback':
                return self._do_update_seller_feedback(data)
            elif op == 'update_seller_items_sold':
                return self._do_update_seller_items_sold(data)
            elif op == 'create_buyer':
                return self._do_create_buyer(data)
            elif op == 'login_buyer':
                return self._do_login_buyer(data)
            elif op == 'logout_buyer':
                return self._do_logout_buyer(data)
            elif op == 'add_purchase':
                return self._do_add_purchase(data)
            elif op == 'add_to_cart':
                return self._do_add_to_cart(data)
            elif op == 'remove_from_cart':
                return self._do_remove_from_cart(data)
            elif op == 'save_cart':
                return self._do_save_cart(data)
            elif op == 'clear_cart':
                return self._do_clear_cart(data)
            else:
                return {'status': 0, 'message': f'Unknown operation: {op}'}
        except Exception as e:
            return {'status': 0, 'message': f'Apply error: {str(e)}'}

    # =========================================================================
    # Helpers for gRPC responses
    # =========================================================================

    def _ok(self, data=None):
        return customer_pb2.DBResponse(
            status=1, message="Success", json_data=json.dumps(data or {})
        )

    def _err(self, msg):
        return customer_pb2.DBResponse(status=0, message=msg, json_data="{}")

    def _dict_ok(self, data=None):
        return {'status': 1, 'message': 'Success', 'data': data or {}}

    def _dict_err(self, msg):
        return {'status': 0, 'message': msg}

    def _result_to_grpc(self, result):
        """Convert dict result from _apply_operation to gRPC DBResponse."""
        if result is None:
            return self._err("No result")
        return customer_pb2.DBResponse(
            status=result.get('status', 0),
            message=result.get('message', ''),
            json_data=json.dumps(result.get('data', {}))
        )

    # =========================================================================
    # Write operation implementations (applied via atomic broadcast)
    # =========================================================================

    def _do_create_seller(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO sellers (username, password, seller_name) VALUES (?, ?, ?)',
                (data['username'], data['password'], data['seller_name'])
            )
            seller_id = cursor.lastrowid
            conn.commit()
            return self._dict_ok({'seller_id': seller_id})
        except sqlite3.IntegrityError:
            return self._dict_err("Username already exists")
        finally:
            conn.close()

    def _do_login_seller(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT seller_id, seller_name FROM sellers WHERE username = ? AND password = ?',
                (data['username'], data['password'])
            )
            result = cursor.fetchone()
            if result:
                seller_id, seller_name = result
                session_id = data.get('session_id', generate_session_id())
                current_time = get_current_timestamp()
                cursor.execute(
                    'INSERT INTO seller_sessions (session_id, seller_id, last_activity, created_at) VALUES (?, ?, ?, ?)',
                    (session_id, seller_id, current_time, current_time)
                )
                conn.commit()
                return self._dict_ok({
                    'session_id': session_id, 'seller_id': seller_id, 'seller_name': seller_name
                })
            else:
                return self._dict_err("Invalid username or password")
        finally:
            conn.close()

    def _do_logout_seller(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (data['session_id'],))
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_update_seller_feedback(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if data['feedback_type'] == 'thumbs_up':
                cursor.execute('UPDATE sellers SET thumbs_up = thumbs_up + 1 WHERE seller_id = ?',
                               (data['seller_id'],))
            else:
                cursor.execute('UPDATE sellers SET thumbs_down = thumbs_down + 1 WHERE seller_id = ?',
                               (data['seller_id'],))
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_update_seller_items_sold(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE sellers SET items_sold = items_sold + ? WHERE seller_id = ?',
                (data['quantity'], data['seller_id'])
            )
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_create_buyer(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO buyers (username, password, buyer_name) VALUES (?, ?, ?)',
                (data['username'], data['password'], data['buyer_name'])
            )
            buyer_id = cursor.lastrowid
            conn.commit()
            return self._dict_ok({'buyer_id': buyer_id})
        except sqlite3.IntegrityError:
            return self._dict_err("Username already exists")
        finally:
            conn.close()

    def _do_login_buyer(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT buyer_id, buyer_name FROM buyers WHERE username = ? AND password = ?',
                (data['username'], data['password'])
            )
            result = cursor.fetchone()
            if result:
                buyer_id, buyer_name = result
                session_id = data.get('session_id', generate_session_id())
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
                return self._dict_ok({
                    'session_id': session_id, 'buyer_id': buyer_id, 'buyer_name': buyer_name
                })
            else:
                return self._dict_err("Invalid username or password")
        finally:
            conn.close()

    def _do_logout_buyer(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (data['session_id'],))
            cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (data['session_id'],))
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_add_purchase(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO purchase_history (buyer_id, item_id, quantity) VALUES (?, ?, ?)',
                (data['buyer_id'], data['item_id'], data['quantity'])
            )
            cursor.execute(
                'UPDATE buyers SET items_purchased = items_purchased + ? WHERE buyer_id = ?',
                (data['quantity'], data['buyer_id'])
            )
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_add_to_cart(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT quantity FROM shopping_carts WHERE session_id = ? AND item_id = ?',
                (data['session_id'], data['item_id'])
            )
            result = cursor.fetchone()
            if result:
                cursor.execute(
                    'UPDATE shopping_carts SET quantity = ? WHERE session_id = ? AND item_id = ?',
                    (result[0] + data['quantity'], data['session_id'], data['item_id'])
                )
            else:
                cursor.execute(
                    'INSERT INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, ?)',
                    (data['session_id'], data['buyer_id'], data['item_id'], data['quantity'])
                )
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_remove_from_cart(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT quantity FROM shopping_carts WHERE session_id = ? AND item_id = ?',
                (data['session_id'], data['item_id'])
            )
            result = cursor.fetchone()
            if result:
                new_qty = result[0] - data['quantity']
                if new_qty <= 0:
                    cursor.execute(
                        'DELETE FROM shopping_carts WHERE session_id = ? AND item_id = ?',
                        (data['session_id'], data['item_id'])
                    )
                else:
                    cursor.execute(
                        'UPDATE shopping_carts SET quantity = ? WHERE session_id = ? AND item_id = ?',
                        (new_qty, data['session_id'], data['item_id'])
                    )
                conn.commit()
                return self._dict_ok()
            else:
                return self._dict_err("Item not in cart")
        finally:
            conn.close()

    def _do_save_cart(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?',
                (data['session_id'],)
            )
            cart_items = cursor.fetchall()
            cursor.execute('DELETE FROM saved_carts WHERE buyer_id = ?', (data['buyer_id'],))
            for item_id, quantity in cart_items:
                cursor.execute(
                    'INSERT INTO saved_carts (buyer_id, item_id, quantity) VALUES (?, ?, ?)',
                    (data['buyer_id'], item_id, quantity)
                )
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    def _do_clear_cart(self, data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (data['session_id'],))
            conn.commit()
            return self._dict_ok()
        finally:
            conn.close()

    # =========================================================================
    # gRPC RPC methods — WRITE ops go through atomic broadcast
    # =========================================================================

    def CreateSeller(self, request, context):
        result = self._submit_and_wait({
            'op': 'create_seller',
            'data': {
                'username': request.username,
                'password': request.password,
                'seller_name': request.seller_name,
            }
        })
        return self._result_to_grpc(result)

    def LoginSeller(self, request, context):
        session_id = generate_session_id()
        result = self._submit_and_wait({
            'op': 'login_seller',
            'data': {
                'username': request.username,
                'password': request.password,
                'session_id': session_id,
            }
        })
        return self._result_to_grpc(result)

    def LogoutSeller(self, request, context):
        result = self._submit_and_wait({
            'op': 'logout_seller',
            'data': {'session_id': request.session_id}
        })
        return self._result_to_grpc(result)

    def ValidateSessionSeller(self, request, context):
        # READ-only, serve locally
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
                FROM seller_sessions ss JOIN sellers s ON ss.seller_id = s.seller_id
                WHERE ss.session_id = ?
            ''', (request.session_id,))
            result = cursor.fetchone()
            if result:
                seller_id, last_activity, seller_name = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    'UPDATE seller_sessions SET last_activity = ? WHERE session_id = ?',
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({
                    'session_id': request.session_id,
                    'seller_id': seller_id,
                    'seller_name': seller_name
                })
            else:
                return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def GetSellerRating(self, request, context):
        # READ-only
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
        result = self._submit_and_wait({
            'op': 'update_seller_feedback',
            'data': {
                'seller_id': request.seller_id,
                'feedback_type': request.feedback_type,
            }
        })
        return self._result_to_grpc(result)

    def UpdateSellerItemsSold(self, request, context):
        result = self._submit_and_wait({
            'op': 'update_seller_items_sold',
            'data': {
                'seller_id': request.seller_id,
                'quantity': request.quantity,
            }
        })
        return self._result_to_grpc(result)

    def CreateBuyer(self, request, context):
        result = self._submit_and_wait({
            'op': 'create_buyer',
            'data': {
                'username': request.username,
                'password': request.password,
                'buyer_name': request.buyer_name,
            }
        })
        return self._result_to_grpc(result)

    def LoginBuyer(self, request, context):
        session_id = generate_session_id()
        result = self._submit_and_wait({
            'op': 'login_buyer',
            'data': {
                'username': request.username,
                'password': request.password,
                'session_id': session_id,
            }
        })
        return self._result_to_grpc(result)

    def LogoutBuyer(self, request, context):
        result = self._submit_and_wait({
            'op': 'logout_buyer',
            'data': {'session_id': request.session_id}
        })
        return self._result_to_grpc(result)

    def ValidateSessionBuyer(self, request, context):
        # READ-only
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
                FROM buyer_sessions bs JOIN buyers b ON bs.buyer_id = b.buyer_id
                WHERE bs.session_id = ?
            ''', (request.session_id,))
            result = cursor.fetchone()
            if result:
                buyer_id, last_activity, buyer_name = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    'UPDATE buyer_sessions SET last_activity = ? WHERE session_id = ?',
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({
                    'session_id': request.session_id,
                    'buyer_id': buyer_id,
                    'buyer_name': buyer_name
                })
            else:
                return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def GetBuyerPurchases(self, request, context):
        # READ-only
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
        result = self._submit_and_wait({
            'op': 'add_purchase',
            'data': {
                'buyer_id': request.buyer_id,
                'item_id': request.item_id,
                'quantity': request.quantity,
            }
        })
        return self._result_to_grpc(result)

    def GetCart(self, request, context):
        # READ-only
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
            cursor.execute(
                'SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?',
                (request.session_id,)
            )
            cart = {r[0]: r[1] for r in cursor.fetchall()}
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
        result = self._submit_and_wait({
            'op': 'add_to_cart',
            'data': {
                'session_id': request.session_id,
                'buyer_id': request.buyer_id,
                'item_id': request.item_id,
                'quantity': request.quantity,
            }
        })
        return self._result_to_grpc(result)

    def RemoveFromCart(self, request, context):
        result = self._submit_and_wait({
            'op': 'remove_from_cart',
            'data': {
                'session_id': request.session_id,
                'buyer_id': request.buyer_id,
                'item_id': request.item_id,
                'quantity': request.quantity,
            }
        })
        return self._result_to_grpc(result)

    def SaveCart(self, request, context):
        result = self._submit_and_wait({
            'op': 'save_cart',
            'data': {
                'session_id': request.session_id,
                'buyer_id': request.buyer_id,
            }
        })
        return self._result_to_grpc(result)

    def ClearCart(self, request, context):
        result = self._submit_and_wait({
            'op': 'clear_cart',
            'data': {'session_id': request.session_id}
        })
        return self._result_to_grpc(result)


def serve():
    parser = argparse.ArgumentParser(description='Customer DB Replica')
    parser.add_argument('--node-id', type=int, required=True, help='Node ID (0-4)')
    args = parser.parse_args()

    node_id = args.node_id
    replica = config.CUSTOMER_DB_REPLICAS[node_id]
    grpc_port = replica['grpc_port']

    # Use a per-replica DB file
    db_path = f"data/customer_node{node_id}.db"

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS))
    servicer = ReplicatedCustomerDBServicer(db_path, node_id)
    customer_pb2_grpc.add_CustomerDBServicer_to_server(servicer, server)
    server.add_insecure_port(f'0.0.0.0:{grpc_port}')
    server.start()
    print(f"[Node {node_id}] Customer DB gRPC server on port {grpc_port}, UDP on {replica['udp_port']}")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
