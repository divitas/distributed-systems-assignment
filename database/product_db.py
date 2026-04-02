"""
Product Database Server - Raft-Replicated gRPC version (PA3)
Uses PySyncObj for Raft consensus across 5 replicas.
Each replica maintains its own SQLite DB, but all writes go through Raft.
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


class RaftProductStore(SyncObj):
    """
    Raft-replicated state machine for the Product DB.
    All write operations are decorated with @replicated so they go through
    Raft consensus before being applied to each replica's local SQLite.
    """

    def __init__(self, self_addr, partners, db_path):
        cfg = SyncObjConf(
            autoTick=True,
            compactionMinEntries=1000,
            dynamicMembershipChange=False,
        )
        super(RaftProductStore, self).__init__(self_addr, partners, cfg)
        self.db_path = db_path
        self._init_database()

    def __getstate__(self):
        """Custom pickle: only serialize the db_path (no locks, no connections)."""
        return {'db_path': self.db_path}

    def __setstate__(self, state):
        """Custom unpickle: restore db_path."""
        self.db_path = state['db_path']

    def _init_database(self):
        from database.init_db import init_product_database
        init_product_database(self.db_path)

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    # ------------------------------------------------------------------
    # REPLICATED WRITES — these go through Raft consensus
    # ------------------------------------------------------------------

    @replicated
    def raft_register_item(self, item_id, seller_id, name, category, keywords_json, condition, price, quantity):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO items (item_id, seller_id, name, category, keywords, condition, price, quantity, thumbs_up, thumbs_down)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (item_id, seller_id, name, category, keywords_json, condition, price, quantity))
            conn.commit()
            return True
        except Exception as e:
            print(f"[RAFT] register_item error: {e}")
            return False
        finally:
            conn.close()

    @replicated
    def raft_update_price(self, item_id, new_price):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE items SET price = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?',
                (new_price, item_id)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[RAFT] update_price error: {e}")
            return False
        finally:
            conn.close()

    @replicated
    def raft_update_quantity(self, item_id, new_quantity):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?',
                (new_quantity, item_id)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[RAFT] update_quantity error: {e}")
            return False
        finally:
            conn.close()

    @replicated
    def raft_make_purchase(self, item_id, quantity):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE items SET quantity = quantity - ? WHERE item_id = ?',
                (quantity, item_id)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"[RAFT] make_purchase error: {e}")
            return False
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
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[RAFT] provide_feedback error: {e}")
            return False
        finally:
            conn.close()

    @replicated
    def raft_increment_category_counter(self, category):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE category_counters SET last_id = last_id + 1 WHERE category = ?',
                (category,)
            )
            cursor.execute(
                'SELECT last_id FROM category_counters WHERE category = ?',
                (category,)
            )
            row = cursor.fetchone()
            conn.commit()
            return row[0] if row else None
        except Exception as e:
            print(f"[RAFT] increment_category_counter error: {e}")
            return None
        finally:
            conn.close()


class ProductDBServicer(product_pb2_grpc.ProductDBServicer):

    def __init__(self, raft_store):
        self.raft = raft_store

    def _ok(self, data=None):
        return product_pb2.DBResponse(
            status=1,
            message="Success",
            json_data=json.dumps(data or {})
        )

    def _err(self, msg):
        return product_pb2.DBResponse(status=0, message=msg, json_data="{}")

    def _check_leader(self, context):
        """If this node is not the Raft leader, reject with UNAVAILABLE so the client retries another replica."""
        if not self.raft._isLeader():
            leader = self.raft._getLeader()
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details(f"Not the leader. Leader is {leader}")
            return False
        return True

    def _get_connection(self):
        return sqlite3.connect(self.raft.db_path, check_same_thread=False)

    # ------------------------------------------------------------------
    # WRITE endpoints — require leader, go through Raft
    # ------------------------------------------------------------------

    def RegisterItem(self, request, context):
        if not self._check_leader(context):
            return self._err("Not leader")

        # Increment counter through Raft first
        sequence = self.raft.raft_increment_category_counter(request.category, sync=True, timeout=10)
        if sequence is None:
            return self._err("Failed to generate item ID")

        item_id = generate_item_id(request.category, sequence)
        keywords_json = json.dumps(list(request.keywords))

        result = self.raft.raft_register_item(
            item_id, request.seller_id, request.name, request.category,
            keywords_json, request.condition, request.price, request.quantity,
            sync=True, timeout=10
        )
        if result:
            return self._ok({'item_id': item_id})
        else:
            return self._err("Failed to register item")

    def UpdateItemPrice(self, request, context):
        if not self._check_leader(context):
            return self._err("Not leader")

        # Validate ownership locally (read is fine on any replica)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT seller_id FROM items WHERE item_id = ?', (request.item_id,))
            result = cursor.fetchone()
            if not result:
                return self._err("Item not found")
            if str(result[0]) != str(request.seller_id):
                return self._err("You don't own this item")
        finally:
            conn.close()

        ok = self.raft.raft_update_price(request.item_id, request.new_price, sync=True, timeout=10)
        return self._ok() if ok else self._err("Failed to update price")

    def UpdateItemQuantity(self, request, context):
        if not self._check_leader(context):
            return self._err("Not leader")

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
        finally:
            conn.close()

        ok = self.raft.raft_update_quantity(request.item_id, new_quantity, sync=True, timeout=10)
        if ok:
            return self._ok({'remaining': new_quantity})
        return self._err("Failed to update quantity")

    def MakePurchase(self, request, context):
        if not self._check_leader(context):
            return self._err("Not leader")

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
        finally:
            conn.close()

        ok = self.raft.raft_make_purchase(request.item_id, request.quantity, sync=True, timeout=10)
        if ok:
            return self._ok({'seller_id': str(seller_id)})
        return self._err("Purchase failed")

    def ProvideItemFeedback(self, request, context):
        if not self._check_leader(context):
            return self._err("Not leader")

        ok = self.raft.raft_provide_feedback(request.item_id, request.thumbs, sync=True, timeout=10)
        if ok:
            return self._ok()
        return self._err("Item not found")

    # ------------------------------------------------------------------
    # READ endpoints — can serve from any replica (local SQLite)
    # ------------------------------------------------------------------

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True, help="Replica ID (0-4)")
    args = parser.parse_args()

    replica_id = args.id
    replicas = config.PRODUCT_DB_REPLICAS
    my_replica = replicas[replica_id]

    # Build pysyncobj addresses: "host:raft_port"
    self_addr = f"{my_replica['host']}:{my_replica['raft_port']}"
    partner_addrs = [
        f"{r['host']}:{r['raft_port']}"
        for r in replicas if r['id'] != replica_id
    ]

    db_path = my_replica['db_file']
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    print(f"[Product DB Replica {replica_id}] Raft self={self_addr}, partners={partner_addrs}")
    print(f"[Product DB Replica {replica_id}] DB: {db_path}")
    print(f"[Product DB Replica {replica_id}] gRPC port: {my_replica['grpc_port']}")

    raft_store = RaftProductStore(self_addr, partner_addrs, db_path)

    # Wait briefly for Raft to elect a leader
    time.sleep(2)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS))
    product_pb2_grpc.add_ProductDBServicer_to_server(
        ProductDBServicer(raft_store), server
    )
    server.add_insecure_port(f'0.0.0.0:{my_replica["grpc_port"]}')
    server.start()
    print(f"[Product DB Replica {replica_id}] gRPC server started on port {my_replica['grpc_port']}")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()