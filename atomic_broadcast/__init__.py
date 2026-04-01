"""
Rotating Sequencer Atomic Broadcast Protocol

Message types:
  REQUEST   - broadcast by a node when it receives a client operation
  SEQUENCE  - broadcast by the sequencer node to assign a global order
  RETRANSMIT - negative ack sent to recover missing messages

Delivery rule:
  A node delivers request with global seq s only after:
    1. All requests with global seq < s have been delivered.
    2. A majority of nodes have received all Request + Sequence messages
       with global seq <= s.

Sequencer for global seq k is node (k mod n).
"""

import socket
import threading
import json
import time
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [AB-%(name)s] %(message)s')

MSG_REQUEST = "REQUEST"
MSG_SEQUENCE = "SEQUENCE"
MSG_RETRANSMIT = "RETRANSMIT"
MSG_ACK_STATUS = "ACK_STATUS"       # periodic status broadcast for majority check


class AtomicBroadcast:
    """
    Rotating Sequencer Atomic Broadcast over UDP.

    Each node maintains:
      - local_seq_num: counter for requests originated at this node
      - next_global_seq: next global sequence number to assign (if this node is sequencer)
      - pending_requests: dict of (sender_id, local_seq) -> request payload
      - sequenced: dict of global_seq -> (sender_id, local_seq)
      - delivered_up_to: highest global_seq delivered to application (inclusive), -1 initially
      - peer_status: dict of node_id -> highest global_seq for which that peer has
                     received both Request and Sequence messages
    """

    def __init__(self, node_id, peers, on_deliver_callback, udp_port=None):
        """
        Args:
            node_id: integer ID of this node (0..n-1)
            peers: list of dicts with keys 'id', 'host', 'udp_port' for ALL nodes (including self)
            on_deliver_callback: function(operation_dict) called when a request is delivered
            udp_port: UDP port for this node (if None, looked up from peers)
        """
        self.node_id = node_id
        self.n = len(peers)
        self.peers = {p['id']: (p['host'], p['udp_port']) for p in peers}
        self.on_deliver = on_deliver_callback
        self.logger = logging.getLogger(f"Node{node_id}")

        # Find our own UDP address
        if udp_port:
            self.udp_port = udp_port
        else:
            self.udp_port = self.peers[node_id][1]

        # Local sequence counter for requests originated here
        self.local_seq_num = 0
        self.local_seq_lock = threading.Lock()

        # Storage for received Request messages: (sender_id, local_seq) -> payload
        self.requests = {}
        self.requests_lock = threading.Lock()

        # Highest local_seq received from each sender
        self.highest_local_seq = defaultdict(lambda: -1)

        # Sequence assignments: global_seq -> (sender_id, local_seq)
        self.sequenced = {}
        self.sequenced_lock = threading.Lock()

        # Reverse mapping: (sender_id, local_seq) -> global_seq
        self.request_to_global = {}

        # Track which requests have been assigned a global sequence number
        self.assigned_requests = set()  # set of (sender_id, local_seq)

        # Next global sequence number this node needs to assign (if it's our turn)
        self.next_global_to_assign = 0
        self.assign_lock = threading.Lock()

        # Delivery tracking
        self.delivered_up_to = -1  # highest delivered global_seq
        self.delivery_lock = threading.Lock()

        # Peer status for majority check: peer_id -> highest_complete_global_seq
        # "complete" means peer has both the Request and Sequence for that global_seq
        self.peer_status = defaultdict(lambda: -1)
        self.peer_status[self.node_id] = -1
        self.peer_status_lock = threading.Lock()

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', self.udp_port))
        self.sock.settimeout(1.0)

        # Condition variable to wake sequencer / delivery threads
        self.new_message_event = threading.Event()

        # Running flag
        self.running = True

        # Start threads
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

        self.seq_thread = threading.Thread(target=self._sequencer_loop, daemon=True)
        self.seq_thread.start()

        self.deliver_thread = threading.Thread(target=self._delivery_loop, daemon=True)
        self.deliver_thread.start()

        self.retransmit_thread = threading.Thread(target=self._retransmit_loop, daemon=True)
        self.retransmit_thread.start()

        self.status_thread = threading.Thread(target=self._status_broadcast_loop, daemon=True)
        self.status_thread.start()

        self.logger.info(f"Atomic Broadcast node {node_id} started on UDP port {self.udp_port}")

    # =========================================================================
    # Public API
    # =========================================================================

    def submit(self, operation):
        """
        Submit a client operation to the broadcast group.
        Called by the local gRPC servicer when it receives a client request.
        Returns an Event that will be set when the operation is delivered.
        """
        with self.local_seq_lock:
            local_seq = self.local_seq_num
            self.local_seq_num += 1

        req_id = (self.node_id, local_seq)
        done_event = threading.Event()

        # Store locally
        with self.requests_lock:
            self.requests[req_id] = {
                'operation': operation,
                'done_event': done_event,
                'result': None
            }
            self.highest_local_seq[self.node_id] = max(
                self.highest_local_seq[self.node_id], local_seq
            )

        # Broadcast REQUEST to all peers (including self, already stored)
        msg = {
            'type': MSG_REQUEST,
            'sender_id': self.node_id,
            'local_seq': local_seq,
            'operation': operation,
            'highest_local_seq': dict(self.highest_local_seq),
            'status_seq': self._my_complete_seq(),
        }
        self._broadcast(msg)
        self.new_message_event.set()

        return done_event, req_id

    def get_result(self, req_id):
        """Get the result of a submitted operation after its done_event is set."""
        with self.requests_lock:
            entry = self.requests.get(req_id)
            if entry:
                return entry.get('result')
        return None

    def set_result(self, req_id, result):
        """Set the result for a request (called by application after processing)."""
        with self.requests_lock:
            entry = self.requests.get(req_id)
            if entry:
                entry['result'] = result
                entry['done_event'].set()

    def shutdown(self):
        self.running = False
        self.sock.close()

    # =========================================================================
    # Internal: UDP send/recv
    # =========================================================================

    def _send_to(self, peer_id, msg_dict):
        try:
            data = json.dumps(msg_dict).encode('utf-8')
            addr = self.peers[peer_id]
            self.sock.sendto(data, addr)
        except Exception as e:
            self.logger.debug(f"Send to {peer_id} failed: {e}")

    def _broadcast(self, msg_dict):
        data = json.dumps(msg_dict).encode('utf-8')
        for pid, addr in self.peers.items():
            if pid == self.node_id:
                continue
            try:
                self.sock.sendto(data, addr)
            except Exception as e:
                self.logger.debug(f"Broadcast to {pid} failed: {e}")

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                msg = json.loads(data.decode('utf-8'))
                self._handle_message(msg)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.debug(f"Recv error: {e}")

    # =========================================================================
    # Message handling
    # =========================================================================

    def _handle_message(self, msg):
        msg_type = msg.get('type')

        if msg_type == MSG_REQUEST:
            self._handle_request(msg)
        elif msg_type == MSG_SEQUENCE:
            self._handle_sequence(msg)
        elif msg_type == MSG_RETRANSMIT:
            self._handle_retransmit(msg)
        elif msg_type == MSG_ACK_STATUS:
            self._handle_ack_status(msg)

    def _handle_request(self, msg):
        sender_id = msg['sender_id']
        local_seq = msg['local_seq']
        req_id = (sender_id, local_seq)

        with self.requests_lock:
            if req_id not in self.requests:
                self.requests[req_id] = {
                    'operation': msg['operation'],
                    'done_event': None,
                    'result': None,
                }
            self.highest_local_seq[sender_id] = max(
                self.highest_local_seq[sender_id], local_seq
            )

        # Update peer status from piggybacked info
        if 'status_seq' in msg:
            with self.peer_status_lock:
                old = self.peer_status[sender_id]
                self.peer_status[sender_id] = max(old, msg['status_seq'])

        self.new_message_event.set()

    def _handle_sequence(self, msg):
        global_seq = msg['global_seq']
        sender_id = msg['sender_id']
        local_seq = msg['local_seq']
        req_id = (sender_id, local_seq)

        with self.sequenced_lock:
            if global_seq not in self.sequenced:
                self.sequenced[global_seq] = req_id
                self.request_to_global[req_id] = global_seq
                self.assigned_requests.add(req_id)

        # Update peer status from piggybacked info
        sequencer_id = msg.get('sequencer_id', global_seq % self.n)
        if 'status_seq' in msg:
            with self.peer_status_lock:
                old = self.peer_status[sequencer_id]
                self.peer_status[sequencer_id] = max(old, msg['status_seq'])

        self.new_message_event.set()

    def _handle_retransmit(self, msg):
        """Respond to a retransmit request."""
        missing_type = msg.get('missing_type')
        requester_id = msg.get('requester_id')

        if missing_type == 'request':
            sender_id = msg['sender_id']
            local_seq = msg['local_seq']
            req_id = (sender_id, local_seq)
            with self.requests_lock:
                entry = self.requests.get(req_id)
                if entry:
                    retransmit_msg = {
                        'type': MSG_REQUEST,
                        'sender_id': sender_id,
                        'local_seq': local_seq,
                        'operation': entry['operation'],
                        'highest_local_seq': dict(self.highest_local_seq),
                        'status_seq': self._my_complete_seq(),
                    }
                    self._send_to(requester_id, retransmit_msg)

        elif missing_type == 'sequence':
            global_seq = msg['global_seq']
            with self.sequenced_lock:
                if global_seq in self.sequenced:
                    req_id = self.sequenced[global_seq]
                    seq_msg = {
                        'type': MSG_SEQUENCE,
                        'global_seq': global_seq,
                        'sender_id': req_id[0],
                        'local_seq': req_id[1],
                        'sequencer_id': self.node_id,
                        'status_seq': self._my_complete_seq(),
                    }
                    self._send_to(requester_id, seq_msg)

    def _handle_ack_status(self, msg):
        peer_id = msg['node_id']
        status_seq = msg['status_seq']
        with self.peer_status_lock:
            old = self.peer_status[peer_id]
            self.peer_status[peer_id] = max(old, status_seq)
        self.new_message_event.set()

    # =========================================================================
    # Sequencer loop
    # =========================================================================

    def _sequencer_loop(self):
        """
        If this node is the sequencer for the next unassigned global_seq,
        pick a pending request and assign it.
        """
        while self.running:
            self.new_message_event.wait(timeout=0.5)
            self.new_message_event.clear()

            while self.running:
                with self.assign_lock:
                    k = self.next_global_to_assign

                # Am I the sequencer for k?
                if k % self.n != self.node_id:
                    # Not my turn — but track the global assignment frontier
                    with self.sequenced_lock:
                        if k in self.sequenced:
                            with self.assign_lock:
                                self.next_global_to_assign = k + 1
                            continue
                    break

                # Condition 1: I must have received all Sequence messages with
                # global seq < k
                with self.sequenced_lock:
                    all_prior_sequenced = all(
                        g in self.sequenced for g in range(k)
                    )
                if not all_prior_sequenced:
                    break

                # Condition 2: I must have received all Request messages to which
                # global seq < k have been assigned
                ready = True
                with self.sequenced_lock:
                    for g in range(k):
                        req_id = self.sequenced.get(g)
                        if req_id:
                            with self.requests_lock:
                                if req_id not in self.requests:
                                    ready = False
                                    break
                if not ready:
                    break

                # Pick a pending request that hasn't been assigned yet
                # Condition 3: All prior local_seq from the same sender must
                # already be assigned
                chosen = None
                with self.requests_lock:
                    candidates = []
                    for req_id in self.requests:
                        if req_id in self.assigned_requests:
                            continue
                        sid, lseq = req_id
                        # Check condition 3
                        all_prior_assigned = all(
                            (sid, prev) in self.assigned_requests
                            for prev in range(lseq)
                        )
                        if all_prior_assigned:
                            candidates.append(req_id)

                    if candidates:
                        # Pick deterministically: lowest sender_id, then lowest local_seq
                        candidates.sort()
                        chosen = candidates[0]

                if chosen is None:
                    break  # No suitable request yet, wait for more

                # Assign global sequence number k to this request
                with self.sequenced_lock:
                    self.sequenced[k] = chosen
                    self.request_to_global[chosen] = k
                    self.assigned_requests.add(chosen)

                with self.assign_lock:
                    self.next_global_to_assign = k + 1

                # Broadcast SEQUENCE message
                seq_msg = {
                    'type': MSG_SEQUENCE,
                    'global_seq': k,
                    'sender_id': chosen[0],
                    'local_seq': chosen[1],
                    'sequencer_id': self.node_id,
                    'status_seq': self._my_complete_seq(),
                }
                self._broadcast(seq_msg)
                self.logger.info(f"Assigned global_seq {k} -> request {chosen}")

    # =========================================================================
    # Delivery loop
    # =========================================================================

    def _delivery_loop(self):
        while self.running:
            self.new_message_event.wait(timeout=0.5)

            while self.running:
                with self.delivery_lock:
                    next_to_deliver = self.delivered_up_to + 1

                # Do we have the Sequence for next_to_deliver?
                with self.sequenced_lock:
                    if next_to_deliver not in self.sequenced:
                        break
                    req_id = self.sequenced[next_to_deliver]

                # Do we have the Request?
                with self.requests_lock:
                    entry = self.requests.get(req_id)
                    if not entry:
                        break

                # Majority check: a majority must have received all Request +
                # Sequence messages with global seq <= next_to_deliver
                majority_needed = (self.n // 2) + 1
                with self.peer_status_lock:
                    # Update our own status first
                    self.peer_status[self.node_id] = self._my_complete_seq()
                    count = sum(
                        1 for pid in self.peer_status
                        if self.peer_status[pid] >= next_to_deliver
                    )

                if count < majority_needed:
                    break

                # Deliver!
                operation = entry['operation']
                self.logger.info(
                    f"Delivering global_seq {next_to_deliver}: {operation.get('op', '?')}"
                )

                # Call application callback
                result = self.on_deliver(operation)

                # Store result and signal done
                with self.requests_lock:
                    entry['result'] = result
                    if entry['done_event']:
                        entry['done_event'].set()

                with self.delivery_lock:
                    self.delivered_up_to = next_to_deliver

    # =========================================================================
    # Retransmit loop (negative acknowledgement)
    # =========================================================================

    def _retransmit_loop(self):
        """Periodically check for gaps and request retransmissions."""
        while self.running:
            time.sleep(1.0)

            with self.delivery_lock:
                next_needed = self.delivered_up_to + 1

            # Check for missing Sequence messages
            # We look ahead a bit to detect gaps
            with self.assign_lock:
                frontier = self.next_global_to_assign

            # Also look at what we've seen in sequenced
            with self.sequenced_lock:
                max_seen = max(self.sequenced.keys()) if self.sequenced else -1

            check_up_to = max(frontier, max_seen + 1, next_needed + self.n * 2)

            for g in range(next_needed, check_up_to):
                with self.sequenced_lock:
                    if g not in self.sequenced:
                        # Missing Sequence message — request from sequencer
                        sequencer = g % self.n
                        if sequencer != self.node_id:
                            self._send_to(sequencer, {
                                'type': MSG_RETRANSMIT,
                                'missing_type': 'sequence',
                                'global_seq': g,
                                'requester_id': self.node_id,
                            })
                    else:
                        # We have the sequence, check if we have the request
                        req_id = self.sequenced[g]
                        with self.requests_lock:
                            if req_id not in self.requests:
                                sender = req_id[0]
                                if sender != self.node_id:
                                    self._send_to(sender, {
                                        'type': MSG_RETRANSMIT,
                                        'missing_type': 'request',
                                        'sender_id': req_id[0],
                                        'local_seq': req_id[1],
                                        'requester_id': self.node_id,
                                    })

            # Also check for gaps in local_seq from each sender
            for sid in range(self.n):
                highest = self.highest_local_seq[sid]
                for lseq in range(highest + 1):
                    req_id = (sid, lseq)
                    with self.requests_lock:
                        if req_id not in self.requests:
                            if sid != self.node_id:
                                self._send_to(sid, {
                                    'type': MSG_RETRANSMIT,
                                    'missing_type': 'request',
                                    'sender_id': sid,
                                    'local_seq': lseq,
                                    'requester_id': self.node_id,
                                })

    # =========================================================================
    # Status broadcast loop
    # =========================================================================

    def _status_broadcast_loop(self):
        """Periodically broadcast our status so peers can do majority checks."""
        while self.running:
            time.sleep(0.5)
            my_status = self._my_complete_seq()
            msg = {
                'type': MSG_ACK_STATUS,
                'node_id': self.node_id,
                'status_seq': my_status,
            }
            self._broadcast(msg)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _my_complete_seq(self):
        """
        Return the highest global_seq s such that we have both the Request and
        Sequence message for all global_seq 0..s.
        """
        with self.sequenced_lock:
            s = -1
            while True:
                next_s = s + 1
                if next_s not in self.sequenced:
                    break
                req_id = self.sequenced[next_s]
                with self.requests_lock:
                    if req_id not in self.requests:
                        break
                s = next_s
            return s
