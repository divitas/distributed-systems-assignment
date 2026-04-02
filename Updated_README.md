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

## Fault Tolerance Testing

### Kill a Customer DB replica
Stop any Customer DB process. The remaining 4 replicas still form a majority (≥3), so writes continue. The rotating sequencer skips the dead node. On restart, the replica recovers missed sequences via NACK gap catch-up.

### Kill a Product DB replica
If a non-leader replica dies, reads may briefly fail on that node but frontends failover to the next. If the leader dies, Raft elects a new leader within seconds. Frontends automatically discover the new leader through the failover loop.

### Kill a Frontend
The CLI client detects the connection error and retries the next frontend replica automatically. No user intervention required.

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
