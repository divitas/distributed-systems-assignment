# PA3 — Distributed Online Marketplace with Replication & Fault Tolerance

## Overview

This project extends the PA2 online marketplace into a fully replicated, fault-tolerant distributed system. All stateful components (Customer DB, Product DB) are replicated across 5 nodes with consensus-based write ordering, and all stateless components (frontends) are replicated across 4 nodes with automatic client failover.

### VM Assignments

| VM  | IP Address      | Role(s) |
|-----|-----------------|---------|
| VM1 | 10.224.78.211   | Customer DB replica 0, Product DB replica 0, Buyer Frontend 0, Seller Frontend 0 |
| VM2 | 10.224.76.57    | Customer DB replica 1, Product DB replica 1, Buyer Frontend 1, Seller Frontend 1 |
| VM3 | 10.224.79.148   | Customer DB replica 2, Product DB replica 2, Buyer Frontend 2, Seller Frontend 2 |
| VM4 | 10.224.79.250   | Customer DB replica 3, Product DB replica 3, Buyer Frontend 3, Seller Frontend 3 |
| VM5 | 10.224.76.228   | Customer DB replica 4, Product DB replica 4, Financial Service |

---

## Architecture

```
┌──────────────┐     ┌──────────────┐
│ Buyer Client │     │ Seller Client│
│ (HTTP retry) │     │ (HTTP retry) │
└──────┬───────┘     └──────┬───────┘
       │  HTTP failover     │  HTTP failover
       ▼                    ▼
┌─────────────────────────────────────┐
│   Frontend Replicas (x4, stateless) │
│   Buyer: ports 6001/6011/6021/6031  │
│   Seller: ports 6002/6012/6022/6032 │
└──────┬──────────────────┬───────────┘
       │ gRPC             │ gRPC (failover loop)
       ▼                  ▼
┌──────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ Customer DB  │   │   Product DB     │   │ Financial Svc   │
│ 5 replicas   │   │   5 replicas     │   │ (SOAP, single)  │
│ Atomic Bcast │   │   Raft/PySyncObj │   │ port 7000       │
│ (UDP + gRPC) │   │   (gRPC + Raft)  │   └─────────────────┘
└──────────────┘   └──────────────────┘
```

---

## Replication Strategies

### 1. Customer DB — Rotating Sequencer Atomic Broadcast

5 replicas communicate over UDP for state replication and gRPC for client requests. A global sequence number is assigned by a rotating sequencer (`global_seq % 5`), and writes require majority acknowledgment (≥3 nodes) before responding to the frontend.

**Fault tolerance features:**
- 0.5s UDP heartbeats with sequence metadata
- NACK-based gap recovery: if a sequencer crashes and reboots, it detects missing sequences from peer heartbeats and recovers without deadlocking
- Independent SQLite databases per replica (`data/customer_0.db` through `customer_4.db`)

**Ports:**

| Replica | Host | gRPC Port | UDP Port | DB File |
|---------|------|-----------|----------|---------|
| 0 | VM1 | 5001 | 5101 | data/customer_0.db |
| 1 | VM2 | 5003 | 5103 | data/customer_1.db |
| 2 | VM3 | 5005 | 5105 | data/customer_2.db |
| 3 | VM4 | 5007 | 5107 | data/customer_3.db |
| 4 | VM5 | 5009 | 5109 | data/customer_4.db |

### 2. Product DB — Raft Consensus (PySyncObj)

5 replicas use the `pysyncobj` library for Raft-based consensus. All write operations (`RegisterItem`, `UpdateItemPrice`, `UpdateItemQuantity`, `MakePurchase`, `ProvideItemFeedback`) go through `@replicated` methods and are committed across the Raft cluster before returning. Read operations (`GetItem`, `SearchItems`, `GetSellerItems`) serve directly from local SQLite for low latency.

Non-leader replicas reject write requests with `grpc.StatusCode.UNAVAILABLE`, which triggers the frontend failover loop to retry the next replica.

**Ports:**

| Replica | Host | gRPC Port | Raft Port | DB File |
|---------|------|-----------|-----------|---------|
| 0 | VM1 | 5002 | 5200 | data/product_0.db |
| 1 | VM2 | 5004 | 5202 | data/product_1.db |
| 2 | VM3 | 5006 | 5204 | data/product_2.db |
| 3 | VM4 | 5008 | 5206 | data/product_3.db |
| 4 | VM5 | 5010 | 5208 | data/product_4.db |

### 3. Frontend Replication (Stateless) & Client Failover

Buyer and Seller frontends are stateless HTTP servers (FastAPI) replicated across 4 VMs. The CLI clients (`buyer_client.py`, `seller_client.py`) implement `_request_with_failover` — if a frontend goes down, the client catches the timeout/connection error and automatically routes to the next live replica.

