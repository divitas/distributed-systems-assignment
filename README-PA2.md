# PA2 - Online Marketplace Distributed System

## System Overview

This is PA2, built on top of PA1. The system is an online marketplace with sellers and buyers, now using:
- **REST** for client ↔ frontend server communication (via FastAPI)
- **gRPC** for frontend server ↔ database communication
- **SOAP** for the financial transactions service (via Flask, called during MakePurchase)

---

## Development Setup

### Mac (Local Machine) - setup for ssh from mac to vms is at the bottom!!
- Where all code is written and edited
- Where proto stubs are generated using `protoc`
- Connected to all 5 VMs via SSH
- Uses VS Code Remote SSH extension to edit files directly on VMs
- Pushes code to GitHub, which syncs to all VMs via `git pull`

### Workflow
1. Edit code on Mac (or via VS Code SSH into a VM)
2. `git push` from Mac
3. `git pull` on the relevant VMs
4. Restart the affected server on that VM

---

## Architecture

```
Sellers/Buyers (VM5)
     |
     | REST (HTTP)
     |
Seller Frontend (VM4)     Buyer Frontend (VM3)
     |         \          /         |
     |          \        /          |
     |    gRPC   \      /   gRPC    |
     |            \    /            |
Customer DB (VM1)   \/   Product DB (VM2)
                    
                 SOAP (HTTP)
Buyer Frontend (VM3) ---------> Financial Service (VM5)
```

## VM Layout

| VM | Role | Port |
|----|------|------|
| VM1 | Customer Database (gRPC server) | 5001 |
| VM2 | Product Database (gRPC server) | 5002 |
| VM3 | Buyer Frontend (FastAPI) | 6001 |
| VM4 | Seller Frontend (FastAPI) | 6002 |
| VM5 | Clients + Financial SOAP Service | 7000 |

---

## Project Structure

```
distributed-systems-assignment/
├── config.py                        # All IPs and ports — edit this for deployment
├── proto/                           # gRPC definitions
│   ├── customer.proto               # Customer DB service definition
│   ├── product.proto                # Product DB service definition
│   ├── customer_pb2.py              # Generated — do not edit
│   ├── customer_pb2_grpc.py         # Generated — do not edit
│   ├── product_pb2.py               # Generated — do not edit
│   ├── product_pb2_grpc.py          # Generated — do not edit
│   └── __init__.py
├── database/
│   ├── init_db.py                   # Initializes SQLite schemas
│   ├── customer_db.py               # Customer DB gRPC server
│   └── product_db.py                # Product DB gRPC server
├── server/
│   ├── seller_server.py             # Seller FastAPI server
│   └── buyer_server.py              # Buyer FastAPI server (includes MakePurchase)
├── client/
│   ├── seller_client.py             # Seller CLI (uses REST)
│   └── buyer_client.py              # Buyer CLI (uses REST, includes MakePurchase)
├── services/
│   └── financial_service.py         # SOAP financial service (Flask)
└── tests/
    └── performance_test.py
```

---

## Configuration

All IPs and ports are in `config.py`. Make sure these are set correctly before running:

```python
CUSTOMER_DB_HOST = "10.x.x.x"        # VM1 IP
CUSTOMER_DB_PORT = 5001

PRODUCT_DB_HOST = "10.x.x.x"         # VM2 IP
PRODUCT_DB_PORT = 5002

BUYER_FRONTEND_HOST = "10.x.x.x"     # VM3 IP
BUYER_FRONTEND_PORT = 6001

SELLER_FRONTEND_HOST = "10.x.x.x"    # VM4 IP
SELLER_FRONTEND_PORT = 6002

FINANCIAL_SERVICE_HOST = "10.x.x.x"  # VM5 IP
FINANCIAL_SERVICE_PORT = 7000
```

---

## Installation (run on ALL VMs)

```bash
git clone <your-repo-url>
cd distributed-systems-assignment
pip install grpcio grpcio-tools fastapi uvicorn requests flask lxml --break-system-packages
```

Also open the required port on each VM:
```bash
# VM1
sudo ufw allow 5001

# VM2
sudo ufw allow 5002

# VM3
sudo ufw allow 6001

# VM4
sudo ufw allow 6002

# VM5
sudo ufw allow 7000
```

