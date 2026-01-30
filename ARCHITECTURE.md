# System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DISTRIBUTED MARKETPLACE                         │
│                           Architecture Overview                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│    ┌──────────────────┐                    ┌──────────────────┐         │
│    │  Seller Client   │                    │  Buyer Client    │         │
│    │   (CLI)          │                    │   (CLI)          │         │
│    │                  │                    │                  │         │
│    │  - Create Acct   │                    │  - Create Acct   │         │
│    │  - Login/Logout  │                    │  - Login/Logout  │         │
│    │  - Register Item │                    │  - Search Items  │         │
│    │  - Update Price  │                    │  - Shopping Cart │         │
│    │  - View Items    │                    │  - Feedback      │         │
│    └────────┬─────────┘                    └─────────┬────────┘         │
│             │                                        │                  │
│             │ TCP/IP                    TCP/IP       │                  │
└─────────────┼────────────────────────────────────────┼──────────────────┘
              │                                        │
              │                                        │
┌─────────────▼────────────────────────────────────────▼──────────────────┐
│                           FRONTEND LAYER                                 │
│                         (Stateless Servers)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│    ┌──────────────────┐                    ┌──────────────────┐         │
│    │ Seller Frontend  │                    │ Buyer Frontend   │         │
│    │   Server         │                    │   Server         │         │
│    │ (Port 6002)      │                    │ (Port 6001)      │         │
│    │                  │                    │                  │         │
│    │ - Session Valid. │                    │ - Session Valid. │         │
│    │ - Input Valid.   │                    │ - Input Valid.   │         │
│    │ - Request Routing│                    │ - Request Routing│         │
│    │ - No State       │                    │ - No State       │         │
│    └────────┬─────────┘                    └─────────┬────────┘         │
│             │                                        │                  │
│             │ TCP/IP                    TCP/IP       │                  │
│             │                                        │                  │
└─────────────┼────────────────────────────────────────┼──────────────────┘
              │                                        │
              │                                        │
              ├────────────┬───────────────────────────┤
              │            │                           │
┌─────────────▼────────┐   │   ┌───────────────────────▼──────────────────┐
│  BACKEND LAYER       │   │   │  BACKEND LAYER                           │
│  (Database Servers)  │   │   │  (Database Servers)                      │
├──────────────────────┤   │   ├──────────────────────────────────────────┤
│                      │   │   │                                          │
│ Customer Database    │   │   │  Product Database                        │
│   (Port 5001)        │   │   │    (Port 5002)                           │
│                      │   │   │                                          │
│ ┌────────────────┐   │   │   │  ┌────────────────┐                     │
│ │ SQLite DB      │   │   │   │  │ SQLite DB      │                     │
│ │                │   │   │   │  │                │                     │
│ │ Tables:        │   │   │   │  │ Tables:        │                     │
│ │ - sellers      │   │   │   │  │ - items        │                     │
│ │ - buyers       │   │   │   │  │ - category_ctr │                     │
│ │ - seller_sess. │   │   │   │  │                │                     │
│ │ - buyer_sess.  │   │   │   │  │ Manages:       │                     │
│ │ - shop_carts   │   │   │   │  │ - Item listing │                     │
│ │ - saved_carts  │   │   │   │  │ - Inventory    │                     │
│ │ - purchase_hist│   │   │   │  │ - Search       │                     │
│ │                │   │   │   │  │ - Feedback     │                     │
│ │ Manages:       │   │   │   │  └────────────────┘                     │
│ │ - Accounts     │   │   │   │                                          │
│ │ - Sessions     │   │   │   │                                          │
│ │ - Carts        │   │   │   │                                          │
│ │ - Ratings      │   │   │   │                                          │
│ └────────────────┘   │   │   │                                          │
│                      │   │   │                                          │
└──────────────────────┘   │   └──────────────────────────────────────────┘
                           │
                           │