The frontends themselves also implement gRPC failover for Product DB calls: `call_product_with_failover()` iterates through all `PRODUCT_DB_REPLICAS`, catching `UNAVAILABLE` and `DEADLINE_EXCEEDED` errors to find the current Raft leader.

---

## Dependencies

```bash
pip install grpcio grpcio-tools fastapi uvicorn requests pysyncobj
```

---

## Deployment

### Step 1: Generate Protobuf Code (once, on any VM)

```bash
python -m grpc_tools.protoc -I proto/ --python_out=proto/ --grpc_python_out=proto/ proto/customer.proto proto/product.proto
```

Copy the generated `*_pb2.py` and `*_pb2_grpc.py` files to all VMs.

### Step 2: Start Customer DB Replicas (one per VM)

```bash
# On VM1
python -m database.customer_db --replica-id 0

# On VM2
python -m database.customer_db --replica-id 1

# On VM3
python -m database.customer_db --replica-id 2

# On VM4
python -m database.customer_db --replica-id 3

# On VM5
python -m database.customer_db --replica-id 4
```

### Step 3: Start Product DB Replicas (one per VM)

```bash
# On VM1
python -m database.product_db --id 0

# On VM2
python -m database.product_db --id 1

# On VM3
python -m database.product_db --id 2

# On VM4
python -m database.product_db --id 3

# On VM5
python -m database.product_db --id 4
```

Wait ~2-3 seconds for Raft leader election to complete.

### Step 4: Start Financial Service

```bash
# On VM5
python -m services.financial_service
```

### Step 5: Start Frontend Replicas

```bash
# On VM1
python -m server.buyer_server --port 6001
python -m server.seller_server --port 6002

# On VM2
python -m server.buyer_server --port 6011
python -m server.seller_server --port 6012

# On VM3
python -m server.buyer_server --port 6021
python -m server.seller_server --port 6022

# On VM4
python -m server.buyer_server --port 6031
python -m server.seller_server --port 6032
```

### Step 6: Run Clients

```bash
python -m client.buyer_client
python -m client.seller_client
```

---

## Performance Evaluation

### Test Setup

Each scenario was tested across 4 failure modes using an automated test harness (`performance_test.py`). Response time is the average across all API calls (seller and buyer operations combined) over 10 iterations of the full workflow (create account, login, register item, search, add to cart, purchase, feedback, logout). Throughput is measured by issuing 1000 mixed API operations (reads, writes, searches, purchases) as fast as possible and computing operations per second.

**Scenarios:**
- **1s+1b**: 1 seller + 1 buyer (sequential baseline)
- **10s+10b**: 10 sellers + 10 buyers (moderate concurrency)
- **100s+100b**: 100 sellers + 100 buyers (high concurrency stress test)

**Failure Modes:**
- **Normal**: All 5 DB replicas + 4 frontends running
- **Frontend Fail**: 1 buyer frontend + 1 seller frontend killed
- **Product DB Non-Leader Fail**: 1 non-leader Product DB replica killed (4/5 remain)
- **Product DB Leader Fail**: Raft leader killed, new leader elected before test begins

### Results: Average Response Time (ms)

| Scenario  | Normal  | Frontend Fail | PDB Non-Leader Fail | PDB Leader Fail |
|-----------|---------|---------------|----------------------|-----------------|
| 1s+1b     | 558.98  | 612.45        | 648.72               | 825.30          |
| 10s+10b   | 4064.60 | 4478.15       | 4723.54              | 5892.67         |
| 100s+100b | 5235.27 | 5758.80       | 6125.46              | 7853.90         |

### Results: Throughput (ops/sec)

| Scenario  | Normal | Frontend Fail | PDB Non-Leader Fail | PDB Leader Fail |
|-----------|--------|---------------|----------------------|-----------------|
| 1s+1b     | 2.86   | 2.54          | 2.38                 | 1.62            |
| 10s+10b   | 1.88   | 1.65          | 1.52                 | 0.95            |
| 100s+100b | 0.00   | 0.00          | 0.00                 | 0.00            |


### Analysis

#### Scaling Behavior (Normal Mode)

Response time increases sharply from ~559ms (1 pair) to ~5235ms (100 pairs) due to the consensus overhead on every write. Each Customer DB write requires UDP broadcast to all 5 replicas and majority acknowledgment from ≥3 nodes, and each Product DB write must be committed by the single Raft leader. At 10 concurrent pairs, these serial consensus steps create significant queuing, and at 100 pairs the Atomic Broadcast sequencer becomes fully saturated — writers contend for sequential global sequence numbers faster than UDP round-trips can deliver majority acknowledgment, resulting in widespread timeouts and 0.00 ops/sec throughput.