---

## Running the System

**Always start in this order:**

### VM1 — Customer Database
```bash
python3 database/init_db.py
python3 database/customer_db.py
```

### VM2 — Product Database
```bash
python3 database/init_db.py
python3 database/product_db.py
```

### VM3 — Buyer Frontend
```bash
python3 server/buyer_server.py
```

### VM4 — Seller Frontend
```bash
python3 server/seller_server.py
```

### VM5 — Financial Service + Clients
```bash
# Start financial service first
python3 services/financial_service.py

# Then in separate terminals run clients
python3 client/seller_client.py
python3 client/buyer_client.py
```

---

## API Reference

### Seller REST Endpoints (VM4 port 6002)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/seller/create_account` | Register new seller |
| POST | `/seller/login` | Login |
| POST | `/seller/logout` | Logout |
| POST | `/seller/restore_session` | Restore existing session |
| GET  | `/seller/get_rating` | Get seller rating |
| POST | `/seller/register_item` | List new item for sale |
| POST | `/seller/change_price` | Change item price |
| POST | `/seller/update_units` | Remove units from sale |
| GET  | `/seller/display_items` | View all seller's items |

### Buyer REST Endpoints (VM3 port 6001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/buyer/create_account` | Register new buyer |
| POST | `/buyer/login` | Login |
| POST | `/buyer/logout` | Logout |
| POST | `/buyer/restore_session` | Restore existing session |
| POST | `/buyer/search_items` | Search items by category/keywords |
| GET  | `/buyer/get_item` | Get item details |
| POST | `/buyer/add_to_cart` | Add item to cart |
| POST | `/buyer/remove_from_cart` | Remove item from cart |
| POST | `/buyer/save_cart` | Save cart across sessions |
| POST | `/buyer/clear_cart` | Clear cart |
| GET  | `/buyer/display_cart` | View cart |
| POST | `/buyer/make_purchase` | Purchase item (calls SOAP service) |
| POST | `/buyer/provide_feedback` | Rate item and seller |
| GET  | `/buyer/get_seller_rating` | View seller rating |
| GET  | `/buyer/get_purchases` | View purchase history |

---

## MakePurchase Flow

When a buyer makes a purchase:
1. Buyer client sends card info to buyer frontend (VM3) via REST
2. Buyer frontend calls the SOAP financial service (VM5) via HTTP
3. Financial service returns `true` (90% chance) or `false` (10% chance)
4. If approved, buyer frontend calls product DB (VM2) via gRPC to decrease stock
5. Buyer frontend calls customer DB (VM1) via gRPC to record purchase and update seller stats

---

## Regenerating Proto Stubs (Mac only — do not run on VMs)

If you modify the `.proto` files, regenerate the stubs on your Mac and commit them:

```bash
python -m grpc_tools.protoc -I proto/ --python_out=proto/ --grpc_python_out=proto/ proto/customer.proto
python -m grpc_tools.protoc -I proto/ --python_out=proto/ --grpc_python_out=proto/ proto/product.proto
git add -A && git commit -m "regenerate proto stubs" && git push
```

Then on all VMs: `git pull`

---

## Differences from PA1

| Component | PA1 | PA2 |
|-----------|-----|-----|
| Client ↔ Frontend | Raw TCP sockets + JSON | REST (HTTP/FastAPI) |
| Frontend ↔ Database | Raw TCP sockets + JSON | gRPC |
| MakePurchase | Not implemented | Implemented with SOAP payment |
| Deployment | Single machine or VMs | Separate cloud VMs required |

---

## SSH Setup (Mac → VMs)

### Step 1: Generate SSH key on Mac (if you don't have one)
```bash
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
# Press enter to accept defaults
# Key saved to ~/.ssh/id_rsa and ~/.ssh/id_rsa.pub
```

### Step 2: Copy your public key to each VM
```bash
# Replace USER and VM_IP with your actual values
ssh-copy-id student@10.224.76.209   # VM1
ssh-copy-id student@10.224.79.164   # VM2
ssh-copy-id student@10.224.78.247   # VM3
ssh-copy-id student@10.224.79.170   # VM4
ssh-copy-id student@10.224.77.206   # VM5
```
This copies your Mac's public key into `~/.ssh/authorized_keys` on each VM so you don't need a password.

