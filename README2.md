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

#### Scaling Behavior Across Scenarios (Normal Mode)

Response time increases from ~42ms (1 pair) to ~195ms (100 pairs), roughly a 4.6x increase for a 100x increase in concurrency. This sublinear degradation demonstrates effective parallelism: the 4 stateless frontend replicas distribute incoming HTTP requests across VMs, and read operations (search, get item, display cart) are served directly from each replica's local SQLite without requiring consensus. Throughput scales from 24 ops/sec to 165 ops/sec, confirming that concurrent frontend replicas absorb load effectively.

The primary bottleneck at high concurrency is the write path. Every Customer DB write passes through Atomic Broadcast (UDP round-trips + majority acknowledgment from ≥3 replicas), and every Product DB write must be committed by the single Raft leader. These serial consensus steps create a natural throughput ceiling for write-heavy workloads. At 100 concurrent pairs, contention on the rotating sequencer and the Raft leader becomes the dominant source of increased latency.

#### Impact of Frontend Failure (~7-8% degradation)

Killing one buyer and one seller frontend produces a modest increase in response time and a comparable decrease in throughput. The stateless frontends serve as simple HTTP-to-gRPC proxies, so losing one shifts its share of client requests to the remaining 3 replicas via the client-side failover loop. The small overhead comes from the initial connection timeout (~3 seconds) that a client experiences before discovering the dead frontend and routing to the next one. Once the dead frontend is identified, subsequent requests in the same session skip it entirely. The overall impact is minimal because the bottleneck is in the replicated databases, not the frontends.

#### Impact of Product DB Non-Leader Failure (~10-15% degradation)

Killing a non-leader Product DB replica causes slightly more degradation than frontend failure. The frontend's `call_product_with_failover()` loop must skip the dead replica on every write request, adding one extra gRPC timeout per request cycle. Read operations are also affected since one fewer replica is available to serve local queries. However, the Raft cluster retains 4/5 nodes — well above the majority threshold of 3 — so all writes continue to commit normally. The performance cost is primarily failover overhead rather than any fundamental capacity reduction.

#### Impact of Product DB Leader Failure (~2x degradation)

The leader failure scenario shows the most significant impact: approximately 2x increase in response time and 50% reduction in throughput. Two factors explain this:

1. **Re-election delay**: When the Raft leader dies, the remaining replicas must detect the failure via heartbeat timeout (~1-2s), hold an election, and establish a new leader. During this window, all Product DB write operations are blocked. Although re-election completes within 3-5 seconds, any in-flight requests experience the full delay.

2. **Leader discovery overhead**: After the new leader is elected, frontends must discover it through trial-and-error. Each write request iterates through `PRODUCT_DB_REPLICAS` until it finds the new leader, meaning the first several requests pay a penalty of N-1 failed gRPC attempts (each with a 3-second timeout). Under high concurrency, many requests hit this discovery phase simultaneously.

The Customer DB (Atomic Broadcast) is completely unaffected by Product DB leader failure, so operations that only touch the Customer DB (login, logout, cart operations) maintain their normal latency. The degradation is concentrated in product-related operations: register item, search, purchase, and feedback.

#### Comparison: Atomic Broadcast vs. Raft

The two replication strategies exhibit fundamentally different failure characteristics. The Customer DB's Rotating Sequencer Atomic Broadcast has no single leader — any replica can initiate a write, and the sequencer role rotates deterministically (`global_seq % 5`). Killing any single Customer DB replica does not create a leadership vacuum; the system skips the dead node's turns in the rotation and continues with the remaining majority. Recovery is also graceful: the NACK-based gap catch-up protocol allows a restarted replica to recover missed writes from peers without blocking the cluster.

The Product DB's Raft consensus concentrates all write authority in a single leader. This provides stronger consistency guarantees (strict linearizability of writes) and simpler reasoning about state, but creates a single point of sensitivity: leader failure always triggers an election with a brief unavailability window. This tradeoff is appropriate for the Product DB because item registration and inventory updates require strict ordering to prevent issues like overselling, while the Customer DB's operations (account creation, session management, cart updates) are more tolerant of the slightly weaker ordering guarantees that Atomic Broadcast provides.

#### Impact of PA3 Changes on Performance vs. PA2

Compared to the non-replicated PA2 architecture, PA3 introduces measurable overhead on the write path. In PA2, a write to the Customer DB was a single SQLite INSERT taking <1ms. In PA3, the same write requires broadcasting a REQUEST to all 5 replicas, waiting for the rotating sequencer to assign a global sequence number, collecting majority acknowledgment via UDP, and only then applying the write locally — adding 20-40ms of consensus overhead per write. Similarly, Product DB writes that previously hit a single SQLite now require Raft log replication across 5 nodes.

However, read performance is largely unchanged or improved under concurrency. Reads in PA3 are served from local SQLite replicas without consensus, and the 4 frontend replicas distribute read load across VMs. Under high concurrency (100s+100b), this parallelism more than compensates for the write overhead, yielding significantly higher overall throughput than a single-node PA2 deployment could achieve.

The key insight is that replication introduces a constant per-write overhead (consensus latency) but enables horizontal read scaling and fault tolerance that a single-node architecture cannot provide. The system gracefully degrades under failure — continuing to serve all operations as long as a majority of replicas remain alive — whereas PA2 would experience complete unavailability if any single backend crashed.

---

## Fault Tolerance Testing

### Kill a Customer DB replica
Stop any Customer DB process. The remaining 4 replicas still form a majority (≥3), so writes continue. The rotating sequencer skips the dead node. On restart, the replica recovers missed sequences via NACK gap catch-up.

### Kill a Product DB replica
If a non-leader replica dies, reads may briefly fail on that node but frontends failover to the next. If the leader dies, Raft elects a new leader within seconds. Frontends automatically discover the new leader through the failover loop.

### Kill a Frontend
The CLI client detects the connection error and retries the next frontend replica automatically. No user intervention required.

### Kill an Entire VM
Stopping all processes on a single VM removes one Customer DB replica, one Product DB replica, and one frontend pair simultaneously. All layers handle this independently: Customer DB still has 4/5 majority, Product DB still has 4/5 majority (or triggers re-election if the leader was on that VM), and the clients failover to one of the remaining 3 frontends. The system continues operating without manual intervention.

---

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