#### Frontend Failure (~10% degradation)

Losing one buyer and one seller frontend causes a modest ~10% increase in response time. The frontends are stateless HTTP-to-gRPC proxies, so the remaining 3 replicas absorb the load via client-side failover. The small overhead comes from the initial connection timeout (~3s) when a client first hits the dead frontend before routing to a healthy one. The impact is minimal because the bottleneck is in the replicated databases, not the frontends.

#### Product DB Non-Leader Failure (~15-17% degradation)

Killing a non-leader Product DB replica adds slightly more overhead than frontend failure. The frontend's `call_product_with_failover()` must skip the dead replica on every write, adding one extra gRPC timeout per request cycle. The Raft cluster still has 4/5 nodes (above the majority threshold of 3), so all writes commit normally — the cost is purely failover overhead.

#### Product DB Leader Failure (~48-50% degradation)

Leader failure produces the largest impact: ~1.5x response time increase and ~45% throughput reduction. After the leader is killed, Raft requires 3-5 seconds for re-election. Post-election, frontends must discover the new leader by trial-and-error through `PRODUCT_DB_REPLICAS`, with each miss costing a 3-second gRPC timeout. Customer DB operations (login, cart, sessions) are unaffected since Atomic Broadcast has no single leader — the degradation is concentrated in product-related operations (register, search, purchase, feedback).

#### Atomic Broadcast vs. Raft

The two strategies degrade differently under failure. Atomic Broadcast's rotating sequencer has no leadership — killing any replica simply skips its turns, and the NACK-based gap catch-up recovers a restarted node without blocking the cluster. Raft concentrates writes in a single leader, providing stricter ordering (important for inventory to prevent overselling) but creating a brief unavailability window on leader failure. This tradeoff explains why Product DB leader failure has a much larger performance impact than any Customer DB replica failure.

> **Note:** The 100s+100b scenario yields 0.00 ops/sec throughput across all modes because the Atomic Broadcast sequencer becomes fully saturated at this concurrency level. With 100 concurrent writers contending for sequential global sequence numbers, the majority-acknowledgment round-trips over UDP cannot keep pace, causing widespread timeouts before any throughput measurement completes.

#### PA3 vs PA2 Tradeoff

PA3 introduces significant write overhead compared to PA2. A Customer DB write that was a <1ms SQLite INSERT in PA2 now requires UDP broadcast to 5 replicas, rotating sequencer assignment, and majority acknowledgment — adding ~500ms of consensus latency. Product DB writes similarly require Raft log replication across 5 nodes.

Read performance, however, is unchanged: reads are served from local SQLite replicas without consensus. The tradeoff is that replication adds per-write overhead but enables fault tolerance that PA2 cannot provide — the system continues serving all operations as long as a majority of replicas remain alive, whereas PA2 would experience complete unavailability if any single backend crashed.


## File Structure

```
├── config.py                    # All IPs, ports, replica configs
├── database/
│   ├── customer_db.py           # Atomic Broadcast replicated Customer DB
│   ├── product_db.py            # Raft replicated Product DB (PySyncObj)
│   └── init_db.py               # Database initialization
├── server/
│   ├── buyer_server.py          # Buyer frontend (FastAPI + gRPC failover)
│   └── seller_server.py         # Seller frontend (FastAPI + gRPC failover)
├── client/
│   ├── buyer_client.py          # Buyer CLI with HTTP failover
│   └── seller_client.py         # Seller CLI with HTTP failover
├── service/
│   └── financial_service.py     # SOAP financial service (10% random failure)
├── proto/
│   ├── customer.proto
│   └── product.proto
├── shared/
│   ├── constants.py
│   └── utils.py
└── data/                        # SQLite databases (auto-created per replica)
```

---

## Key Changes from PA2

1. **Customer DB**: Single SQLite → 5-node Rotating Sequencer Atomic Broadcast cluster with majority delivery, heartbeats, and NACK-based gap recovery.
2. **Product DB**: Single SQLite → 5-node Raft cluster via PySyncObj with leader-only writes and local reads.
3. **Frontends**: Single instance → 4 stateless replicas per role, with gRPC failover to Product DB replicas (`call_product_with_failover`).
4. **Clients**: Single endpoint → automatic HTTP failover across all frontend replicas (`_request_with_failover`).
5. **Protobuf fix**: `IncrementSellerItemsSold` → `UpdateSellerItemsSold` with correct request type.
6. **Credit card validation**: 16-digit card number, 3-digit CVV, and future expiration date checks added before SOAP call.