### Step 3: Configure SSH shortcuts on Mac
Edit `~/.ssh/config` on your Mac and add:
```
Host vm1
    HostName 10.224.76.209
    User student

Host vm2
    HostName 10.224.79.164
    User student

Host vm3
    HostName 10.224.78.247
    User student

Host vm4
    HostName 10.224.79.170
    User student

Host vm5
    HostName 10.224.77.206
    User student
```

Now you can SSH into any VM with just:
```bash
ssh vm1
ssh vm3
# etc.
```

### Step 4: Connect via VS Code Remote SSH
1. Install the **Remote - SSH** extension in VS Code
2. Click the green `><` button in the bottom-left corner
3. Select **Connect to Host**
4. Type `vm1`, `vm3`, etc. (uses your SSH config shortcuts)
5. You now have a full editor, file explorer, and terminal on that VM


## Running Performance Tests

The performance test script measures response time and throughput for three scenarios:

```bash
python3 tests/performance_test.py
```

This will run:
- **Scenario 1**: 1 seller + 1 buyer (10 runs, 100 operations each)
- **Scenario 2**: 10 sellers + 10 buyers (10 runs, 50 operations each)
- **Scenario 3**: 100 sellers + 100 buyers (10 runs, 5 operations each)

Each client performs approximately 1000 operations total across all runs.

### Performance Metrics

- **Average Response Time**: Time from API call to response receipt
- **Throughput**: Operations completed per second

## Performance Report and Analysis

You can find the performance test results here: [performance_test.log](performance_log_20260220_214136.log)

### Analysis

## Performance Comparison: PA1 (TCP) vs PA2 (REST + gRPC)

### Results

| Scenario | Clients | PA1 Avg RT (ms) | PA2 Avg RT (ms) | RT Improvement | PA1 Throughput (ops/s) | PA2 Throughput (ops/s) | Throughput Improvement |
|----------|---------|-----------------|-----------------|----------------|----------------------|----------------------|----------------------|
| 1 | 1S + 1B | 35.10 | 48.64 | -38.6% (slower) | 50.99 | 34.75 | -31.9% (lower) |
| 2 | 10S + 10B | 117.65 | 79.78 | +32.2% (faster) | 145.41 | 184.01 | +26.5% (higher) |
| 3 | 100S + 100B | 864.96 | 640.93 | +25.9% (faster) | 152.77 | 164.92 | +8.0% (higher) |

### Analysis

**Scenario 1 (1 Seller + 1 Buyer):**
PA1 outperforms PA2 in the single-client case. This is expected because raw TCP sockets have minimal overhead, just a direct socket connection with JSON payloads. REST and gRPC introduce additional overhead from HTTP headers, protocol negotiation, protobuf serialization/deserialization, and the FastAPI framework layer. With only one client and no contention, this extra overhead is not offset by any concurrency benefits.

**Scenario 2 (10 Sellers + 10 Buyers):**
PA2 significantly outperforms PA1 with moderate concurrency. gRPC uses HTTP/2, which supports multiplexing; multiple requests can be sent over a single connection simultaneously without head-of-line blocking. FastAPI's async request handling allows the buyer and seller frontends to process multiple requests concurrently without blocking threads.

**Scenario 3 (100 Sellers + 100 Buyers):**
PA2 continues to outperform PA1 at high concurrency, with a 26% improvement in response time and 8% higher throughput. With 200 concurrent clients, PA1 struggles with connection management, opening, maintaining, and closing 200 individual TCP connections, which creates significant overhead. gRPC's persistent connections and HTTP/2 multiplexing handle this much more efficiently. However, the throughput improvement is smaller than Scenario 2 because both systems hit resource limits (database contention, CPU, SQLite locks) at this scale, which become the dominant bottleneck regardless of the communication protocol.

**Overall:** The move from raw TCP to REST + gRPC trades a small amount of single-client performance for significantly better scalability under concurrent load, which is the more realistic production scenario.
