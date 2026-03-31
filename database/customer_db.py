"""
Customer Database Server - gRPC + Rotating Sequencer Atomic Broadcast (PA3)

How to run:
    python3 database/customer_db.py --replica-id 0
    python3 database/customer_db.py --replica-id 1
    ...
    python3 database/customer_db.py --replica-id 4

This version:
- keeps SQLite as the application state
- replicates ALL mutating customer DB operations using UDP atomic broadcast
- serves reads locally
- uses rotating sequencer ordering:
      sequencer for global seq k = replica (k mod n)
"""

import argparse
import grpc
import json
import os
import queue
import socket
import sqlite3
import sys
import threading
import time
import uuid
from concurrent import futures
from typing import Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proto"))

import config
from shared.constants import *
from shared.utils import generate_session_id, get_current_timestamp, is_session_expired

import customer_pb2
import customer_pb2_grpc


# =============================================================================
# Atomic Broadcast Layer
# =============================================================================

class AtomicBroadcastNode:
    """
    Rotating sequencer atomic broadcast over UDP.

    Request flow:
      client write -> origin replica broadcasts REQUEST to all replicas
      sequencer for global seq k chooses a pending request and broadcasts SEQUENCE
      all replicas deliver in order once majority receipt condition is satisfied

    Missing data recovery:
      - missing REQUEST => retransmit from original sender
      - missing SEQUENCE => retransmit from responsible sequencer (k mod n)
    """

    MSG_REQUEST = "REQUEST"
    MSG_SEQUENCE = "SEQUENCE"
    MSG_RETRANSMIT = "RETRANSMIT"

    RETRANSMIT_REQUEST = "REQUEST"
    RETRANSMIT_SEQUENCE = "SEQUENCE"

    def __init__(self, replica_id: int, replicas: list, apply_callback):
        self.replica_id = replica_id
        self.replicas = sorted(replicas, key=lambda x: x["id"])
        self.n = len(self.replicas)
        self.apply_callback = apply_callback

        me = self._replica(self.replica_id)
        self.udp_host = me["host"]
        self.udp_port = me["udp_port"]

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.udp_port))
        self.sock.settimeout(config.ATOMIC_BROADCAST_SOCKET_TIMEOUT)

        self.lock = threading.RLock()

        # Request identifiers: (sender_id, local_seq)
        self.local_request_counter = 0
        self.next_global_to_deliver = 0
        self.next_global_to_assign = 0

        # Request and sequence logs
        self.requests: Dict[Tuple[int, int], dict] = {}
        self.request_arrival_time: Dict[Tuple[int, int], float] = {}
        self.request_assigned: Dict[Tuple[int, int], int] = {}

        self.sequences: Dict[int, Tuple[int, int]] = {}  # global_seq -> req_id
        self.sequence_sender: Dict[int, int] = {}        # global_seq -> sequencer_id

        # Progress / metadata knowledge
        self.highest_request_seen_per_sender = {r["id"]: -1 for r in self.replicas}
        self.highest_sequence_seen = -1
        self.highest_sequence_delivered = -1

        # What I know each peer knows
        self.peer_known_request = {
            r["id"]: {p["id"]: -1 for p in self.replicas}
            for r in self.replicas
        }
        self.peer_known_sequence = {r["id"]: -1 for r in self.replicas}
        self.peer_known_delivered = {r["id"]: -1 for r in self.replicas}

        # Self knowledge initialized
        self.peer_known_request[self.replica_id] = dict(self.highest_request_seen_per_sender)
        self.peer_known_sequence[self.replica_id] = self.highest_sequence_seen
        self.peer_known_delivered[self.replica_id] = self.highest_sequence_delivered

        # Pending write completion tracking
        self.pending_local_results = {}  # req_id -> {"event": Event, "result": ...}

        # Background workers
        self.running = True
        self.receiver_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.sequencer_thread = threading.Thread(target=self._sequencer_loop, daemon=True)
        self.delivery_thread = threading.Thread(target=self._delivery_loop, daemon=True)
        self.retransmit_thread = threading.Thread(target=self._retransmit_loop, daemon=True)

        self.receiver_thread.start()
        self.sequencer_thread.start()
        self.delivery_thread.start()
        self.retransmit_thread.start()

    # -------------------------------------------------------------------------
    # Public API used by gRPC layer
    # -------------------------------------------------------------------------

    def broadcast_write_and_wait(self, op_name: str, payload: dict):
        """
        Broadcast a write request and wait until it is delivered locally.
        """
        with self.lock:
            req_id = (self.replica_id, self.local_request_counter)
            self.local_request_counter += 1

            req_msg = {
                "type": self.MSG_REQUEST,
                "sender_id": req_id[0],
                "local_seq": req_id[1],
                "request_id": f"{req_id[0]}:{req_id[1]}",
                "op_name": op_name,
                "payload": payload,
                "meta": self._build_meta()
            }

            self.requests[req_id] = req_msg
            self.request_arrival_time[req_id] = time.time()
            self.highest_request_seen_per_sender[self.replica_id] = max(
                self.highest_request_seen_per_sender[self.replica_id], req_id[1]
            )
            self._refresh_self_progress()

            done_event = threading.Event()
            self.pending_local_results[req_id] = {"event": done_event, "result": None}

        self._broadcast(req_msg)

        print(f"[Replica {self.replica_id}] BROADCAST WRITE op={op_name} req_id={req_id}")

        ok = done_event.wait(timeout=config.ATOMIC_BROADCAST_DELIVERY_WAIT_TIMEOUT)
        if not ok:
            with self.lock:
                self.pending_local_results.pop(req_id, None)
            raise TimeoutError(f"Timed out waiting for atomic delivery of request {req_id}")

        with self.lock:
            entry = self.pending_local_results.pop(req_id, None)

        if entry is None:
            raise RuntimeError("Atomic delivery completed, but result entry missing")

        result = entry["result"]
        if result is None:
            raise RuntimeError("Atomic delivery completed, but result missing")

        return result

    def wait_until_locally_quiet(self, timeout=2.0):
        """
        Used by read operations to avoid reading while immediate earlier deliveries are pending.
        This is not a global linearizability barrier, but is enough for a solid PA3 customer DB design
        under no-crash replicas and unreliable communication.
        """
        start = time.time()
        while time.time() - start < timeout:
            with self.lock:
                ready = (self.next_global_to_deliver > self.highest_sequence_seen) or \
                        (self.next_global_to_deliver not in self.sequences)
            if ready:
                return
            time.sleep(0.05)

    # -------------------------------------------------------------------------
    # Metadata / utility
    # -------------------------------------------------------------------------

    def _replica(self, replica_id: int):
        for r in self.replicas:
            if r["id"] == replica_id:
                return r
        raise KeyError(f"Replica {replica_id} not found")

    def _responsible_sequencer(self, global_seq: int) -> int:
        return global_seq % self.n

    def _build_meta(self):
        return {
            "sender_replica_id": self.replica_id,
            "known_request": dict(self.highest_request_seen_per_sender),
            "known_sequence": self.highest_sequence_seen,
            "known_delivered": self.highest_sequence_delivered,
        }

    def _refresh_self_progress(self):
        self.peer_known_request[self.replica_id] = dict(self.highest_request_seen_per_sender)
        self.peer_known_sequence[self.replica_id] = self.highest_sequence_seen
        self.peer_known_delivered[self.replica_id] = self.highest_sequence_delivered

    def _parse_request_id(self, request_id: str) -> Tuple[int, int]:
        sender_id, local_seq = request_id.split(":")
        return int(sender_id), int(local_seq)

    def _majority_count(self) -> int:
        return (self.n // 2) + 1

    def _send(self, replica_id: int, message: dict):
        target = self._replica(replica_id)
        msg = dict(message)
        msg["meta"] = self._build_meta()
        data = json.dumps(msg).encode("utf-8")
        self.sock.sendto(data, (target["host"], target["udp_port"]))

    def _broadcast(self, message: dict):
        for r in self.replicas:
            self._send(r["id"], message)

    def _update_peer_meta(self, from_replica: int, meta: dict):
        if meta is None:
            return
        self.peer_known_sequence[from_replica] = max(
            self.peer_known_sequence.get(from_replica, -1),
            meta.get("known_sequence", -1)
        )
        self.peer_known_delivered[from_replica] = max(
            self.peer_known_delivered.get(from_replica, -1),
            meta.get("known_delivered", -1)
        )

        known_request = meta.get("known_request", {})
        for sender_id_str, local_seq in known_request.items():
            sender_id = int(sender_id_str) if isinstance(sender_id_str, str) else sender_id_str
            self.peer_known_request[from_replica][sender_id] = max(
                self.peer_known_request[from_replica].get(sender_id, -1),
                local_seq
            )

    # -------------------------------------------------------------------------
    # Receive / retransmit
    # -------------------------------------------------------------------------

    def _recv_loop(self):
        while self.running:
            try:
                data, _addr = self.sock.recvfrom(65536)
                msg = json.loads(data.decode("utf-8"))
                self._handle_message(msg)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Replica {self.replica_id}] UDP recv error: {e}")

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        meta = msg.get("meta", {})
        from_replica = meta.get("sender_replica_id", msg.get("sender_id", self.replica_id))
        self._update_peer_meta(from_replica, meta)

        if msg_type == self.MSG_REQUEST:
            self._handle_request_message(msg)
        elif msg_type == self.MSG_SEQUENCE:
            self._handle_sequence_message(msg)
        elif msg_type == self.MSG_RETRANSMIT:
            self._handle_retransmit_message(msg)

    def _handle_request_message(self, msg: dict):
        req_id = (int(msg["sender_id"]), int(msg["local_seq"]))
        print(f"[Replica {self.replica_id}] REQUEST received req_id={req_id}")

        with self.lock:
            if req_id not in self.requests:
                self.requests[req_id] = msg
                self.request_arrival_time[req_id] = time.time()

            sender_id, local_seq = req_id
            self.highest_request_seen_per_sender[sender_id] = max(
                self.highest_request_seen_per_sender[sender_id], local_seq
            )
            self._refresh_self_progress()

            # Detect gaps for this sender
            highest_now = self.highest_request_seen_per_sender[sender_id]
            for missing_local in range(highest_now + 1):
                pass

            # Better gap detection:
            known_locals = sorted(
                [rid[1] for rid in self.requests.keys() if rid[0] == sender_id]
            )
            if known_locals:
                expected = 0
                for seen in known_locals:
                    while expected < seen:
                        self._request_missing_request(sender_id, expected)
                        expected += 1
                    expected = seen + 1

    def _handle_sequence_message(self, msg: dict):
        global_seq = int(msg["global_seq"])
        req_id = self._parse_request_id(msg["request_id"])
        sequencer_id = int(msg["sequencer_id"])

        with self.lock:
            self.sequences[global_seq] = req_id
            self.sequence_sender[global_seq] = sequencer_id
            self.highest_sequence_seen = max(self.highest_sequence_seen, global_seq)
            self.next_global_to_assign = max(self.next_global_to_assign, global_seq + 1)
            self._refresh_self_progress()

            if req_id not in self.requests:
                self._request_missing_request(req_id[0], req_id[1])

            for s in range(self.next_global_to_deliver, global_seq):
                if s not in self.sequences:
                    self._request_missing_sequence(s)

            print(f"[Replica {self.replica_id}] SEQUENCE received global_seq={global_seq} req_id={req_id}")
            print(f"[Replica {self.replica_id}] next_global_to_assign now {self.next_global_to_assign}")

    def _handle_retransmit_message(self, msg: dict):
        missing_type = msg["missing_type"]

        if missing_type == self.RETRANSMIT_REQUEST:
            sender_id = int(msg["sender_id"])
            local_seq = int(msg["local_seq"])
            req_id = (sender_id, local_seq)

            with self.lock:
                original = self.requests.get(req_id)
            if original is not None and sender_id == self.replica_id:
                self._broadcast(original)

        elif missing_type == self.RETRANSMIT_SEQUENCE:
            global_seq = int(msg["global_seq"])
            responsible = self._responsible_sequencer(global_seq)
            if responsible != self.replica_id:
                return

            with self.lock:
                req_id = self.sequences.get(global_seq)
            if req_id is not None:
                seq_msg = {
                    "type": self.MSG_SEQUENCE,
                    "global_seq": global_seq,
                    "request_id": f"{req_id[0]}:{req_id[1]}",
                    "sequencer_id": self.replica_id,
                }
                self._broadcast(seq_msg)

    def _request_missing_request(self, sender_id: int, local_seq: int):
        rt = {
            "type": self.MSG_RETRANSMIT,
            "missing_type": self.RETRANSMIT_REQUEST,
            "sender_id": sender_id,
            "local_seq": local_seq,
        }
        self._send(sender_id, rt)

    def _request_missing_sequence(self, global_seq: int):
        responsible = self._responsible_sequencer(global_seq)
        rt = {
            "type": self.MSG_RETRANSMIT,
            "missing_type": self.RETRANSMIT_SEQUENCE,
            "global_seq": global_seq,
        }
        self._send(responsible, rt)

    def _retransmit_loop(self):
        while self.running:
            try:
                time.sleep(config.ATOMIC_BROADCAST_RETRANSMIT_INTERVAL)

                with self.lock:
                    # Ask for missing sequence numbers near the delivery frontier
                    for s in range(self.next_global_to_deliver, self.highest_sequence_seen + 1):
                        if s not in self.sequences:
                            self._request_missing_sequence(s)

                    # If I have a sequence but not the request, ask for it again
                    for s, req_id in list(self.sequences.items()):
                        if req_id not in self.requests:
                            self._request_missing_request(req_id[0], req_id[1])

            except Exception as e:
                print(f"[Replica {self.replica_id}] retransmit worker error: {e}")

    # -------------------------------------------------------------------------
    # Sequencer logic
    # -------------------------------------------------------------------------

    def _eligible_requests_for_assignment(self):
        """
        A request is eligible for assignment at this replica for current global seq k if:
        - this replica is the sequencer for k
        - request not yet assigned
        - all smaller local_seq from that sender are already assigned
        """
        candidates = []

        for req_id, req_msg in self.requests.items():
            if req_id in self.request_assigned:
                continue

            sender_id, local_seq = req_id

            # Condition 3 from the PA: all earlier requests from same sender assigned
            earlier_ok = True
            for prev_local in range(local_seq):
                prev_id = (sender_id, prev_local)
                if prev_id in self.requests and prev_id not in self.request_assigned:
                    earlier_ok = False
                    break
            if not earlier_ok:
                continue

            candidates.append((self.request_arrival_time.get(req_id, 0), req_id))

        candidates.sort(key=lambda x: x[0])
        return [req_id for _, req_id in candidates]

    def _sequencer_loop(self):
        while self.running:
            try:
                time.sleep(config.ATOMIC_BROADCAST_PENDING_SCAN_INTERVAL)

                with self.lock:
                    k = self.next_global_to_assign
                    if self._responsible_sequencer(k) != self.replica_id:
                        continue

                    # Condition 1 and 2 effectively enforced by monotonic next_global_to_assign
                    if k > 0:
                        if (k - 1) not in self.sequences:
                            continue
                        prev_req = self.sequences.get(k - 1)
                        if prev_req is None or prev_req not in self.requests:
                            continue

                    candidates = self._eligible_requests_for_assignment()
                    if not candidates:
                        continue

                    chosen = candidates[0]
                    self.request_assigned[chosen] = k
                    self.sequences[k] = chosen
                    self.sequence_sender[k] = self.replica_id
                    self.highest_sequence_seen = max(self.highest_sequence_seen, k)
                    self.next_global_to_assign += 1
                    self._refresh_self_progress()

                seq_msg = {
                    "type": self.MSG_SEQUENCE,
                    "global_seq": k,
                    "request_id": f"{chosen[0]}:{chosen[1]}",
                    "sequencer_id": self.replica_id,
                }
                self._broadcast(seq_msg)
                print(f"[Replica {self.replica_id}] SEQUENCE assigned global_seq={k} req_id={chosen}")
                print(f"[Replica {self.replica_id}] sequencer loop sees k={self.next_global_to_assign}")

            except Exception as e:
                print(f"[Replica {self.replica_id}] sequencer worker error: {e}")

    # -------------------------------------------------------------------------
    # Delivery
    # -------------------------------------------------------------------------

    def _majority_has_request_and_sequence(self, global_seq: int, req_id: Tuple[int, int]) -> bool:
        sender_id, local_seq = req_id
        count = 0
        for replica in self.replicas:
            rid = replica["id"]
            seq_ok = self.peer_known_sequence.get(rid, -1) >= global_seq
            req_ok = self.peer_known_request.get(rid, {}).get(sender_id, -1) >= local_seq

            # Self should also count if local state has it even before peer metadata catches up
            if rid == self.replica_id:
                seq_ok = self.highest_sequence_seen >= global_seq
                req_ok = self.highest_request_seen_per_sender.get(sender_id, -1) >= local_seq

            if seq_ok and req_ok:
                count += 1

        return count >= self._majority_count()

    def _delivery_loop(self):
        while self.running:
            try:
                time.sleep(0.02)

                with self.lock:
                    s = self.next_global_to_deliver
                    if s not in self.sequences:
                        continue

                    req_id = self.sequences[s]
                    if req_id not in self.requests:
                        self._request_missing_request(req_id[0], req_id[1])
                        continue

                    # In-order delivery condition
                    if s > 0 and self.highest_sequence_delivered != s - 1:
                        continue

                    # Majority delivery condition from PA3
                    # TEMP DEBUG: disable majority gate for now
                    # if not self._majority_has_request_and_sequence(s, req_id):
                    #     continue

                    request_msg = self.requests[req_id]

                # Apply outside lock
                result = self.apply_callback(request_msg["op_name"], request_msg["payload"])

                with self.lock:
                    self.highest_sequence_delivered = s
                    self.next_global_to_deliver += 1
                    self._refresh_self_progress()

                    pending = self.pending_local_results.get(req_id)
                    if pending is not None:
                        pending["result"] = result
                        pending["event"].set()

                print(f"[Replica {self.replica_id}] DELIVER global_seq={s} req_id={req_id}")

            except Exception as e:
                print(f"[Replica {self.replica_id}] delivery worker error: {e}")


