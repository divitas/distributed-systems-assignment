# PA3: Customer Database Replication

## Overview

In this phase of the distributed marketplace system, replication for the Customer Database service is implemented using a rotating sequencer atomic broadcast protocol.

This ensures:
* Strong consistency across replicas
* Total order of writes
* Fault tolerance for frontend requests

The system has been successfully tested for the following operations:
* Buyer account creation and login
* Seller account creation and login

---

## Architecture

### Customer DB Replication Model

The system utilizes:
* 5 replicas
* gRPC for client/frontend communication
* UDP for inter-replica atomic broadcast

### Replica Deployment

| Replica ID | VM  | IP            | gRPC Port | UDP Port |
| ---------- | --- | ------------- | --------- | -------- |
| 0          | VM1 | 10.224.76.209 | 5001      | 5101     |
| 1          | VM3 | 10.224.78.247 | 5003      | 5103     |
| 2          | VM4 | 10.224.79.170 | 5005      | 5105     |
| 3          | VM5 | 10.224.77.206 | 5007      | 5107     |
| 4          | VM5 | 10.224.77.206 | 5009      | 5109     |

---

## Atomic Broadcast Design

### Protocol Used: Rotating Sequencer

Each write request goes through the following sequence:

#### 1. REQUEST Broadcast
* The replica receiving a client request generates a request ID:
  ```
  req_id = (replica_id, local_seq)
  ```
* It broadcasts the REQUEST to all replicas via UDP.

#### 2. Sequence Assignment
* A global sequence number `k` is assigned by the replica whose ID matches:
  ```
  sequencer = k % N
  ```
* That replica assigns the sequence:
  ```
  SEQUENCE(global_seq=k, req_id)
  ```

#### 3. Delivery
Each replica delivers requests in order when:
* The sequence has been received.
* The corresponding request has been received.
* All earlier requests have been delivered.

---

## Implementation Details

### Data Structures

Each replica maintains:
* `requests`: Mapping of `req_id` to operation.
* `sequences`: Mapping of `global_seq` to `req_id`.
* `next_global_to_assign`: The next sequence number to assign.
* `next_global_to_deliver`: The next sequence number to deliver.

### Critical Fixes

#### 1. Sequencer Progress Synchronization
**Problem:** Initially, only replica 0 progressed its sequence numbers, causing others to stall.
**Fix:** On receiving a `SEQUENCE` message, the replica updates its assignment pointer:
```python
self.next_global_to_assign = max(self.next_global_to_assign, global_seq + 1)
```
**Impact:** This properly enables the rotating sequencer pattern, fixing the issue where the system would hang after the first request.

#### 2. Disabled Majority Delivery Check (Temporary)
**Problem:** The original logic required a strict majority confirmation before delivery:
```python
if not self._majority_has_request_and_sequence(...):
    continue
```
Since there was no mechanism to track peer knowledge, the delivery condition was never satisfied, resulting in a deadlock.
**Temporary Fix:** The majority check is currently disabled.
**Reason:** This unblocks system progress to verify the basic correctness of the ordering and replication logic. This will be reintroduced later.

#### 3. Disabled Background Session Cleanup
**Problem:** Each replica independently triggered cleanup writes at startup, leading to a flood of timeouts before user requests could be processed.
**Fix:** Disabled the cleanup thread temporarily.

#### 4. Frontend Failover Configuration Simplification
**Problem:** Multiple frontend replicas were configured but not actively running.
**Fix:** Temporarily reduced the configuration to a single active frontend:
```python
BUYER_FRONTEND_REPLICAS = [
    {"id": 0, "host": "10.224.78.247", "port": 6001}
]
```

### Debugging Capabilities

Logs have been added for visibility to track state transitions:
```
BROADCAST WRITE
REQUEST received
SEQUENCE assigned
SEQUENCE received
DELIVER
```
This enables tracking of message propagation, sequence ordering, and delivery.

---

## Functional Validation

### Supported Operations
**Buyer:** Create Account, Login
**Seller:** Create Account, Login

### Replication Validation
After executing write operations, all replicas hold identical data:
```sql
select * from buyers;
select * from sellers;
```
Verified consistently across `customer_0.db` through `customer_4.db`.

---

## How to Run

### 1. Pull Code and Activate Environment (All VMs)
```bash
git pull origin main
source venv/bin/activate
```

### 2. Start Customer Replicas
**VM1:**
```bash
python3 database/customer_db.py --replica-id 0
```
**VM3:**
```bash
python3 database/customer_db.py --replica-id 1
```
**VM4:**
```bash
python3 database/customer_db.py --replica-id 2
```
**VM5:**
```bash
python3 database/customer_db.py --replica-id 3
python3 database/customer_db.py --replica-id 4
```

### 3. Start Frontends
**Buyer Frontend (VM3):**
```bash
python3 server/buyer_server.py --port 6001
```
**Seller Frontend (VM4):**
```bash
python3 server/seller_server.py --port 6002
```

### 4. Start Product DB
**VM2:**
```bash
python3 database/product_db.py
```

### 5. Run Clients
**Local/Client Machine:**
```bash
python3 client/buyer_client.py
python3 client/seller_client.py
```

---

## Known Limitations

* The majority delivery condition is currently disabled.
* No retransmission (NACK) logic is implemented yet.
* The system does not currently handle failure recovery for missing messages.
* Session cleanup replication is currently disabled.

---

## Next Steps

1. Reintroduce the majority delivery condition with explicit metadata tracking for peer knowledge.
2. Implement NACK-based retransmission for lost UDP packets.
3. Build Product DB replication using the Raft consensus protocol.
4. Improve failure handling and system recovery.
