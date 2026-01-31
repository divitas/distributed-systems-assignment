# Online Marketplace - Distributed System

A distributed online marketplace system implementing client-server architecture using TCP/IP socket programming. This system supports concurrent sellers and buyers with features including item listing, searching, shopping cart management, and user feedback.

## System Design

### Architecture Overview

The system consists of six main components:

1. **Customer Database Server** - Manages seller and buyer accounts, sessions, shopping carts
2. **Product Database Server** - Manages product listings, inventory, search
3. **Seller Frontend Server** - Stateless frontend handling seller client requests
4. **Buyer Frontend Server** - Stateless frontend handling buyer client requests
5. **Seller CLI Client** - Interactive command-line interface for sellers
6. **Buyer CLI Client** - Interactive command-line interface for buyers

### Key Design Decisions

**Stateless Frontend Servers:**
- Frontend servers do not store any persistent state
- All session state, shopping carts, and user data are stored in backend databases
- Supports frontend server crashes/restarts without losing user state
- Enables horizontal scaling of frontend servers

**Session Management:**
- Sessions are identified by unique session IDs generated at login
- Session state persists across TCP reconnections
- Automatic session expiration after 5 minutes of inactivity
- Background thread periodically cleans up expired sessions

**Shopping Cart Architecture:**
- **Active Cart**: Per-session cart stored in shopping_carts table
- **Saved Cart**: Per-user cart stored in saved_carts table
- When a buyer logs in, their saved cart is loaded into the session's active cart
- SaveCart operation persists active cart and updates all other sessions for that buyer
- Logout clears active cart unless it has been saved

**Database Design:**
- SQLite databases with proper indexing for performance
- Thread-safe connection handling
- Separate databases for customer and product data
- ACID compliance for data integrity

**Search Semantics:**
- Category is mandatory and must match exactly
- Keyword scoring system:
  - Exact match of keyword with item name: 10 points
  - Partial match of keyword in item name: 5 points
  - Keyword in item's keyword list: 3 points
- Results sorted by relevance score (highest first)
- Only items with quantity > 0 are returned