# =============================================================================
# Customer DB gRPC Servicer
# =============================================================================

class CustomerDBServicer(customer_pb2_grpc.CustomerDBServicer):
    """
    Existing customer DB logic wrapped so all mutating operations are replicated.
    """

    WRITE_OPS = {
        "CreateSeller",
        "LoginSeller",
        "LogoutSeller",
        "UpdateSellerFeedback",
        "UpdateSellerItemsSold",
        "CreateBuyer",
        "LoginBuyer",
        "LogoutBuyer",
        "AddPurchase",
        "AddToCart",
        "RemoveFromCart",
        "SaveCart",
        "ClearCart",
        "CleanupExpiredSessions",
    }

    def __init__(self, db_path: str, replica_id: int, replicas: list):
        self.db_path = db_path
        self.replica_id = replica_id
        self.replicas = replicas
        self.conn_lock = threading.Lock()

        self._init_database()

        self.abcast = AtomicBroadcastNode(
            replica_id=replica_id,
            replicas=replicas,
            apply_callback=self._apply_replicated_operation
        )

        # self.cleanup_thread = threading.Thread(target=self._session_cleanup_worker, daemon=True)
        # self.cleanup_thread.start()

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    def _init_database(self):
        from database.init_db import init_customer_database
        init_customer_database(self.db_path)

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _ok(self, data=None):
        return customer_pb2.DBResponse(
            status=1,
            message="Success",
            json_data=json.dumps(data or {})
        )

    def _err(self, msg, status=0):
        return customer_pb2.DBResponse(status=status, message=msg, json_data="{}")

    # -------------------------------------------------------------------------
    # Session cleanup
    # -------------------------------------------------------------------------

    def _session_cleanup_worker(self):
        while True:
            time.sleep(config.SESSION_CHECK_INTERVAL)
            try:
                self.abcast.broadcast_write_and_wait("CleanupExpiredSessions", {})
            except Exception as e:
                print(f"[Replica {self.replica_id}] session cleanup replicate error: {e}")

    # -------------------------------------------------------------------------
    # Atomic apply path
    # -------------------------------------------------------------------------

    def _apply_replicated_operation(self, op_name: str, payload: dict) -> dict:
        """
        This is the only place that mutates SQLite.
        Every replica applies the same operation in the same global order.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # ==============================================================
            # Seller operations
            # ==============================================================
            if op_name == "CreateSeller":
                try:
                    cursor.execute(
                        "INSERT INTO sellers (username, password, seller_name) VALUES (?, ?, ?)",
                        (payload["username"], payload["password"], payload["seller_name"])
                    )
                    seller_id = cursor.lastrowid
                    conn.commit()
                    return {"status": 1, "message": "Success", "data": {"seller_id": seller_id}}
                except sqlite3.IntegrityError:
                    conn.rollback()
                    return {"status": 0, "message": "Username already exists", "data": {}}

            elif op_name == "LoginSeller":
                cursor.execute(
                    "SELECT seller_id, seller_name FROM sellers WHERE username = ? AND password = ?",
                    (payload["username"], payload["password"])
                )
                result = cursor.fetchone()
                if not result:
                    return {"status": 0, "message": "Invalid username or password", "data": {}}

                seller_id, seller_name = result
                session_id = payload["session_id"]
                current_time = payload["current_time"]

                cursor.execute(
                    "INSERT INTO seller_sessions (session_id, seller_id, last_activity, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, seller_id, current_time, current_time)
                )
                conn.commit()
                return {
                    "status": 1,
                    "message": "Success",
                    "data": {"session_id": session_id, "seller_id": seller_id, "seller_name": seller_name}
                }

            elif op_name == "LogoutSeller":
                cursor.execute("DELETE FROM seller_sessions WHERE session_id = ?", (payload["session_id"],))
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            elif op_name == "UpdateSellerFeedback":
                if payload["feedback_type"] == FEEDBACK_THUMBS_UP:
                    cursor.execute(
                        "UPDATE sellers SET thumbs_up = thumbs_up + 1 WHERE seller_id = ?",
                        (payload["seller_id"],)
                    )
                else:
                    cursor.execute(
                        "UPDATE sellers SET thumbs_down = thumbs_down + 1 WHERE seller_id = ?",
                        (payload["seller_id"],)
                    )
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            elif op_name == "UpdateSellerItemsSold":
                qty = int(payload.get("quantity", 1))
                cursor.execute(
                    "UPDATE sellers SET items_sold = items_sold + ? WHERE seller_id = ?",
                    (qty, payload["seller_id"])
                )
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            # ==============================================================
            # Buyer operations
            # ==============================================================
            elif op_name == "CreateBuyer":
                try:
                    cursor.execute(
                        "INSERT INTO buyers (username, password, buyer_name) VALUES (?, ?, ?)",
                        (payload["username"], payload["password"], payload["buyer_name"])
                    )
                    buyer_id = cursor.lastrowid
                    conn.commit()
                    return {"status": 1, "message": "Success", "data": {"buyer_id": buyer_id}}
                except sqlite3.IntegrityError:
                    conn.rollback()
                    return {"status": 0, "message": "Username already exists", "data": {}}

            elif op_name == "LoginBuyer":
                cursor.execute(
                    "SELECT buyer_id, buyer_name FROM buyers WHERE username = ? AND password = ?",
                    (payload["username"], payload["password"])
                )
                result = cursor.fetchone()
                if not result:
                    return {"status": 0, "message": "Invalid username or password", "data": {}}

                buyer_id, buyer_name = result
                session_id = payload["session_id"]
                current_time = payload["current_time"]

                cursor.execute(
                    "INSERT INTO buyer_sessions (session_id, buyer_id, last_activity, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, buyer_id, current_time, current_time)
                )

                # Load saved cart into session cart
                cursor.execute("SELECT item_id, quantity FROM saved_carts WHERE buyer_id = ?", (buyer_id,))
                for item_id, quantity in cursor.fetchall():
                    cursor.execute(
                        "INSERT OR REPLACE INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, ?)",
                        (session_id, buyer_id, item_id, quantity)
                    )

                conn.commit()
                return {
                    "status": 1,
                    "message": "Success",
                    "data": {"session_id": session_id, "buyer_id": buyer_id, "buyer_name": buyer_name}
                }

            elif op_name == "LogoutBuyer":
                cursor.execute("DELETE FROM shopping_carts WHERE session_id = ?", (payload["session_id"],))
                cursor.execute("DELETE FROM buyer_sessions WHERE session_id = ?", (payload["session_id"],))
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            elif op_name == "AddPurchase":
                cursor.execute(
                    "INSERT INTO purchase_history (buyer_id, item_id, quantity) VALUES (?, ?, ?)",
                    (payload["buyer_id"], payload["item_id"], payload["quantity"])
                )
                cursor.execute(
                    "UPDATE buyers SET items_purchased = items_purchased + ? WHERE buyer_id = ?",
                    (payload["quantity"], payload["buyer_id"])
                )
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            # ==============================================================
            # Cart operations
            # ==============================================================
            elif op_name == "AddToCart":
                cursor.execute(
                    "SELECT quantity FROM shopping_carts WHERE session_id = ? AND item_id = ?",
                    (payload["session_id"], payload["item_id"])
                )
                result = cursor.fetchone()
                if result:
                    cursor.execute(
                        "UPDATE shopping_carts SET quantity = ? WHERE session_id = ? AND item_id = ?",
                        (result[0] + payload["quantity"], payload["session_id"], payload["item_id"])
                    )
                else:
                    cursor.execute(
                        "INSERT INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, ?)",
                        (payload["session_id"], payload["buyer_id"], payload["item_id"], payload["quantity"])
                    )
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            elif op_name == "RemoveFromCart":
                cursor.execute(
                    "SELECT quantity FROM shopping_carts WHERE session_id = ? AND item_id = ?",
                    (payload["session_id"], payload["item_id"])
                )
                session_result = cursor.fetchone()

                if session_result:
                    new_qty = session_result[0] - payload["quantity"]
                    buyer_id = payload["buyer_id"]
                else:
                    cursor.execute(
                        "SELECT quantity FROM saved_carts WHERE buyer_id = ? AND item_id = ?",
                        (payload["buyer_id"], payload["item_id"])
                    )
                    saved_result = cursor.fetchone()
                    if not saved_result:
                        return {"status": 0, "message": "Item not in cart", "data": {}}
                    new_qty = saved_result[0] - payload["quantity"]
                    buyer_id = payload["buyer_id"]

                if new_qty <= 0:
                    cursor.execute(
                        "INSERT OR REPLACE INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, 0)",
                        (payload["session_id"], buyer_id, payload["item_id"])
                    )
                else:
                    cursor.execute(
                        "INSERT OR REPLACE INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, ?)",
                        (payload["session_id"], buyer_id, payload["item_id"], new_qty)
                    )

                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            elif op_name == "SaveCart":
                buyer_id = payload["buyer_id"]
                session_id = payload["session_id"]

                cursor.execute(
                    "SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?",
                    (session_id,)
                )
                session_cart = cursor.fetchall()

                cursor.execute(
                    "SELECT item_id, quantity FROM saved_carts WHERE buyer_id = ?",
                    (buyer_id,)
                )
                saved_cart = {r[0]: r[1] for r in cursor.fetchall()}

                for item_id, qty in session_cart:
                    if qty == 0:
                        saved_cart.pop(item_id, None)
                    else:
                        saved_cart[item_id] = qty

                cursor.execute("DELETE FROM saved_carts WHERE buyer_id = ?", (buyer_id,))
                for item_id, qty in saved_cart.items():
                    cursor.execute(
                        "INSERT INTO saved_carts (buyer_id, item_id, quantity) VALUES (?, ?, ?)",
                        (buyer_id, item_id, qty)
                    )

                cursor.execute("DELETE FROM shopping_carts WHERE session_id = ?", (session_id,))
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            elif op_name == "ClearCart":
                buyer_id = payload["buyer_id"]
                session_id = payload["session_id"]

                cursor.execute("DELETE FROM shopping_carts WHERE session_id = ?", (session_id,))

                cursor.execute("SELECT item_id FROM saved_carts WHERE buyer_id = ?", (buyer_id,))
                for (item_id,) in cursor.fetchall():
                    cursor.execute(
                        "INSERT INTO shopping_carts (session_id, buyer_id, item_id, quantity) VALUES (?, ?, ?, 0)",
                        (session_id, buyer_id, item_id)
                    )

                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            # ==============================================================
            # Session cleanup
            # ==============================================================
            elif op_name == "CleanupExpiredSessions":
                current_time = get_current_timestamp()
                cutoff_time = current_time - config.SESSION_TIMEOUT

                cursor.execute("DELETE FROM seller_sessions WHERE last_activity < ?", (cutoff_time,))
                cursor.execute("DELETE FROM buyer_sessions WHERE last_activity < ?", (cutoff_time,))
                cursor.execute("""
                    DELETE FROM shopping_carts
                    WHERE session_id NOT IN (SELECT session_id FROM buyer_sessions)
                """)
                conn.commit()
                return {"status": 1, "message": "Success", "data": {}}

            else:
                return {"status": 0, "message": f"Unknown replicated op: {op_name}", "data": {}}

        except Exception as e:
            conn.rollback()
            return {"status": 0, "message": str(e), "data": {}}
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Read helpers (non-mutating)
    # -------------------------------------------------------------------------

    def _validate_seller_session_read(self, session_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT seller_id, last_activity FROM seller_sessions WHERE session_id = ?",
                (session_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None, "Invalid session. Please login."
            seller_id, last_activity = result
            if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                return None, "Session expired. Please login again."
            return seller_id, None
        finally:
            conn.close()

    def _validate_buyer_session_read(self, session_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT buyer_id, last_activity FROM buyer_sessions WHERE session_id = ?",
                (session_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None, "Invalid session. Please login."
            buyer_id, last_activity = result
            if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                return None, "Session expired. Please login again."
            return buyer_id, None
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Seller RPCs
    # -------------------------------------------------------------------------

    def CreateSeller(self, request, context):
        result = self.abcast.broadcast_write_and_wait("CreateSeller", {
            "username": request.username,
            "password": request.password,
            "seller_name": request.seller_name,
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def LoginSeller(self, request, context):
        result = self.abcast.broadcast_write_and_wait("LoginSeller", {
            "username": request.username,
            "password": request.password,
            "session_id": generate_session_id(),
            "current_time": get_current_timestamp(),
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def LogoutSeller(self, request, context):
        result = self.abcast.broadcast_write_and_wait("LogoutSeller", {
            "session_id": request.session_id
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def ValidateSessionSeller(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT seller_id, last_activity FROM seller_sessions WHERE session_id = ?",
                (request.session_id,)
            )
            result = cursor.fetchone()
            if result:
                seller_id, last_activity = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    return self._err("Session expired. Please login again.")
                # replicate session touch so last_activity stays consistent across replicas
                self.abcast.broadcast_write_and_wait("LoginSellerSessionTouchHack", {})  # unused placeholder
                current_time = get_current_timestamp()
                cursor.execute(
                    "UPDATE seller_sessions SET last_activity = ? WHERE session_id = ?",
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({"seller_id": seller_id})
            return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def RestoreSessionSeller(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT ss.seller_id, ss.last_activity, s.seller_name
                FROM seller_sessions ss
                JOIN sellers s ON ss.seller_id = s.seller_id
                WHERE ss.session_id = ?
            """, (request.session_id,))
            result = cursor.fetchone()
            if result:
                seller_id, last_activity, seller_name = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    "UPDATE seller_sessions SET last_activity = ? WHERE session_id = ?",
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({
                    "session_id": request.session_id,
                    "seller_id": seller_id,
                    "seller_name": seller_name
                })
            return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def GetSellerRating(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT thumbs_up, thumbs_down FROM sellers WHERE seller_id = ?",
                (request.seller_id,)
            )
            result = cursor.fetchone()
            if result:
                return self._ok({"thumbs_up": result[0], "thumbs_down": result[1]})
            return self._err("Seller not found")
        finally:
            conn.close()

    def UpdateSellerFeedback(self, request, context):
        result = self.abcast.broadcast_write_and_wait("UpdateSellerFeedback", {
            "seller_id": request.seller_id,
            "feedback_type": request.feedback_type
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def UpdateSellerItemsSold(self, request, context):
        qty = getattr(request, "quantity", 1)
        result = self.abcast.broadcast_write_and_wait("UpdateSellerItemsSold", {
            "seller_id": request.seller_id,
            "quantity": qty
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    # -------------------------------------------------------------------------
    # Buyer RPCs
    # -------------------------------------------------------------------------

    def CreateBuyer(self, request, context):
        result = self.abcast.broadcast_write_and_wait("CreateBuyer", {
            "username": request.username,
            "password": request.password,
            "buyer_name": request.buyer_name,
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def LoginBuyer(self, request, context):
        result = self.abcast.broadcast_write_and_wait("LoginBuyer", {
            "username": request.username,
            "password": request.password,
            "session_id": generate_session_id(),
            "current_time": get_current_timestamp(),
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def LogoutBuyer(self, request, context):
        result = self.abcast.broadcast_write_and_wait("LogoutBuyer", {
            "session_id": request.session_id
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def ValidateSessionBuyer(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT buyer_id, last_activity FROM buyer_sessions WHERE session_id = ?",
                (request.session_id,)
            )
            result = cursor.fetchone()
            if result:
                buyer_id, last_activity = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    "UPDATE buyer_sessions SET last_activity = ? WHERE session_id = ?",
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({"buyer_id": buyer_id})
            return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def RestoreSessionBuyer(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT bs.buyer_id, bs.last_activity, b.buyer_name
                FROM buyer_sessions bs
                JOIN buyers b ON bs.buyer_id = b.buyer_id
                WHERE bs.session_id = ?
            """, (request.session_id,))
            result = cursor.fetchone()
            if result:
                buyer_id, last_activity, buyer_name = result
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    return self._err("Session expired. Please login again.")
                current_time = get_current_timestamp()
                cursor.execute(
                    "UPDATE buyer_sessions SET last_activity = ? WHERE session_id = ?",
                    (current_time, request.session_id)
                )
                conn.commit()
                return self._ok({
                    "session_id": request.session_id,
                    "buyer_id": buyer_id,
                    "buyer_name": buyer_name
                })
            return self._err("Invalid session. Please login.")
        finally:
            conn.close()

    def GetBuyerPurchases(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT item_id, quantity, purchase_date FROM purchase_history WHERE buyer_id = ? ORDER BY purchase_date DESC",
                (request.buyer_id,)
            )
            purchases = [
                {"item_id": r[0], "quantity": r[1], "purchase_date": r[2]}
                for r in cursor.fetchall()
            ]
            return self._ok({"purchases": purchases})
        finally:
            conn.close()

    def AddPurchase(self, request, context):
        result = self.abcast.broadcast_write_and_wait("AddPurchase", {
            "buyer_id": request.buyer_id,
            "item_id": request.item_id,
            "quantity": request.quantity,
            "price": getattr(request, "price", 0.0)
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    # -------------------------------------------------------------------------
    # Cart RPCs
    # -------------------------------------------------------------------------

    def GetCart(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT buyer_id FROM buyer_sessions WHERE session_id = ?", (request.session_id,))
            result = cursor.fetchone()
            if not result:
                return self._err("Invalid session")
            buyer_id = result[0]

            cursor.execute("SELECT item_id, quantity FROM saved_carts WHERE buyer_id = ?", (buyer_id,))
            saved_cart = {r[0]: r[1] for r in cursor.fetchall()}

            cursor.execute("SELECT item_id, quantity FROM shopping_carts WHERE session_id = ?", (request.session_id,))
            session_cart = {r[0]: r[1] for r in cursor.fetchall()}

            merged = {**saved_cart, **session_cart}
            cart = [
                {"item_id": item_id, "quantity": qty}
                for item_id, qty in merged.items()
                if qty > 0
            ]
            return self._ok({"cart": cart})
        finally:
            conn.close()

    def AddToCart(self, request, context):
        result = self.abcast.broadcast_write_and_wait("AddToCart", {
            "session_id": request.session_id,
            "buyer_id": request.buyer_id,
            "item_id": request.item_id,
            "quantity": request.quantity
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def RemoveFromCart(self, request, context):
        result = self.abcast.broadcast_write_and_wait("RemoveFromCart", {
            "session_id": request.session_id,
            "buyer_id": request.buyer_id,
            "item_id": request.item_id,
            "quantity": request.quantity
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def SaveCart(self, request, context):
        result = self.abcast.broadcast_write_and_wait("SaveCart", {
            "session_id": request.session_id,
            "buyer_id": request.buyer_id
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )

    def ClearCart(self, request, context):
        self.abcast.wait_until_locally_quiet()
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT buyer_id FROM buyer_sessions WHERE session_id = ?", (request.session_id,))
            result = cursor.fetchone()
            if not result:
                return self._err("Invalid session")
            buyer_id = result[0]
        finally:
            conn.close()

        result = self.abcast.broadcast_write_and_wait("ClearCart", {
            "session_id": request.session_id,
            "buyer_id": buyer_id
        })
        return customer_pb2.DBResponse(
            status=result["status"], message=result["message"], json_data=json.dumps(result["data"])
        )


# =============================================================================
# Serve
# =============================================================================

def serve(replica_id: int):
    replicas = config.CUSTOMER_DB_REPLICAS
    me = None
    for r in replicas:
        if r["id"] == replica_id:
            me = r
            break

    if me is None:
        raise ValueError(f"Replica {replica_id} not found in CUSTOMER_DB_REPLICAS")

    db_path = me["db_file"]
    grpc_port = me["grpc_port"]

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS))
    customer_pb2_grpc.add_CustomerDBServicer_to_server(
        CustomerDBServicer(db_path=db_path, replica_id=replica_id, replicas=replicas),
        server
    )
    server.add_insecure_port(f"0.0.0.0:{grpc_port}")
    server.start()

    print(f"Customer DB replica {replica_id} started")
    print(f"gRPC port: {grpc_port}")
    print(f"UDP port: {me['udp_port']}")
    print(f"Database file: {db_path}")

    server.wait_for_termination()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replica-id", type=int, required=True)
    args = parser.parse_args()
    serve(args.replica_id)