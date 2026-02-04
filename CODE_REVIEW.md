# Comprehensive Code Review & Architecture Guide

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Analysis](#architecture-analysis)
3. [Code Structure Review](#code-structure-review)
4. [Module-by-Module Analysis](#module-by-module-analysis)
5. [Key Features](#key-features)
6. [Code Quality Review](#code-quality-review)
7. [Potential Issues & Improvements](#potential-issues--improvements)
8. [Getting Started Guide](#getting-started-guide)

---

## System Overview

This is an **Online Marketplace distributed system** built with Python, implementing a multi-tier architecture with stateless frontend servers and separate database backends.

### Key Characteristics
- **Architecture**: Distributed 4-tier system (2 DBs + 2 frontend servers + clients)
- **Communication**: TCP sockets with JSON protocol
- **Database**: SQLite with thread-safe connections
- **Session Management**: Timeout-based with optional restoration
- **Shopping System**: Dual-cart architecture (active + saved carts)

---

## Architecture Analysis

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTS                               │
│          ┌─────────────┐              ┌─────────────┐       │
│          │ Buyer CLI   │              │ Seller CLI  │       │
│          └─────────────┘              └─────────────┘       │
│                │                             │                │
└────────────────┼─────────────────────────────┼────────────────┘
                 │                             │
                 ▼                             ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  BUYER FRONTEND SERVER   │    │ SELLER FRONTEND SERVER   │
│  (Stateless)             │    │ (Stateless)              │
│  Port: 6001              │    │ Port: 6002               │
└──────────────────────────┘    └──────────────────────────┘
         │                              │
         │                              │
    ┌────┴──────────────────────────────┴────┐
    │                                         │
    ▼                                         ▼
┌─────────────────────────────┐    ┌──────────────────────┐
│ CUSTOMER DATABASE SERVER    │    │PRODUCT DATABASE      │
│ - Sellers                   │    │ - Items              │
│ - Buyers                    │    │ - Inventory          │
│ - Sessions                  │    │ - Search/Feedback    │
│ - Shopping Carts            │    │                      │
│ Port: 5001                  │    │ Port: 5002           │
└─────────────────────────────┘    └──────────────────────┘
```

### Communication Protocol

**Message Format:**
```json
{
  "operation": "API_BUYER_LOGIN",
  "data": {
    "username": "john",
    "password": "secret123"
  },
  "session_id": "uuid-here"
}
```

**Response Format:**
```json
{
  "status": "SUCCESS",
  "message": "Login successful",
  "data": {
    "session_id": "uuid-here",
    "buyer_id": 1,
    "buyer_name": "John Doe"
  }
}
```

**Message Delimiter:** `\n###END###\n` (ensures complete message reception)

---

## Code Structure Review

### Project Layout
```
online-marketplace/
├── config.py                      # Centralized configuration
├── README.md                       # Project documentation
├── shared/                         # Shared code across all components
│   ├── protocol.py                # Message serialization/deserialization
│   ├── constants.py               # All API codes and status codes
│   └── utils.py                   # Helper functions
├── database/                       # Backend database servers
│   ├── init_db.py                 # Database schema initialization
│   ├── customer_db.py             # Customer DB server (1025 LOC)
│   └── product_db.py              # Product DB server (561 LOC)
├── server/                         # Stateless frontend servers
│   ├── seller_server.py           # Seller frontend (447 LOC)
│   └── buyer_server.py            # Buyer frontend (578 LOC)
├── client/                         # CLI clients
│   ├── seller_client.py           # Seller CLI
│   └── buyer_client.py            # Buyer CLI (518 LOC)
├── tests/                          # Testing
│   └── performance_test.py        # Load testing (635 LOC)
└── scripts/                        # Utility scripts
    ├── start_all.sh               # Start all servers
    └── stop_all.sh                # Stop all servers
```

---

## Module-by-Module Analysis

### 1. **Configuration (`config.py`)**

**Purpose:** Centralized settings for the entire system

**Key Settings:**
```python
# Database Servers
CUSTOMER_DB_HOST/PORT = 10.224.78.211:5001
PRODUCT_DB_HOST/PORT = 10.224.76.57:5002

# Frontend Servers
BUYER_FRONTEND_HOST/PORT = 10.224.79.148:6001
SELLER_FRONTEND_HOST/PORT = 10.224.79.250:6002

# Session Management
SESSION_TIMEOUT = 300 seconds (5 minutes)
SESSION_CHECK_INTERVAL = 60 seconds

# Performance
BUFFER_SIZE = 8192 bytes
MAX_WORKERS = 100 threads
SOCKET_TIMEOUT = 30 seconds
```

**Review:** ✓ Well-structured, easy to modify for different deployments

---

### 2. **Constants (`shared/constants.py`)**

**Purpose:** Centralized definition of all API operations, status codes, and message delimiters

**Key Sections:**
- **Status Codes**: `SUCCESS`, `ERROR`, `NOT_FOUND`, `UNAUTHORIZED`, `DUPLICATE`, `INSUFFICIENT_QUANTITY`
- **Operations**: 40+ operation codes organized by:
  - Customer DB operations (login, sessions, user management)
  - Product DB operations (item management, search)
  - Frontend API operations (client-facing)
  - Shopping cart operations
- **Item Categories**: 8 predefined categories (Electronics, Clothing, Books, etc.)
- **Validation Limits**: Name/password length constraints

**New Features Added:**
- `OP_RESTORE_SESSION_BUYER` / `OP_RESTORE_SESSION_SELLER`
- `API_BUYER_RESTORE_SESSION` / `API_SELLER_RESTORE_SESSION`

**Review:** ✓ Comprehensive and well-organized

---

### 3. **Protocol (`shared/protocol.py`)**

**Purpose:** Handles all TCP message serialization/deserialization

**Key Methods:**
```python
encode_message(dict) → bytes       # Dict to JSON + delimiter
decode_message(bytes) → dict       # Bytes to JSON dict
send_message(sock, dict)           # Send over TCP
receive_message(sock) → dict       # Receive with delimiter handling
create_response(status, data)      # Standardized response
create_request(operation, data)    # Standardized request
```

**Design Strengths:**
- ✓ JSON for human-readable debugging
- ✓ Message delimiter prevents partial message corruption
- ✓ Accumulated data buffer handles TCP fragmentation
- ✓ Static methods make it namespace-like

**Potential Issue:**
- ⚠️ No encryption (plaintext JSON over network)
- ⚠️ No versioning/compatibility checking

---

### 4. **Utils (`shared/utils.py`)**

**Purpose:** Shared utility functions across the system

**Key Functions:**
```python
generate_session_id()              # UUID-based unique sessions
generate_item_id(category, seq)    # Format: "category-sequence"
parse_item_id(item_id)             # Extract category/sequence
get_current_timestamp()            # Current epoch time
is_session_expired(last_activity)  # Check timeout
validate_item_name(name)           # Validation
validate_keywords(keywords)        # Validation
calculate_search_score(...)        # Search ranking algorithm
format_item_display(item)          # Pretty-print items
```

**Search Scoring Algorithm:**
```python
Exact match in name:      +10 points
Partial match in name:     +5 points
Match in keywords list:    +3 points
Results sorted by score (highest first)
```

**Review:** ✓ Good separation of concerns

---

### 5. **Database Initialization (`database/init_db.py`)**

**Purpose:** Schema creation for both database servers

#### Customer Database Tables:
```sql
sellers
├── seller_id (PK)
├── username (UNIQUE)
├── password
├── seller_name
├── thumbs_up/thumbs_down (ratings)
├── items_sold (counter)
└── created_at

buyers
├── buyer_id (PK)
├── username (UNIQUE)
├── password
├── buyer_name
├── items_purchased (counter)
└── created_at

seller_sessions
├── session_id (PK)
├── seller_id (FK)
├── last_activity (for timeout)
└── created_at

buyer_sessions
├── session_id (PK)
├── buyer_id (FK)
├── last_activity
└── created_at

shopping_carts (active, per-session)
├── id (PK)
├── session_id (FK)
├── buyer_id (FK)
├── item_id (FK)
├── quantity
└── added_at

saved_carts (persistent, per-user)
├── id (PK)
├── buyer_id (FK)
├── item_id (FK)
├── quantity
└── saved_at

purchase_history
├── id (PK)
├── buyer_id (FK)
├── item_id
├── quantity
└── purchase_date
```

#### Product Database Tables:
```sql
items
├── item_id (PK, format: "category-sequence")
├── seller_id
├── name
├── category
├── keywords (stored as JSON)
├── condition (New/Used)
├── price
├── quantity
├── thumbs_up/thumbs_down (item ratings)
└── created_at

item_feedback
├── id (PK)
├── item_id (FK)
├── feedback_type (thumbs_up/down)

category_counters
├── category (PK)
└── last_id (for generating sequential IDs)
```

**Design Points:**
- ✓ Composite keys with UNIQUE constraints for consistency
- ✓ Proper indexing on foreign keys and frequently queried columns
- ✓ Timestamps for audit trails
- ✓ Dual shopping cart system (active + saved)

**Potential Issue:**
- ⚠️ No soft deletes (deleted data lost forever)
- ⚠️ No audit logs for accountability

---

### 6. **Customer Database Server (`database/customer_db.py`)**

**Purpose:** Manages user accounts, sessions, and shopping carts (1025 LOC)

**Main Classes:**
- `CustomerDatabase`: Main server class

**Key Responsibilities:**

**User Management:**
- `_create_seller()` / `_create_buyer()` - Account creation with duplicate checking
- `_login_seller()` / `_login_buyer()` - Generate sessions, validate credentials
- `_logout_seller()` / `_logout_buyer()` - Cleanup sessions and carts
- `_get_seller_info()` / `_get_buyer_info()` - Retrieve user info

**Session Management:**
- `_validate_seller_session()` / `_validate_buyer_session()` - Verify active session
- `_update_session_activity()` - Update last_activity timestamp (prevent timeout)
- `_cleanup_expired_sessions()` - Background thread removes stale sessions
- `_restore_session_buyer()` / `_restore_session_seller()` - **NEW** Session restoration feature

**Shopping Cart Operations:**
- `_get_cart()` - Retrieve active cart items
- `_add_to_cart()` - Add item to session's active cart
- `_remove_from_cart()` - Remove item from cart
- `_clear_cart()` - Clear all items (on logout)
- `_save_cart()` - Persist to saved_carts table, broadcast to other sessions

**Rating System:**
- `_get_seller_rating()` - Calculate seller's average rating
- `_update_seller_feedback()` - Record thumbs up/down votes

**Architecture Patterns:**
```python
def _create_seller(self, data):
    username = data.get('username')
    password = data.get('password')
    seller_name = data.get('seller_name')
    
    conn = self._get_connection()  # Thread-safe connection
    cursor = conn.cursor()
    
    try:
        cursor.execute('''INSERT INTO sellers ...''')
        seller_id = cursor.lastrowid
        conn.commit()
        return Protocol.create_response(STATUS_SUCCESS, data={'seller_id': seller_id})
    except sqlite3.IntegrityError:  # Handle duplicates
        return Protocol.create_response(STATUS_DUPLICATE, message="Username already exists")
    finally:
        conn.close()  # Always clean up
```

**Session Restoration Feature (NEW):**
```python
def _restore_session_buyer(self, data):
    """
    Restore a previous buyer session using session_id
    Validates session exists and is not expired
    Loads active cart from saved_carts on login
    """
    session_id = data.get('session_id')
    
    conn = self._get_connection()
    cursor = conn.cursor()
    
    # Check if session exists and not expired
    cursor.execute('''
        SELECT buyer_id FROM buyer_sessions
        WHERE session_id = ? AND last_activity > ?
    ''', (session_id, current_time - SESSION_TIMEOUT))
    
    # If valid, update activity and return buyer info
```

**Thread Safety:**
- ✓ `self.conn_lock` for database access
- ✓ Background cleanup thread with proper exception handling
- ✓ `check_same_thread=False` for SQLite multi-threading

**Review:**
- ✓ Well-structured with clear method organization
- ✓ Proper error handling
- ⚠️ Plaintext password storage (security risk)
- ⚠️ Shopping cart cleanup could fail if product DB is down
- ⚠️ No transaction rollback on errors

---

### 7. **Product Database Server (`database/product_db.py`)**

**Purpose:** Manages product listings, inventory, and search (561 LOC)

**Key Responsibilities:**

**Item Management:**
- `_register_item()` - Create new item with auto-generated ID
- `_get_item()` - Retrieve item details
- `_update_item_price()` - Modify price
- `_update_item_quantity()` - Adjust inventory
- `_decrease_item_quantity()` - Atomically reduce stock

**Search & Discovery:**
- `_search_items()` - Multi-keyword search with scoring
  - Category is mandatory (must match exactly)
  - Keywords scored: exact match (10), partial (5), in keywords list (3)
  - Only returns items with quantity > 0
  - Results sorted by relevance score
- `_get_seller_items()` - List all items by seller

**Feedback System:**
- `_provide_item_feedback()` - Record thumbs up/down
- `_get_item_feedback()` - Retrieve feedback counts
- `_get_seller_rating()` - Calculate average seller rating

**Item ID Generation:**
```python
# Format: "category-sequence"
# Example: "1-42" means Electronics category, 42nd item
# Thread-safe via SQL UPDATE with counter table
cursor.execute('''
    UPDATE category_counters SET last_id = last_id + 1
    WHERE category = ?
''', (category,))
```

**Search Implementation:**
```python
def _search_items(self, data):
    category = data.get('category')
    keywords = data.get('keywords', [])
    
    # Fetch all items in category with stock > 0
    items = fetch_from_db(category)
    
    # Score each item
    for item in items:
        score = 0
        for keyword in keywords:
            if keyword in item['name'].lower():
                if item['name'].lower() == keyword:
                    score += 10  # Exact match
                else:
                    score += 5   # Partial match
            elif keyword in item['keywords']:
                score += 3       # In keyword list
        
        item['score'] = score
    
    # Sort by score (highest first)
    return sorted(items, key=lambda x: x['score'], reverse=True)
```

**Review:**
- ✓ Atomic operations for inventory (prevents overselling)
- ✓ Flexible search algorithm
- ⚠️ No stock reservation (race condition possible in concurrent purchases)
- ⚠️ No transaction isolation level specified

---

### 8. **Buyer Frontend Server (`server/buyer_server.py`)**

**Purpose:** Stateless frontend handling buyer client requests (578 LOC)

**Architecture:**
```
Buyer Client → Buyer Frontend → Customer DB + Product DB
  (session_id)    (stateless)    (persistent state)
```

**Key Methods:**

**Account Operations:**
- `_create_account()` - Register buyer
- `_login()` - Create session, return session_id
- `_logout()` - Validate session and clean up
- `_restore_session()` - **NEW** Restore previous session

**Shopping Operations:**
- `_add_to_cart()` - Add item, validate availability
- `_remove_from_cart()` - Remove item from active cart
- `_display_cart()` - Show current cart contents
- `_save_cart()` - Persist cart across sessions
- `_clear_cart()` - Empty cart

**Product Discovery:**
- `_search_items()` - Forward search request to product DB
- `_get_item()` - Get single item details

**Ratings & Feedback:**
- `_provide_feedback()` - Rate seller/item
- `_get_seller_rating()` - View seller reputation
- `_get_purchases()` - View purchase history

**Implementation Pattern:**
```python
def _connect_to_db(self, host, port):
    """Create new connection for each request (stateless)"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(config.SOCKET_TIMEOUT)
    sock.connect((host, port))
    return sock

def _db_request(self, db_host, db_port, request):
    """Per-request connection (no pooling)"""
    sock = None
    try:
        sock = self._connect_to_db(db_host, db_port)
        Protocol.send_message(sock, request)
        response = Protocol.receive_message(sock)
        return response
    finally:
        if sock:
            sock.close()  # Always close
```

**Session Validation Flow:**
```
1. Client sends request with session_id
2. Frontend validates session with Customer DB
3. If valid, proceed with operation
4. If invalid/expired, return error
```

**Review:**
- ✓ True stateless design (no in-memory session storage)
- ✓ Each request creates fresh DB connections
- ⚠️ High connection overhead (could use connection pooling)
- ⚠️ No request batching/pipelining

---

### 9. **Seller Frontend Server (`server/seller_server.py`)**

**Purpose:** Stateless frontend for seller operations (447 LOC)

**Similar to buyer frontend with seller-specific operations:**

**Account Operations:**
- `_create_account()` - Register seller
- `_login()` - Create session
- `_logout()` - End session
- `_restore_session()` - **NEW** Session restoration

**Inventory Management:**
- `_register_item()` - List new item for sale
- `_change_price()` - Update item price
- `_update_units()` - Modify inventory quantity
- `_display_items()` - List all seller's items

**Performance:**
- `_get_rating()` - View own seller rating

**Architecture:** Identical to buyer frontend (stateless, per-request DB connections)

**Review:**
- ✓ Clean implementation
- ✓ Consistent with buyer frontend patterns
- ⚠️ No batch operations

---

### 10. **Buyer CLI Client (`client/buyer_client.py`)**

**Purpose:** Interactive command-line interface for buyers (518 LOC)

**Architecture:**
```
User → Buyer CLI ←→ Buyer Frontend Server ←→ Databases
     (interactive)    (stateless)           (persistent)
```

**Session Management:**
```python
self.session_id = None      # Persists across reconnections
self.buyer_id = None        # Local cache
self.buyer_name = None      # Local cache

def restore_session(self):
    """Try to restore previous session using self.session_id"""
    response = self.send_request(API_BUYER_RESTORE_SESSION, {'session_id': self.session_id})
    if response['status'] == STATUS_SUCCESS:
        # Session restored, reload user info
        return True
```

**Main Menu Flow:**
1. **Account**: Create / Login / Logout
2. **Shopping**: Search / Add to cart / View cart / Save cart
3. **Ratings**: View seller rating / Provide feedback
4. **History**: View purchases

**Key Features:**

**Session Restoration (NEW):**
```python
def restore_session(self):
    """Attempt to restore session after client restart"""
    if not self.session_id:
        return False
    
    response = self.send_request(
        API_BUYER_RESTORE_SESSION,
        {'session_id': self.session_id}
    )
    
    if response and response['status'] == STATUS_SUCCESS:
        # Reload buyer info from response
        self.buyer_id = response['data']['buyer_id']
        self.buyer_name = response['data']['buyer_name']
        print(f"✓ Session restored. Welcome back, {self.buyer_name}!")
        return True
    else:
        self.session_id = None  # Clear invalid session
        return False
```

**Search with Scoring:**
```
Category: Electronics
Keywords: laptop gaming

Search Results:
1. Gaming Laptop - $1200 (score: 18) [category match + 2 keyword matches]
2. Laptop Stand - $50 (score: 5) [1 keyword match]
3. Desktop PC - $800 (score: 3) [in keywords list]
```

**Shopping Cart:**
```
Active Cart (per-session, cleared on logout):
├── Item 1-42: Gaming Laptop x1 @ $1200
├── Item 2-15: Clothing Shirt x2 @ $50 each
└── Save Cart → persists to saved_carts (survives logout)

Saved Cart (per-user, loads on login):
├── Item 1-42: Gaming Laptop x1 @ $1200
└── Item 2-15: Clothing Shirt x2 @ $50 each
```

**Display Formatting:**
```python
def format_item_display(item):
    """Pretty-print item details"""
    return f"""
    Item ID: {item['item_id']}
    Name: {item['name']}
    Category: {category_name}
    Price: ${item['price']}
    Quantity Available: {item['quantity']}
    Condition: {item['condition']}
    Seller Rating: {rating:.1f}/5 ({thumbs_up}/{thumbs_down})
    """
```

**Review:**
- ✓ User-friendly menu interface
- ✓ Session restoration capability
- ✓ Good error handling and user feedback
- ⚠️ Session ID not persisted to disk (lost on exit)
- ⚠️ No input validation
- ⚠️ No timeout detection on user side

---

### 11. **Seller CLI Client (`client/seller_client.py`)**

**Purpose:** Interactive CLI for sellers (similar to buyer client)

**Main Operations:**
1. Account management (create/login/logout)
2. Item registration with category, keywords, price, quantity
3. Inventory management (adjust units, change price)
4. Performance tracking (view rating)

**Key Differences from Buyer:**
- Focus on inventory management
- No shopping cart
- View own rating instead of other sellers

**Review:**
- Similar to buyer client
- ✓ Seller-appropriate operations

---

### 12. **Performance Testing (`tests/performance_test.py`)**

**Purpose:** Load testing and performance measurement (635 LOC)

**Test Scenarios:**
- Concurrent client simulation
- Operation type variance (login, search, cart operations)
- Response time measurement
- Throughput calculation

**Metrics Collected:**
```
Average Response Time
Median Response Time
Min/Max Response Time
Standard Deviation
Operations Completed
Error Count
```

**Implementation:**
```python
class PerformanceTester:
    def record_response_time(self, response_time):
        """Thread-safe recording"""
        
    def get_statistics(self):
        """Calculate mean, median, std dev"""
        return {
            'avg_response_time': statistics.mean(...),
            'median_response_time': statistics.median(...),
            'std_dev': statistics.stdev(...),
            'operations_completed': ...,
            'errors': ...
        }
```

**Results Logging:**
- Real-time console output
- Detailed log file with timestamp
- Stored in `tests/logs/performance_summary_YYYYMMDD_HHMMSS.csv`

**Review:**
- ✓ Comprehensive metrics
- ✓ Thread-safe operations
- ✓ Good logging setup
- ⚠️ No warmup phase (JVM/startup overhead included)
- ⚠️ No persistence of results (hard to compare over time)

---

## Key Features

### 1. **Session Management with Timeout**
- Sessions expire after 5 minutes of inactivity
- Background cleanup thread removes stale sessions every 60 seconds
- Activity timestamp updated on each operation

### 2. **Stateless Frontend Architecture**
- Frontend servers hold no persistent state
- Each request creates fresh DB connections
- Allows frontend server restarts without data loss
- Enables horizontal scaling

### 3. **Dual Shopping Cart System**
```
Active Cart (per-session)
├── Temporary, cleared on logout
├── Isolated per login session
└── Modified by add/remove operations

Saved Cart (per-buyer, persistent)
├── Survives logout and session expiration
├── Loaded on login (into active cart)
├── Updated by explicit save_cart operation
└── Survives frontend/backend crashes
```

### 4. **Multi-Keyword Search with Scoring**
- Mandatory exact-match category
- Keyword relevance scoring:
  - Exact name match: 10 points
  - Partial name match: 5 points
  - In keywords field: 3 points
- Results ranked by score

### 5. **Session Restoration (NEW FEATURE)**
- Preserves session across client disconnections
- Client can restore previous session_id
- Avoids re-login after network hiccup
- Loads saved cart automatically

### 6. **Thread-Safe Database Access**
- Proper SQLite connection handling
- Locking mechanisms for concurrent requests
- Background cleanup for expired sessions
- Error recovery patterns

### 7. **TCP Protocol with Message Framing**
- JSON serialization for readability
- `\n###END###\n` delimiter ensures complete message reception
- Handles TCP packet fragmentation
- Request/response pattern

---

## Code Quality Review

### Strengths ✓

1. **Good Separation of Concerns**
   - Database logic isolated from frontend
   - Frontend isolated from clients
   - Shared utilities in separate module

2. **Consistent Error Handling**
   - Standardized response format
   - Proper HTTP-like status codes
   - Informative error messages

3. **Thread Safety**
   - Proper connection management
   - Lock-based synchronization
   - Background cleanup threads

4. **Clear Documentation**
   - Module docstrings explain purpose
   - README with architecture overview
   - Comments on complex algorithms

5. **Scalability Considerations**
   - Stateless frontend allows horizontal scaling
   - Configurable parameters (timeouts, buffer sizes)
   - Thread pool configuration

### Weaknesses & Issues ⚠️

1. **Security Concerns**
   - ❌ Plaintext password storage (no hashing)
   - ❌ No encryption over network (JSON sent in clear)
   - ⚠️ No input validation/sanitization
   - ⚠️ No authentication tokens (just session ID)
   - ⚠️ SQL injectable if not using parameterized queries properly

2. **Data Integrity Issues**
   - ⚠️ Race condition in inventory management
     - Two buyers can both reduce stock to < 0
     - No atomic transaction across DB operations
   - ⚠️ No ACID transaction support for multi-item operations
   - ⚠️ Saved cart can contain items from deleted listings

3. **Error Handling**
   - ⚠️ Limited transaction rollback
   - ⚠️ Incomplete cleanup on errors
   - ⚠️ No retry logic for failed DB operations

4. **Performance Issues**
   - ⚠️ Per-request DB connections (no pooling)
   - ⚠️ No query optimization (sequential search scoring)
   - ⚠️ Full table scan for search (no database indices on keywords)
   - ⚠️ Repeated session validation on each operation

5. **Code Quality**
   - ⚠️ Some methods are long (>100 lines)
   - ⚠️ Limited test coverage (only performance tests)
   - ⚠️ Inconsistent logging
   - ⚠️ Magic numbers scattered throughout

6. **Design Issues**
   - ⚠️ Shopping cart broadcast logic incomplete
   - ⚠️ MakePurchase not implemented
   - ⚠️ No support for partial purchases
   - ⚠️ Session ID stored in plaintext in client

---

## Potential Issues & Improvements

### Critical Issues 🔴

1. **Inventory Race Condition**
   ```python
   # UNSAFE - Race condition possible
   current_qty = db.get_quantity(item_id)
   if current_qty >= requested_qty:
       db.update_quantity(item_id, current_qty - requested_qty)  # <- Another thread can sneak in here!
   ```
   **Fix:** Use atomic SQL UPDATE with WHERE clause
   ```sql
   UPDATE items SET quantity = quantity - ?
   WHERE item_id = ? AND quantity >= ?
   ```

2. **Plaintext Password Storage**
   ```python
   # UNSAFE
   cursor.execute('INSERT INTO sellers VALUES (?, ?, ?)', (username, password, name))
   ```
   **Fix:** Use bcrypt/argon2
   ```python
   import bcrypt
   hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
   cursor.execute('INSERT INTO sellers VALUES (?, ?, ?)', (username, hashed, name))
   ```

3. **SQL Injection Potential**
   **Current:** Using parameterized queries (safe) ✓
   **But:** Ensure all queries use `?` placeholders

### High Priority Issues 🟡

1. **Session ID Persistence**
   - Client loses session_id when exits
   - Can be stored in `~/.marketplace_session` file
   ```python
   import json
   def save_session(self):
       with open(os.path.expanduser("~/.marketplace_session"), 'w') as f:
           json.dump({'session_id': self.session_id, 'buyer_id': self.buyer_id}, f)
   
   def load_session(self):
       try:
           with open(os.path.expanduser("~/.marketplace_session"), 'r') as f:
               return json.load(f)
       except: return {}
   ```

2. **Connection Pooling**
   - Every request creates new connection (overhead)
   - Use `queue.Queue` to maintain connection pool
   ```python
   class DBConnectionPool:
       def __init__(self, host, port, size=5):
           self.pool = queue.Queue()
           for _ in range(size):
               self.pool.put(self._create_connection())
       
       def get_connection(self):
           return self.pool.get()
       
       def return_connection(self, conn):
           self.pool.put(conn)
   ```

3. **Input Validation**
   - No length/type checking on user inputs
   ```python
   def _validate_input(self, username, password):
       if not isinstance(username, str) or len(username) > 32:
           raise ValueError("Invalid username")
       if not isinstance(password, str) or len(password) < 4:
           raise ValueError("Password too short")
   ```

### Medium Priority Issues 🟠

1. **Logging**
   - Only performance_test has logging
   - Add logging to database servers
   ```python
   import logging
   logger = logging.getLogger(__name__)
   logger.info(f"Login successful for user {username}")
   ```

2. **Graceful Shutdown**
   - Servers don't handle SIGTERM
   - Add signal handlers
   ```python
   import signal
   def signal_handler(sig, frame):
       self.running = False
   signal.signal(signal.SIGINT, signal_handler)
   ```

3. **Error Recovery**
   - Limited retry logic
   - Add exponential backoff for DB connection failures
   ```python
   def _get_connection_with_retry(self, max_retries=3):
       for attempt in range(max_retries):
           try:
               return self._get_connection()
           except ConnectionError:
               time.sleep(2 ** attempt)  # Exponential backoff
       raise ConnectionError("Could not connect after retries")
   ```

4. **Unit Tests**
   - Only performance tests exist
   - Add unit tests for core logic
   ```python
   import unittest
   class TestSearchScoring(unittest.TestCase):
       def test_exact_match(self):
           score = calculate_search_score("laptop", ["laptop"])
           self.assertEqual(score, 10)
   ```

### Low Priority Improvements 🟢

1. **Code Organization**
   - Break large files into modules
   - Extract helper classes

2. **Configuration**
   - Load from environment variables
   - Support multiple config profiles

3. **Documentation**
   - Add inline comments for complex algorithms
   - Create API documentation (Swagger/OpenAPI)

4. **Monitoring**
   - Add metrics collection (response times, error rates)
   - Implement health check endpoints

---

## Getting Started Guide

### Prerequisites
- Python 3.7+
- SQLite3

### Installation

1. **Clone the project**
   ```bash
   cd distributed-systems-assignment-session-restore-feature
   ```

2. **No external dependencies** (uses only Python stdlib)
   - sqlite3
   - socket
   - threading
   - json

### Running the System

#### Option 1: Using Start Script
```bash
./scripts/start_all.sh
```
This will start all 4 servers in background

#### Option 2: Manual Startup

Terminal 1 - Customer DB:
```bash
python3 database/customer_db.py
```

Terminal 2 - Product DB:
```bash
python3 database/product_db.py
```

Terminal 3 - Buyer Frontend:
```bash
python3 server/buyer_server.py
```

Terminal 4 - Seller Frontend:
```bash
python3 server/seller_server.py
```

Terminal 5 - Buyer Client:
```bash
python3 client/buyer_client.py
```

Terminal 6 - Seller Client:
```bash
python3 client/seller_client.py
```

### Using the Buyer Client

```
=== Main Menu ===
1. Create Account
2. Login
3. Logout
4. Search Items
5. View Item Details
6. Add to Cart
7. View Cart
8. Save Cart
9. Clear Cart
10. View Purchases
11. Rate Seller
12. Exit

Select option: 2
Username: alice
Password: pass123

✓ Welcome, Alice!

Select option: 4  # Search Items
Category: 1 (Electronics)
Keywords: laptop gaming

=== Search Results (3 items found) ===
--- Item 1 ---
Item ID: 1-42
Name: Gaming Laptop
Price: $1200
Quantity: 5
Condition: New
```

### Using the Seller Client

```
=== Main Menu ===
1. Create Account
2. Login
3. Logout
4. Register Item
5. Change Price
6. Update Inventory
7. Display Items
8. View Rating
9. Exit

Select option: 2
Username: bob
Password: pass123

✓ Welcome, Bob!

Select option: 4  # Register Item
Item Name: Gaming Laptop
Category: 1 (Electronics)
Keywords: gaming,laptop,performance
Price: 1200
Quantity: 5
Condition: New

✓ Item registered! Item ID: 1-42
```

### Session Restoration Example

**Session 1:**
```
python3 client/buyer_client.py
→ Login
→ Add items to cart
→ **Exit application** (Ctrl+C)
```

**Session 2:**
```
python3 client/buyer_client.py
→ **Restore Session** (option in menu)
→ Cart items are still there!
→ Server is still running, session active
```

### Performance Testing

```bash
python3 tests/performance_test.py

====================================
Performance Test Starting
====================================
Testing with 10 concurrent clients...

--- Initial Results ---
Avg Response Time: 45.2ms
Median: 42.1ms
Min: 12.5ms
Max: 156.3ms
StdDev: 23.4ms
Operations: 500
Errors: 0

Results saved to: tests/logs/performance_summary_20260204_120000.csv
```

### Stopping Servers

```bash
./scripts/stop_all.sh
```

Or manually:
```bash
pkill -f "customer_db.py"
pkill -f "product_db.py"
pkill -f "buyer_server.py"
pkill -f "seller_server.py"
```

### Troubleshooting

**"Connection refused"**
- Ensure all backend servers are running
- Check config.py for correct IP addresses

**"Database locked"**
- SQLite doesn't handle concurrent writes well
- Reduce MAX_WORKERS in config.py

**"Session expired"**
- Sessions timeout after 5 minutes of inactivity
- Use "Restore Session" feature to resume
- Or login again

---

## Summary

This is a well-designed distributed marketplace system with:
- ✓ Good separation of concerns
- ✓ Stateless architecture for scalability
- ✓ Thread-safe database handling
- ✓ Clear protocol and API design
- ✓ Session management with restoration

Key improvements needed:
- 🔴 Password hashing (security)
- 🔴 Atomic inventory operations (data integrity)
- 🟡 Connection pooling (performance)
- 🟡 Session persistence (usability)
- 🟡 Input validation (robustness)
- 🟠 Logging and monitoring
- 🟠 Unit tests

The codebase demonstrates solid distributed systems principles and would serve well as a learning project or foundation for a production system after addressing security concerns.

