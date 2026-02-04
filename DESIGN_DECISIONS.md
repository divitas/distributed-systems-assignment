# Design Decision Journey: From Scratch to Complete System

## Table of Contents
1. [Initial Requirements](#initial-requirements)
2. [Phase 1: Architectural Decisions](#phase-1-architectural-decisions)
3. [Phase 2: Component Design](#phase-2-component-design)
4. [Phase 3: Protocol & Communication](#phase-3-protocol--communication)
5. [Phase 4: Database Design](#phase-4-database-design)
6. [Phase 5: Implementation Decisions](#phase-5-implementation-decisions)
7. [Phase 6: Feature Additions (Session Restore)](#phase-6-feature-additions-session-restore)
8. [Lessons Learned](#lessons-learned)

---

## Initial Requirements

### Project Scope
Build a distributed **Online Marketplace System** where:
- Sellers can register items and manage inventory
- Buyers can search items and manage shopping carts
- System should be deployable on 5 separate VMs
- Must handle concurrent users
- Session state must persist across frontend crashes

### Key Constraints
1. **Distributed**: Must run on multiple machines
2. **Scalable**: Should handle increasing load
3. **Resilient**: Frontend crashes shouldn't lose user data
4. **Stateless Frontends**: No persistent state in frontend servers
5. **Educational**: Should demonstrate distributed systems principles

---

## Phase 1: Architectural Decisions

### Decision 1.1: Multi-Tier Architecture vs. Monolithic

**Options Considered:**
```
Option A: Monolith
[Client] → [All-in-One Server (Users, Products, Sessions, Carts)]

Option B: Multi-Tier ← CHOSEN
[Client] → [Frontend] → [Customer DB] + [Product DB]
```

**Why Multi-Tier?**

**Reasoning:**
- ✓ Separation of concerns (frontend handles requests, DB handles data)
- ✓ Independent scaling (can scale customer DB separately from product DB)
- ✓ Deployment flexibility (customers and products on different machines)
- ✓ Demonstrates distributed systems (core learning goal)
- ✓ Frontend statelessness = crash resilience

**Trade-off:** Slightly higher complexity, inter-service communication overhead

### Decision 1.2: Stateless vs. Stateful Frontend

**Options Considered:**
```
Option A: Stateful Frontend
[Client] → [Frontend with session cache] 
           ↓
        [DB]
Problems: Frontend crash = session loss

Option B: Stateless Frontend ← CHOSEN
[Client] → [Frontend (pass-through)]
           ↓
        [DB (holds state)]
Benefits: Frontend crash = no impact (session survives in DB)
```

**Why Stateless?**

**Code Example:**
```python
# STATELESS PATTERN (chosen)
def handle_request(request):
    session_id = request.get('session_id')
    
    # Validate with backend DB
    validation = db_request(
        CUSTOMER_DB,
        OP_VALIDATE_SESSION,
        {'session_id': session_id}
    )
    
    if validation['status'] == SUCCESS:
        # Proceed with operation
        return perform_operation()
    else:
        # Session invalid/expired
        return error_response()

# No session cache in frontend memory!
# If frontend crashes, DB still has session
```

**Reasoning:**
- ✓ Frontend crash doesn't lose user sessions
- ✓ Frontend can restart and resume exactly where it left off
- ✓ Allows unlimited frontend restarts
- ✓ Enables horizontal scaling (add more frontends anytime)

### Decision 1.3: Separation of Customer vs. Product Database

**Options Considered:**
```
Option A: Single Database
[All Users, Products, Sessions, Carts] in one DB
Problem: Bottleneck, hard to scale

Option B: Split by Functionality ← CHOSEN
[Customer DB]: Users, Sessions, Carts
[Product DB]: Items, Inventory, Search
Benefits: Independent scaling, clear separation
```

**Why Split?**

**Reasoning:**
- ✓ Different access patterns (users small, products large)
- ✓ Can optimize each separately
- ✓ Easier to scale (e.g., read replicas of product DB)
- ✓ Different data sizes (users grow slower than products)
- ✓ Clear domain boundaries

**Data Distribution:**
```
Customer DB:
├── sellers (few, relatively static)
├── buyers (growing, but moderate)
├── sessions (small, temporary)
└── shopping_carts (moderate size, high churn)

Product DB:
├── items (large, grows continuously)
├── item_feedback (large, continuous updates)
└── category_counters (small)
```

### Decision 1.4: Separate Frontend Servers for Sellers vs. Buyers

**Options Considered:**
```
Option A: Single Frontend
[Seller Client] → [Universal Frontend] ← [Buyer Client]
                       ↓
              [Customer DB + Product DB]

Option B: Separate Frontends ← CHOSEN
[Seller Client] → [Seller Frontend] → [DBs]
[Buyer Client] → [Buyer Frontend] → [DBs]
```

**Why Separate?**

**Reasoning:**
- ✓ Different API contracts (sellers vs. buyers)
- ✓ Independent scaling (can scale buyer frontend if more buyers than sellers)
- ✓ Easier to modify one without affecting other
- ✓ Can have different authentication/authorization for each
- ✓ Clearer code (no branching on user type)

**Design Trade-off:** Code duplication (both frontends similar) vs. clarity

**Our Choice:** Accepted code duplication for clarity (good for learning project)

---

## Phase 2: Component Design

### Decision 2.1: Communication Mechanism

**Options Considered:**
```
Option A: REST HTTP
Pros: Standard, well-known
Cons: Higher overhead, requires web framework, more complex

Option B: gRPC
Pros: Fast, modern, type-safe
Cons: Heavy dependency, learning curve, binary protocol

Option C: Raw TCP Sockets ← CHOSEN
Pros: Minimal dependencies, full control, educational
Cons: Manual protocol design, more error-prone
```

**Why Raw TCP?**

**Reasoning:**
- ✓ No external dependencies (pure Python stdlib)
- ✓ Direct control over communication
- ✓ Educational value (understand socket programming)
- ✓ Lightweight for learning project
- ✓ Maximum performance (no HTTP overhead)

### Decision 2.2: Message Protocol Format

**Options Considered:**
```
Option A: Binary (pickle, protobuf)
Pros: Compact, fast
Cons: Unreadable, security issues, version compatibility

Option B: JSON ← CHOSEN
Pros: Human-readable (for debugging), language-neutral, built-in
Cons: Slightly larger size, slightly slower parsing

Option C: CSV/Delimited
Pros: Simple
Cons: Hard to handle nested data, fragile
```

**Why JSON?**

**Reasoning:**
- ✓ Human-readable (can see what's transmitted)
- ✓ Built into Python (no dependencies)
- ✓ Easy to debug by looking at logs
- ✓ Supports nested structures (headers, data, etc.)
- ✓ Language-neutral (future frontend compatibility)

**Message Format Decision:**
```python
# Each message is a JSON object:
{
    "operation": "API_BUYER_LOGIN",
    "data": {
        "username": "alice",
        "password": "secret"
    },
    "session_id": null
}

# With delimiter for message framing:
# <JSON>\n###END###\n
```

### Decision 2.3: Message Framing Strategy

**Options Considered:**
```
Option A: Length-Prefixed
[4-byte length][message]
Pros: Efficient, binary-safe
Cons: Manual parsing, binary complexity

Option B: Delimiter-Based ← CHOSEN
[message]\n###END###\n
Pros: Simple, human-readable, easy to debug
Cons: Slightly less efficient, delimiter could appear in data

Option C: Line-Based
One message per line
Cons: Doesn't work for multi-line JSON
```

**Why Delimiter-Based?**

**Reasoning:**
- ✓ Simple to implement (string split)
- ✓ Easy to debug (clear message boundaries)
- ✓ Human-readable (can see messages in logs)
- ✓ Sufficient for our scale

**Implementation:**
```python
MESSAGE_DELIMITER = "\n###END###\n"

def receive_message(sock):
    accumulated_data = b''
    delimiter_bytes = MESSAGE_DELIMITER.encode('utf-8')
    
    while True:
        chunk = sock.recv(BUFFER_SIZE)
        accumulated_data += chunk
        
        # Check if complete message received
        if delimiter_bytes in accumulated_data:
            message_bytes = accumulated_data.split(delimiter_bytes)[0]
            return json.loads(message_bytes.decode('utf-8'))
```

---

## Phase 3: Protocol & Communication

### Decision 3.1: Request-Response vs. Publish-Subscribe

**Options Considered:**
```
Option A: Request-Response (Synchronous)
Client sends request → Server processes → Client waits for response
Pros: Simple, easy to reason about, clear error handling
Cons: Client must wait, potential blocking

Option B: Pub-Sub (Asynchronous)
Client publishes event → Server processes in background
Pros: Non-blocking, better for many subscribers
Cons: Complex error handling, hard to correlate requests/responses

Option C: Hybrid (Request-Response) ← CHOSEN
Synchronous for most operations, async for cart updates
```

**Why Request-Response?**

**Reasoning:**
- ✓ Simpler to implement and debug
- ✓ Client needs immediate feedback (success/failure)
- ✓ Natural for CLI interface (wait for response before showing menu)
- ✓ Easier error handling (response includes status)
- ✓ Good for educational purposes

**Pattern:**
```python
# Client
response = send_request(
    API_BUYER_LOGIN,
    {'username': 'alice', 'password': 'secret'}
)

if response['status'] == STATUS_SUCCESS:
    session_id = response['data']['session_id']
    # Continue
else:
    # Handle error
    print(f"Login failed: {response['message']}")
```

### Decision 3.2: Session ID vs. Username/Password per Request

**Options Considered:**
```
Option A: Username/Password in Every Request
Request: {"operation": "...", "username": "alice", "password": "secret"}
Cons: Network overhead, security risk (credentials in every message)

Option B: Session ID Token ← CHOSEN
After login:
  Response: {"session_id": "uuid-12345", ...}
Subsequent:
  Request: {"operation": "...", "session_id": "uuid-12345"}
Pros: Credentials sent only once, session can expire
```

**Why Session Tokens?**

**Reasoning:**
- ✓ Credentials transmitted only once (at login)
- ✓ Supports session expiration (5-minute timeout)
- ✓ Server-side invalidation possible (logout)
- ✓ Less network traffic (UUID < password)
- ✓ Industry standard pattern

**Implementation Decision: UUID vs. Sequential**
```python
# Chosen: UUID (true randomness)
import uuid
def generate_session_id():
    return str(uuid.uuid4())  # "a1b2c3d4-e5f6-..."

# Not chosen: Sequential (predictable)
# session_id = str(last_session + 1)  # 12345, 12346...
# Risk: attackers can guess other users' sessions
```

**Why UUID?**
- ✓ Unpredictable (can't guess other sessions)
- ✓ Extremely low collision probability
- ✓ Standard security practice

---

## Phase 4: Database Design

### Decision 4.1: SQLite vs. Other Options

**Options Considered:**
```
Option A: PostgreSQL / MySQL
Pros: Production-ready, powerful, distributed support
Cons: Requires server setup, dependencies, overkill for learning

Option B: In-Memory (Python dict)
Pros: Fast, simple
Cons: Lost on crash, no persistence

Option C: SQLite ← CHOSEN
Pros: File-based, no setup, ACID, thread-safe, persistent
Cons: Single-writer limitation (acceptable for learning)
```

**Why SQLite?**

**Reasoning:**
- ✓ Zero setup (just create .db file)
- ✓ No dependencies
- ✓ Built into Python
- ✓ ACID transactions
- ✓ Thread-safe (can handle concurrent requests)
- ✓ File-based (persistent across crashes)

### Decision 4.2: Schema Organization

**Single DB File vs. Multiple Files:**
```
Option A: Single customer.db + single product.db ← CHOSEN
Pros: Clear separation, matches service boundary
Cons: Two files to manage

Option B: Monolithic database.db
Cons: Violates separation of concerns
```

**Key Tables Decision:**

**For Customer DB - Why these tables?**
```sql
CREATE TABLE sellers (
    seller_id INT PRIMARY KEY,
    username TEXT UNIQUE,  -- Why UNIQUE? Prevent duplicate accounts
    password TEXT,
    seller_name TEXT,      -- Why separate from username? Allow non-unique display names
    thumbs_up INT,         -- Why store rating? Fast access without aggregation
    thumbs_down INT,
    items_sold INT,        -- Why counter? Performance tracking
    created_at TIMESTAMP
);
```

**Reasoning for each column:**
- `seller_id`: Primary key - unique identifier, used in foreign keys
- `username UNIQUE`: Constraint - prevent duplicate logins
- `password`: Plaintext for now (simplified security for learning)
- `seller_name`: Separate field - allows non-unique display names
- `thumbs_up/down`: Denormalized - fast rating calculation without joins
- `items_sold`: Counter - track performance metrics
- `created_at`: Audit trail - know when user registered

### Decision 4.3: Shopping Cart Architecture

**Options Considered:**
```
Option A: Single Cart per Buyer (Ever)
Problem: Can't have multiple sessions simultaneously

Option B: Active Cart per Session (Lost on Logout) ← Initial
Problem: Users lose unsaved carts

Option C: Dual Cart System (Active + Saved) ← FINAL CHOSEN
└─ Active Cart: Per-session, cleared on logout
└─ Saved Cart: Per-buyer, persists across logouts/crashes
Benefits: Best of both worlds
```

**Dual Cart Implementation:**
```python
# Table structure:
CREATE TABLE shopping_carts (        -- Active (per-session)
    id INT,
    session_id TEXT,                 -- Links to current session
    buyer_id INT,
    item_id TEXT,
    quantity INT,
    UNIQUE(session_id, item_id)      -- One entry per item per session
);

CREATE TABLE saved_carts (           -- Saved (per-buyer)
    id INT,
    buyer_id INT,                    -- Links to buyer (not session)
    item_id TEXT,
    quantity INT,
    UNIQUE(buyer_id, item_id)        -- One entry per item per buyer
);

# Workflow:
1. Buyer logs in
   → Load from saved_carts into active shopping_carts for this session

2. Buyer adds/removes items
   → Modify shopping_carts (active only)

3. Buyer clicks "Save Cart"
   → Copy shopping_carts to saved_carts

4. Buyer logs out
   → Delete from shopping_carts (but saved_carts persists!)

5. Buyer logs in again
   → saved_carts still there! Load it again!
```

**Why This Design?**

**Reasoning:**
- ✓ Supports typical user expectation (save things for later)
- ✓ Active cart can be session-specific (multiple tabs/sessions)
- ✓ Saved cart persists across frontend crashes
- ✓ Clear separation of concerns (session vs. user data)

### Decision 4.4: Item ID Generation Strategy

**Options Considered:**
```
Option A: Global Sequential (1, 2, 3...)
Cons: Hard to infer category from ID

Option B: Category-Prefixed ← CHOSEN
Format: "category-sequence"
Example: "1-42" = Electronics category, 42nd item
Pros: ID encodes category, useful for search, consistent with category indices
```

**Implementation:**
```python
# category_counters table keeps track per category:
CREATE TABLE category_counters (
    category INT PRIMARY KEY,
    last_id INT
);

# When registering item in category 1 (Electronics):
1. SELECT last_id FROM category_counters WHERE category = 1
   → Returns 41
2. Increment: UPDATE category_counters SET last_id = 42 WHERE category = 1
3. Generate ID: "1-42"
4. Insert item with this ID
```

**Why This Design?**

**Reasoning:**
- ✓ ID encodes category (can parse to know category)
- ✓ Sequential within category (inventory easier)
- ✓ Category-based inventory management
- ✓ Intuitive naming scheme

### Decision 4.5: Indexes for Performance

**Which columns to index?**
```sql
-- Chosen indexes:
CREATE INDEX idx_seller_sessions_seller ON seller_sessions(seller_id);
CREATE INDEX idx_buyer_sessions_buyer ON buyer_sessions(buyer_id);
CREATE INDEX idx_shopping_carts_session ON shopping_carts(session_id);
CREATE INDEX idx_shopping_carts_buyer ON shopping_carts(buyer_id);
CREATE INDEX idx_saved_carts_buyer ON saved_carts(buyer_id);
CREATE INDEX idx_purchase_history_buyer ON purchase_history(buyer_id);
```

**Why These Indexes?**

**Reasoning:**
- ✓ Foreign key columns (quick joins)
- ✓ Frequently searched columns (session lookup, buyer lookup)
- ✓ Avoid full table scans for common queries
- ✓ Index on WHERE clause columns

---

## Phase 5: Implementation Decisions

### Decision 5.1: Threading Model

**Options Considered:**
```
Option A: Async/Await (asyncio)
Pros: Modern, efficient, single-threaded
Cons: Learning curve, callback complexity

Option B: Threads ← CHOSEN
Pros: Straightforward, simple to understand, built-in
Cons: Global Interpreter Lock (GIL) limits true parallelism

Option C: Processes
Pros: True parallelism
Cons: Heavy, inter-process communication complex
```

**Why Threads?**

**Reasoning:**
- ✓ Simple to implement and understand
- ✓ Good for I/O-bound operations (socket communication)
- ✓ Built-in Python threading module
- ✓ Educational (easy to see threading patterns)
- ✓ GIL acceptable (I/O waits release GIL anyway)

**Pattern Used:**
```python
def run_server(self):
    """Main server loop"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((self.host, self.port))
    server_socket.listen(config.BACKLOG)
    
    while self.running:
        client_socket, addr = server_socket.accept()
        
        # Handle each client in a separate thread
        thread = threading.Thread(
            target=self.handle_client,
            args=(client_socket, addr)
        )
        thread.daemon = True
        thread.start()
```

### Decision 5.2: Error Handling Strategy

**Pattern Chosen:**
```python
def _create_seller(self, data):
    username = data.get('username')
    password = data.get('password')
    seller_name = data.get('seller_name')
    
    conn = self._get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''INSERT INTO sellers ...''', (username, password, seller_name))
        seller_id = cursor.lastrowid
        conn.commit()
        
        return Protocol.create_response(
            STATUS_SUCCESS,
            data={'seller_id': seller_id},
            message="Seller account created successfully"
        )
    
    except sqlite3.IntegrityError:  # Handle specific errors
        return Protocol.create_response(
            STATUS_DUPLICATE,
            message="Username already exists"
        )
    
    except Exception as e:
        return Protocol.create_response(
            STATUS_ERROR,
            message=str(e)
        )
    
    finally:
        conn.close()  # Always clean up
```

**Why This Approach?**

**Reasoning:**
- ✓ Specific exception handling (sqlite3.IntegrityError)
- ✓ Always cleanup (finally block)
- ✓ Return structured error response
- ✓ No silent failures

### Decision 5.3: Database Connection Handling

**Options Considered:**
```
Option A: Single Global Connection
Cons: Not thread-safe, one thread blocks all

Option B: Connection Pool
Pros: Reuse connections, better performance
Cons: Complexity, might be overkill

Option C: Per-Request Connection ← CHOSEN
Pros: Thread-safe, simple, no state
Cons: Overhead of creating connections
```

**Why Per-Request?**

**Reasoning:**
- ✓ SQLite handles concurrent access better with separate connections
- ✓ Each thread gets its own connection (no locking needed)
- ✓ Simple to understand and implement
- ✓ Connection setup is fast for local SQLite

**Implementation:**
```python
def _get_connection(self):
    """Get a thread-safe database connection"""
    return sqlite3.connect(self.db_path, check_same_thread=False)

# Used in every operation:
def _create_seller(self, data):
    conn = self._get_connection()  # Create fresh connection
    try:
        # ... use connection
        conn.commit()
    finally:
        conn.close()  # Always close
```

### Decision 5.4: Session Timeout Implementation

**Options Considered:**
```
Option A: Lazy Cleanup (Check on Access)
Problem: User doesn't know session expired until next operation

Option B: Background Cleanup ← CHOSEN
Separate thread periodically removes expired sessions
Pros: Sessions cleaned proactively, consistent behavior
```

**Implementation:**
```python
def __init__(self):
    # ... other initialization
    
    # Start background cleanup thread
    self.cleanup_thread = threading.Thread(
        target=self._session_cleanup_worker,
        daemon=True
    )
    self.cleanup_thread.start()

def _session_cleanup_worker(self):
    """Background thread runs periodically"""
    while True:
        time.sleep(config.SESSION_CHECK_INTERVAL)  # 60 seconds
        try:
            self._cleanup_expired_sessions()
        except Exception as e:
            print(f"Error in session cleanup: {e}")

def _cleanup_expired_sessions(self):
    """Remove sessions inactive > 5 minutes"""
    current_time = get_current_timestamp()
    timeout = config.SESSION_TIMEOUT  # 300 seconds
    cutoff_time = current_time - timeout
    
    cursor.execute('''
        DELETE FROM seller_sessions 
        WHERE last_activity < ?
    ''', (cutoff_time,))
    # ... also clean buyer_sessions and carts
```

**Configuration Choices:**
```python
SESSION_TIMEOUT = 300          # 5 minutes (user-friendly)
SESSION_CHECK_INTERVAL = 60    # Clean every minute (not too often)
```

**Why These Values?**

**Reasoning:**
- 5 minutes: Reasonable for interactive CLI (enough time for operations)
- 60 seconds: Cleanup runs periodically but not too often (low overhead)

### Decision 5.5: Search Algorithm

**Options Considered:**
```
Option A: Simple Substring Match
Problem: No ranking, poor quality results

Option B: Relevance Scoring ← CHOSEN
Exact match: 10 points
Partial match: 5 points
In keywords: 3 points
Pros: Better result ranking, customizable
```

**Implementation:**
```python
def _search_items(self, data):
    category = data.get('category')
    keywords = data.get('keywords', [])
    
    # Fetch all items in category
    items = fetch_items_by_category(category)
    
    # Score each item
    for item in items:
        score = 0
        for keyword in keywords:
            keyword_lower = keyword.lower()
            item_name_lower = item['name'].lower()
            
            if item_name_lower == keyword_lower:
                score += 10  # Exact match in name
            elif keyword_lower in item_name_lower:
                score += 5   # Partial match in name
            elif keyword_lower in item['keywords']:
                score += 3   # In keywords field
        
        item['score'] = score
    
    # Sort by score (highest first)
    results = sorted(items, key=lambda x: x['score'], reverse=True)
    return results[:MAX_SEARCH_RESULTS]
```

**Why This Scoring?**

**Reasoning:**
- ✓ Exact matches prioritized (if searching "laptop", prefer "laptop" over "laptop stand")
- ✓ Partial matches useful (search "gaming" finds "Gaming Laptop")
- ✓ Keywords useful (seller-provided keywords matter)
- ✓ Tunable (can adjust points later)

---

## Phase 6: Feature Additions (Session Restore)

### Decision 6.1: Should Sessions Be Persistent Across Frontend Restarts?

**Initial Design Problem:**
```
Scenario: Frontend server crashes
Client A: Connected to old frontend (now dead)
Client needs to:
  1. Detect frontend crash (timeout)
  2. Reconnect to potentially different frontend
  3. Resume work
  
Initial approach: Must login again (session lost)
Problem: Poor user experience, data in cart lost (if not saved)
```

**Solution: Session Restoration Feature**

**Architecture Decision:**
```
Before: [Client] --login--> [Frontend] --create session--> [DB]
                             ^
                             └─ If frontend crashes, session orphaned

After: [Client] --login--> [Frontend] --create session--> [DB]
                                                          ↑
                                                   (session lives in DB)
       
       If frontend dies, client can:
       [Client] --restore_session(id)--> [New Frontend] --lookup--> [DB]
                                                        ↓
                                              (session still active!)
```

### Decision 6.2: How to Store and Restore Session?

**Options Considered:**
```
Option A: Client-Side Session Storage
Client saves: session_id in memory
Problem: Lost when client exits/crashes

Option B: Client-Side File Storage
Client saves: session_id in ~/.marketplace_session
Pros: Survives client restart
Cons: Adds complexity, user sees details

Option C: DB-Only (Current Implementation) ← CHOSEN
Session lives in DB, client stores in memory only
Pros: Simple, stateless, works fine for learning
Note: Can add option B later

Option D: Server-Side Session List
Frontend maintains active sessions in memory
Problem: Lost when frontend crashes (defeats purpose)
```

### Implementation of Session Restoration

**API Definition:**
```python
# New operation codes in constants.py:
OP_RESTORE_SESSION_BUYER = 'restore_session_buyer'
OP_RESTORE_SESSION_SELLER = 'restore_session_seller'
API_BUYER_RESTORE_SESSION = 'buyer_restore_session'
API_SELLER_RESTORE_SESSION = 'seller_restore_session'
```

**Database Layer (customer_db.py):**
```python
def _restore_session_buyer(self, data):
    """Restore a previous buyer session"""
    session_id = data.get('session_id')
    
    conn = self._get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if session exists and not expired
        current_time = get_current_timestamp()
        timeout = config.SESSION_TIMEOUT
        cutoff_time = current_time - timeout
        
        cursor.execute('''
            SELECT buyer_id FROM buyer_sessions
            WHERE session_id = ? AND last_activity > ?
        ''', (session_id, cutoff_time))
        
        result = cursor.fetchone()
        
        if result:
            buyer_id = result[0]
            
            # Update activity to prevent immediate timeout
            cursor.execute('''
                UPDATE buyer_sessions SET last_activity = ?
                WHERE session_id = ?
            ''', (current_time, session_id))
            
            # Load buyer info
            cursor.execute('''
                SELECT buyer_id, username, buyer_name
                FROM buyers WHERE buyer_id = ?
            ''', (buyer_id,))
            
            buyer = cursor.fetchone()
            
            # Load saved cart into active cart for this session
            cursor.execute('''
                INSERT OR REPLACE INTO shopping_carts (session_id, buyer_id, item_id, quantity)
                SELECT ?, buyer_id, item_id, quantity FROM saved_carts
                WHERE buyer_id = ?
            ''', (session_id, buyer_id))
            
            conn.commit()
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={
                    'buyer_id': buyer_id,
                    'buyer_name': buyer[2]
                },
                message="Session restored"
            )
        else:
            return Protocol.create_response(
                STATUS_ERROR,
                message="Session expired or invalid"
            )
    finally:
        conn.close()
```

**Frontend Layer (buyer_server.py):**
```python
def _restore_session(self, session_id):  # NEW
    """Restore an existing session using session_id"""
    if not session_id:
        return Protocol.create_response(
            STATUS_INVALID_REQUEST,
            message="Session ID is required"
        )
    
    # Forward to customer DB
    request = Protocol.create_request(
        OP_RESTORE_SESSION_BUYER,
        data={'session_id': session_id}
    )
    
    return self._db_request(
        self.customer_db_host,
        self.customer_db_port,
        request
    )

def handle_request(self, request):
    operation = request.get('operation')
    
    # Handle restore without session validation
    if operation == API_BUYER_RESTORE_SESSION:
        session_id = request.get('session_id')
        return self._restore_session(session_id)
    
    # ... rest of operations require session validation
```

**Client Layer (buyer_client.py):**
```python
def restore_session(self):
    """Try to restore existing session using session_id"""
    if not self.session_id:
        return False
    
    response = self.send_request(
        API_BUYER_RESTORE_SESSION,
        {'session_id': self.session_id}
    )
    
    if response and response['status'] == STATUS_SUCCESS:
        self.buyer_id = response['data']['buyer_id']
        self.buyer_name = response['data']['buyer_name']
        print(f"\n✓ Session restored. Welcome back, {self.buyer_name}!")
        return True
    else:
        # Session invalid/expired, clear it
        self.session_id = None
        return False
```

**User Experience:**
```
Session 1:
python3 client/buyer_client.py
→ Login as alice
→ Add items to cart
→ ... [Disconnect/Exit] ...
Session ID remembered in memory: "abc123def456"

Session 2 (Client Restart):
python3 client/buyer_client.py
→ Menu offers: "Restore Session" option
→ User selects "Restore Session"
→ Cart items are still there!
→ Backend session still active (< 5 minutes)
```

**Design Decisions in Restoration:**

1. **Why update last_activity?**
   - Prevents session from timing out while user is using restored session
   - Restarts the 5-minute timer

2. **Why load saved_cart into active_cart?**
   - User expects to see their saved items
   - Active cart needs to exist for add/remove operations
   - Automatic on restore

3. **Why check cutoff_time?**
   - Sessions expire after 5 minutes
   - Old session IDs shouldn't work after timeout
   - Prevents session fixation attacks

---

## Lessons Learned

### What Went Right ✓

1. **Stateless Frontend Architecture**
   - Proved resilient (frontend crashes don't lose data)
   - Allowed easy restarts
   - Enabled scalability

2. **Clear Separation of Concerns**
   - Customer DB for user/session logic
   - Product DB for inventory
   - Frontend as thin pass-through
   - Easy to understand and modify

3. **Simple Protocol**
   - JSON + delimiter worked well
   - Human-readable for debugging
   - Easy to implement

4. **Thread-Safe Design**
   - Per-request connections prevented deadlocks
   - Background cleanup thread handles expiration
   - No shared mutable state in frontend

5. **Dual Cart System**
   - Flexible (save when ready, lose when not)
   - Intuitive to users
   - Good balance between stateless and user expectations

### What Could Be Better ⚠️

1. **Security**
   - Plaintext passwords (should use bcrypt)
   - No encryption over network
   - No input validation/sanitization

2. **Performance**
   - No connection pooling (creates new connection per request)
   - Full table scan for search (could use full-text search index)
   - SQLite write serialization (bottleneck at high scale)

3. **Error Handling**
   - Limited transaction rollback
   - Cascading failures if one DB down
   - No circuit breaker pattern

4. **Testing**
   - Only performance tests (no unit tests)
   - No integration tests
   - No failure scenario tests

5. **Observability**
   - Limited logging
   - No metrics collection
   - Hard to debug issues in production

### Key Takeaways

**Architectural Principles:**
- Stateless frontends enable resilience
- Clear separation simplifies development
- Simple protocols aid debugging
- Thread safety prevents subtle bugs

**Performance Considerations:**
- Connection pooling matters at scale
- Indexing is critical for search
- Database choice affects architecture (SQLite has limits)

**Feature Addition Process:**
- Session restoration required changes at 3 layers (DB, frontend, client)
- Each layer needs different logic (validation, forwarding, UI)
- Backward compatibility matters (old sessions still work)

**Design Trade-offs:**
- Simplicity vs. Performance (chose simplicity for learning)
- Stateless vs. Stateful (chose stateless for resilience)
- SQLite vs. Production DB (chose SQLite for zero setup)

---

## Timeline of Design Decisions

### Phase 1: Planning (Day 1)
- Multi-tier architecture chosen
- Stateless frontends decided
- Separate DBs for customers vs. products
- Separate frontends for sellers vs. buyers

### Phase 2: Foundation (Day 2-3)
- Raw TCP sockets + JSON protocol
- Message framing with delimiters
- Request-response pattern
- Session ID tokens

### Phase 3: Database (Day 4-5)
- SQLite chosen
- Schema design (tables, relationships, indexes)
- Dual cart system decided
- Item ID generation strategy

### Phase 4: Implementation (Day 6-10)
- Threading model (per-request)
- Connection handling
- Error handling patterns
- Session timeout implementation
- Search algorithm with scoring

### Phase 5: Testing & Performance (Day 11-12)
- Performance test framework
- 3 concurrent load scenarios
- Results analysis

### Phase 6: Feature Enhancement (Day 13+)
- Session restoration feature
- Changes across all 3 layers
- User experience improvement

### Final: Documentation (Ongoing)
- Architecture diagrams
- API documentation
- Deployment guides
- Code review documentation

---

## Conclusion

This project demonstrates how to approach building a distributed system from scratch:

1. **Start with requirements** and constraints
2. **Make architectural decisions** (multi-tier, stateless, etc.)
3. **Design the protocol** (JSON + TCP)
4. **Build the database** schema
5. **Implement components** with proper patterns
6. **Add features** thoughtfully (session restoration)
7. **Test and document** thoroughly

Each decision was made to balance:
- **Simplicity** (for learning)
- **Scalability** (support many users)
- **Resilience** (survive failures)
- **Clarity** (easy to understand)

The architecture successfully demonstrates distributed systems principles while remaining simple enough to understand completely.

