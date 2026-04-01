# PA3 - Replicated Online Marketplace

## System Design

This system extends PA2 by replicating all server components for fault tolerance:

**Customer Database (5 replicas):** Uses a custom Rotating Sequencer Atomic Broadcast
protocol over UDP. All write operations (account creation, login, cart modifications,
purchases) are broadcast to all replicas and assigned a global sequence number by a
rotating sequencer (node `k mod 5` assigns sequence number `k`). Delivery requires
majority acknowledgment. Read operations (session validation, ratings, purchase history)
are served locally. Communication between replicas uses unreliable UDP; missing messages
are recovered via negative acknowledgments (retransmit requests).

**Product Database (5 replicas):** Uses PySyncObj, an open-source Python Raft
implementation. Write operations (register item, update price/quantity, purchase, feedback)
go through Raft consensus. Read operations are served from the local replica's SQLite.
Handles crash failures and unreliable communication via Raft's leader election and log
replication.

**Seller Frontend (4 replicas) & Buyer Frontend (4 replicas):** Stateless FastAPI servers.
Each frontend replica connects to a random backend database replica with automatic
failover. Clients maintain a list of all frontend replicas and failover to the next one on
connection failure.

**Assumptions:** Servers do not fail for the customer DB (per assignment spec); product DB
servers may crash. Frontend replicas may crash and are restarted with the same IP. All
communication between client and frontend uses REST, frontend to backend uses gRPC,
and financial transactions use SOAP — same as PA2.

## Project Structure

```
├── config.py                           # All replica addresses and settings
├── requirements.txt                    # Python dependencies
├── start.sh                            # Startup script
├── benchmark.py                        # Performance measurement
├── atomic_broadcast/
│   └── __init__.py                     # Rotating Sequencer Atomic Broadcast
├── database/
│   ├── init_db.py                      # DB schema initialization (unchanged)
│   ├── customer_db_replicated.py       # Customer DB with atomic broadcast
│   └── product_db_replicated.py        # Product DB with Raft (PySyncObj)
├── frontend/
│   ├── buyer_server_replicated.py      # Buyer frontend with failover
│   └── seller_server_replicated.py     # Seller frontend with failover
├── client/
│   ├── buyer_client.py                 # Buyer CLI with replica failover
│   └── seller_client.py               # Seller CLI with replica failover
├── shared/
│   ├── constants.py                    # Shared constants (unchanged)
│   ├── utils.py                        # Utility functions (unchanged)
│   └── protocol.py                     # Protocol helpers (unchanged)
└── proto/
    ├── customer.proto                  # Customer DB protobuf (unchanged)
    └── product.proto                   # Product DB protobuf (unchanged)
```

## Deployment (4 VMs minimum)

### VM1 (10.224.78.211)
- Customer DB replicas 0, 1
- Product DB replica 2
- Buyer Frontend replica 2
- Seller Frontend replica 2

### VM2 (10.224.76.57)
- Customer DB replicas 2, 3
- Product DB replicas 0, 1
- Buyer Frontend replica 3
- Seller Frontend replica 3

### VM3 (10.224.79.148)
- Customer DB replica 4
- Product DB replica 3
- Buyer Frontend replicas 0
- Seller Frontend replica 1

### VM4 (10.224.79.250)
- Product DB replica 4
- Buyer Frontend replica 1
- Seller Frontend replica 0

### Starting Components
```bash
# Install dependencies on all VMs
pip install -r requirements.txt

# On VM1:
python database/customer_db_replicated.py --node-id 0 &
python database/customer_db_replicated.py --node-id 1 &
python database/product_db_replicated.py --node-id 2 &
python frontend/buyer_server_replicated.py --replica-id 2 &
python frontend/seller_server_replicated.py --replica-id 2 &

# On VM2:
python database/customer_db_replicated.py --node-id 2 &
python database/customer_db_replicated.py --node-id 3 &
python database/product_db_replicated.py --node-id 0 &
python database/product_db_replicated.py --node-id 1 &
python frontend/buyer_server_replicated.py --replica-id 3 &
python frontend/seller_server_replicated.py --replica-id 3 &

# On VM3:
python database/customer_db_replicated.py --node-id 4 &
python database/product_db_replicated.py --node-id 3 &
python frontend/buyer_server_replicated.py --replica-id 0 &
python frontend/seller_server_replicated.py --replica-id 1 &

# On VM4:
python database/product_db_replicated.py --node-id 4 &
python frontend/buyer_server_replicated.py --replica-id 1 &
python frontend/seller_server_replicated.py --replica-id 0 &
```

## Running Benchmarks
```bash
# Scenario 1: 1 seller + 1 buyer
python benchmark.py --scenario 1 --runs 10 --ops 1000

# Scenario 2: 10 sellers + 10 buyers
python benchmark.py --scenario 2 --runs 10 --ops 1000

# Scenario 3: 100 sellers + 100 buyers
python benchmark.py --scenario 3 --runs 10 --ops 1000
```

To test failure conditions, terminate specific processes before running benchmarks.

## Current Status

**What works:**
- Rotating Sequencer Atomic Broadcast for customer DB replication
- Raft-based product DB replication via PySyncObj
- Stateless frontend replication with client-side failover
- All PA2 APIs preserved with identical interface
- Performance benchmarking across all scenarios

**Limitations:**
- Session validation is read-local (eventual consistency possible briefly after login)
- Atomic broadcast assumes no node crashes (per assignment spec)
- PySyncObj Raft leader election may cause brief unavailability (~3s) on leader failure