┌──────────────────────────┴───────────────────────────────────────────────┐
│                         DATA FLOW EXAMPLES                                │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  1. SELLER REGISTERS ITEM:                                                │
│     Seller Client → Seller Frontend → Product DB (create item)            │
│                                    → Customer DB (validate session)       │
│                                                                            │
│  2. BUYER SEARCHES ITEMS:                                                 │
│     Buyer Client → Buyer Frontend → Customer DB (validate session)        │
│                                  → Product DB (search items)              │
│                                                                            │
│  3. BUYER ADDS TO CART:                                                   │
│     Buyer Client → Buyer Frontend → Product DB (check availability)       │
│                                  → Customer DB (add to cart)              │
│                                                                            │
│  4. BUYER SAVES CART:                                                     │
│     Buyer Client → Buyer Frontend → Customer DB (save cart + sync         │
│                                      all sessions for this buyer)         │
│                                                                            │
└───────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                      KEY ARCHITECTURAL FEATURES                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ✓ STATELESS FRONTENDS                                                   │
│    - No persistent state stored in frontend servers                      │
│    - All state persisted in backend databases                            │
│    - Frontend can crash/restart without losing user state                │
│    - Enables horizontal scaling                                          │
│                                                                           │
│  ✓ SESSION MANAGEMENT                                                    │
│    - Sessions identified by UUID                                         │
│    - Session state persists across TCP reconnects                        │
│    - Automatic timeout after 5 minutes of inactivity                     │
│    - Background cleanup thread removes expired sessions                  │
│                                                                           │
│  ✓ SHOPPING CART PERSISTENCE                                             │
│    - Active cart: Per-session (shopping_carts table)                     │
│    - Saved cart: Per-user (saved_carts table)                            │
│    - Login loads saved cart into active cart                             │
│    - Save cart syncs across all buyer's sessions                         │
│                                                                           │
│  ✓ THREAD-SAFE OPERATIONS                                                │
│    - Multi-threaded request handling                                     │
│    - Thread-safe database connections                                    │
│    - Proper locking for concurrent operations                            │
│                                                                           │
│  ✓ DISTRIBUTED DEPLOYMENT                                                │
│    - All components run as separate processes                            │
│    - Can be deployed across different machines/VMs                       │
│    - Communication via TCP/IP sockets                                    │
│    - No shared memory or local file dependencies                         │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                     DEPLOYMENT ON 5 VMs                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   VM1: Customer Database (IP: 10.0.0.1)                                  │
│   ├── database/customer_db.py                                            │
│   └── data/customer.db                                                   │
│                                                                           │
│   VM2: Product Database (IP: 10.0.0.2)                                   │
│   ├── database/product_db.py                                             │
│   └── data/product.db                                                    │
│                                                                           │
│   VM3: Buyer Frontend (IP: 10.0.0.3)                                     │
│   └── frontend/buyer_server.py                                           │
│                                                                           │
│   VM4: Seller Frontend (IP: 10.0.0.4)                                    │
│   └── frontend/seller_server.py                                          │
│                                                                           │
│   VM5: Test Clients (IP: 10.0.0.5)                                       │
│   ├── client/buyer_client.py                                             │
│   ├── client/seller_client.py                                            │
│   └── tests/performance_test.py                                          │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                      MESSAGE PROTOCOL                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Format: JSON with delimiter                                             │
│                                                                           │
│  Request:                                                                 │
│  {                                                                        │
│    "operation": "API_OPERATION_CODE",                                    │
│    "session_id": "uuid-string",                                          │
│    "data": {                                                             │
│      "key": "value",                                                     │
│      ...                                                                 │
│    }                                                                     │
│  }\n###END###\n                                                          │
│                                                                           │
│  Response:                                                                │
│  {                                                                        │
│    "status": "SUCCESS|ERROR|...",                                        │
│    "message": "descriptive message",                                     │
│    "data": {                                                             │
│      "key": "value",                                                     │
│      ...                                                                 │
│    }                                                                     │
│  }\n###END###\n                                                          │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Performance Characteristics

### Scalability Profile

```
Throughput vs. Concurrent Clients

   ^
   │                                  ╱─────────
   │                              ╱───
   │                          ╱───
Ops│                      ╱───
/sec│                  ╱───
   │              ╱───
   │          ╱───
   │      ╱───
   │  ╱───
   └─────────────────────────────────────────> Clients
   1        10        20        50       100

Legend:
- Linear scaling: 1-10 clients
- Sublinear scaling: 10-50 clients  
- Saturation: 50-100 clients (SQLite write limit)
```

### Response Time Distribution

```
Response Time vs. Load

   ^
   │                                      ┌───┐
   │                                  ┌───┤   │
   │                              ┌───┤   │   │
 ms│                          ┌───┤   │   │   │
   │                      ┌───┤   │   │   │   │
   │                  ┌───┤   │   │   │   │   │
   │              ┌───┤   │   │   │   │   │   │
   │          ┌───┤   │   │   │   │   │   │   │
   │      ┌───┤   │   │   │   │   │   │   │   │
   └──────┴───┴───┴───┴───┴───┴───┴───┴───┴───┘
         1    10   20   30   40   50   75  100  Clients

Legend:
- Light load (1-10): Network RTT dominant
- Medium load (10-50): Thread contention emerges
- Heavy load (50-100): Resource saturation
```

## Designed for Future Enhancements

The architecture is designed to easily support:

1. **gRPC/SOAP**: Replace TCP protocol module
2. **Raft Consensus**: Add to database layer for replication
3. **Load Balancing**: Multiple frontend instances
4. **Caching**: Redis layer between frontend and database
5. **Database Scaling**: PostgreSQL with read replicas
6. **Monitoring**: Add metrics collection at each layer