**Communication Protocol:**
- JSON-based message format for readability and debugging
- Message delimiter (###END###) for reliable message framing
- Request-response pattern for all operations
- Proper error handling and status codes

### Assumptions

1. Each item ID is uniquely bound to one seller
2. Usernames must be unique within buyer and seller namespaces
3. Item names and seller/buyer names do not need to be unique
4. MakePurchase API is not implemented (as specified)
5. GetBuyerPurchases returns empty list (placeholder as per requirements)
6. Security is simplified (plaintext passwords) for this assignment
7. All communication uses TCP sockets (no REST/RPC/middleware)
8. Frontend servers can crash and restart without affecting active sessions

## Project Structure

```
online-marketplace/
├── config.py                    # Configuration settings
├── requirements.txt             # Python dependencies
├── shared/                      # Shared modules
│   ├── protocol.py             # Message serialization/deserialization
│   ├── constants.py            # Shared constants
│   └── utils.py                # Utility functions
├── database/                    # Backend database servers
│   ├── init_db.py              # Database initialization
│   ├── customer_db.py          # Customer database server
│   └── product_db.py           # Product database server
├── frontend/                    # Stateless frontend servers
│   ├── seller_server.py        # Seller frontend server
│   └── buyer_server.py         # Buyer frontend server
├── client/                      # CLI clients
│   ├── seller_client.py        # Seller CLI client
│   └── buyer_client.py         # Buyer CLI client
├── tests/                       # Testing scripts
│   └── performance_test.py     # Performance testing
└── scripts/                     # Utility scripts
    ├── start_all.sh            # Start all servers
    └── stop_all.sh             # Stop all servers
```

## Installation and Setup

### Prerequisites

- Python 3.7 or higher
- No external dependencies required (uses only Python standard library)

### Installation

1. Extract the project files to your desired location
2. No additional installation required - uses only Python standard library

### Configuration

Edit `config.py` to configure server addresses and ports:

```python
# For local testing (default)
CUSTOMER_DB_HOST = "localhost"
CUSTOMER_DB_PORT = 5001

# For distributed deployment across VMs
CUSTOMER_DB_HOST = "10.0.0.1"  # Replace with your VM IP
CUSTOMER_DB_PORT = 5001
# ... repeat for other components
```

## Running the System

### Starting All Servers (Recommended)

```bash
./scripts/start_all.sh
```

This will:
1. Initialize databases
2. Start Customer Database Server
3. Start Product Database Server
4. Start Seller Frontend Server
5. Start Buyer Frontend Server

### Starting Servers Individually

```bash
# Initialize databases first
python3 database/init_db.py

# Start each server in separate terminals
python3 database/customer_db.py
python3 database/product_db.py
python3 frontend/seller_server.py
python3 frontend/buyer_server.py
```

### Starting Clients

```bash
# Seller client
python3 client/seller_client.py

# Buyer client
python3 client/buyer_client.py
```

### Stopping All Servers

```bash
./scripts/stop_all.sh
```

Or press Ctrl+C in the terminal running start_all.sh

## Deployment on 5 VMs

### Recommended VM Distribution

- **VM 1**: Customer Database Server
- **VM 2**: Product Database Server
- **VM 3**: Seller Frontend Server
- **VM 4**: Buyer Frontend Server
- **VM 5**: Clients and Performance Testing

### Deployment Steps

1. **On each VM**, copy the entire project directory

2. **Update `config.py`** with the actual VM IP addresses:
```python
CUSTOMER_DB_HOST = "10.0.0.1"  # VM1 IP
PRODUCT_DB_HOST = "10.0.0.2"   # VM2 IP
SELLER_FRONTEND_HOST = "10.0.0.4"  # VM4 IP
BUYER_FRONTEND_HOST = "10.0.0.3"   # VM3 IP
```

3. **On VM1** (Customer DB):
```bash
python3 database/init_db.py
python3 database/customer_db.py
```

4. **On VM2** (Product DB):
```bash
python3 database/init_db.py
python3 database/product_db.py
```

5. **On VM3** (Buyer Frontend):
```bash
python3 server/buyer_server.py
```

6. **On VM4** (Seller Frontend):
```bash
python3 server/seller_server.py
```

7. **On VM5** (Clients):
```bash
# Run clients or performance tests
python3 client/seller_client.py
python3 client/buyer_client.py
python3 tests/performance_test.py
```

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
- **Error Rate**: Percentage of failed operations

## API Reference

### Seller APIs

1. **CreateAccount** - Register new seller account
2. **Login** - Authenticate and create session
3. **Logout** - End session
4. **GetSellerRating** - Get feedback ratings
5. **RegisterItemForSale** - List new item
6. **ChangeItemPrice** - Update item price
7. **UpdateUnitsForSale** - Remove units from sale
8. **DisplayItemsForSale** - View all seller's items

### Buyer APIs

1. **CreateAccount** - Register new buyer account
2. **Login** - Authenticate and create session
3. **Logout** - End session (clears unsaved cart)
4. **SearchItemsForSale** - Search by category and keywords
5. **GetItem** - Get item details by ID
6. **AddItemToCart** - Add items to session cart
7. **RemoveItemFromCart** - Remove items from session cart
8. **SaveCart** - Persist cart across sessions
9. **ClearCart** - Empty shopping cart
10. **DisplayCart** - View cart contents
11. **ProvideFeedback** - Rate item and seller
12. **GetSellerRating** - View seller ratings
13. **GetBuyerPurchases** - View purchase history

## Testing Guide

### Manual Testing

1. **Start all servers**
```bash
./scripts/start_all.sh
```

2. **Open two terminals for clients**
```bash
# Terminal 1: Seller
python3 client/seller_client.py

# Terminal 2: Buyer
python3 client/buyer_client.py
```

3. **Test workflow**:
   - Seller: Create account → Login → Register items
   - Buyer: Create account → Login → Search items → Add to cart → Save cart
   - Buyer: Logout → Login again (cart should be restored)
   - Buyer: Provide feedback on items

### Concurrent Testing

Run multiple client instances simultaneously:
```bash
# Start multiple sellers in different terminals
python3 client/seller_client.py &
python3 client/seller_client.py &

# Start multiple buyers
python3 client/buyer_client.py &
python3 client/buyer_client.py &
```

### Automated Performance Testing

```bash
python3 tests/performance_test.py
```

## Current System Status

### Working Features ✓

- ✓ All seller APIs fully functional
- ✓ All buyer APIs functional (except MakePurchase)
- ✓ Session management with timeout
- ✓ Stateless frontend architecture
- ✓ Shopping cart persistence across sessions
- ✓ Multi-user concurrent access
- ✓ Search with relevance scoring
- ✓ Feedback system for items and sellers
- ✓ Thread-safe database operations
- ✓ Proper error handling and validation
- ✓ CLI interfaces for buyers and sellers
- ✓ Performance testing framework

### Not Implemented

- ✗ MakePurchase API (as specified in requirements)
- ✗ Actual purchase transactions
- ✗ GetBuyerPurchases returns empty list (placeholder)

## Troubleshooting

### Port Already in Use
```bash
# Find and kill process using port
lsof -ti:5001 | xargs kill -9
```

### Database Locked
```bash
# Remove and reinitialize databases
rm data/*.db
python3 database/init_db.py
```

### Connection Refused
- Ensure all servers are running
- Check firewall settings (especially when using multiple VMs)
- Verify IP addresses in config.py

### Session Expired
- Sessions expire after 5 minutes of inactivity
- Simply login again to create a new session

## Performance Optimization Features

1. **Connection Pooling**: Database servers handle multiple concurrent connections
2. **Thread Pool**: Frontend servers use thread pools for request handling
3. **Indexed Database**: Proper indexes on frequently queried fields
4. **Efficient Search**: Scored search with early termination
5. **Minimal Data Transfer**: Only necessary data sent in responses
6. **Background Cleanup**: Automatic cleanup of expired sessions

## Future Enhancements (for next assignments)

- Implement MakePurchase API
- Add encryption for passwords and sensitive data
- Implement gRPC/SOAP for inter-service communication
- Add Raft consensus for database replication
- Implement financial transaction tracking
- Add persistent purchase history
- Load balancing for frontend servers
- Caching layer for frequently accessed data

## Authors

Developed for CSCI/ECEN 5673: Distributed Systems, Spring 2026

## License

Educational use only
