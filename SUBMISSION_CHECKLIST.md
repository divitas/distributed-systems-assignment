# Submission Checklist
## CSCI/ECEN 5673 Programming Assignment 1

### Required Deliverables ✓

- [x] **All Source Code Files**
  - [x] Customer Database Server (customer_db.py)
  - [x] Product Database Server (product_db.py)
  - [x] Seller Frontend Server (seller_server.py)
  - [x] Buyer Frontend Server (buyer_server.py)
  - [x] Seller CLI Client (seller_client.py)
  - [x] Buyer CLI Client (buyer_client.py)
  - [x] Shared modules (protocol.py, constants.py, utils.py)
  - [x] Database initialization (init_db.py)
  - [x] Configuration file (config.py)

- [x] **Deployment Files**
  - [x] Start script (start_all.sh)
  - [x] Stop script (stop_all.sh)
  - [x] Requirements file (requirements.txt)

- [x] **README File**
  - [x] System design description (8-10 lines) ✓
  - [x] Assumptions documented ✓
  - [x] Current state (what works/doesn't) ✓
  - [x] Complete usage instructions ✓
  - [x] Deployment guide ✓

- [x] **Performance Report File**
  - [x] Experimental setup description ✓
  - [x] Scenario 1 results (1 seller + 1 buyer) ✓
  - [x] Scenario 2 results (10 sellers + 10 buyers) ✓
  - [x] Scenario 3 results (100 sellers + 100 buyers) ✓
  - [x] Performance comparisons ✓
  - [x] Explanations and insights ✓

- [x] **Testing Scripts**
  - [x] Performance testing script (performance_test.py)
  - [x] Automated testing for all scenarios

### Requirements Compliance ✓

#### Core Functionality

- [x] **Six Components Implemented**
  - [x] Client Side Buyers Interface ✓
  - [x] Client Side Sellers Interface ✓
  - [x] Server Side Buyers Interface ✓
  - [x] Server Side Sellers Interface ✓
  - [x] Product Database ✓
  - [x] Customer Database ✓

- [x] **Distributed Deployment**
  - [x] Each component runs as separate process ✓
  - [x] Can run on different servers/IPs ✓
  - [x] No assumptions about colocation ✓

#### API Implementation

**Seller APIs (8/8 implemented):**
- [x] CreateAccount ✓
- [x] Login ✓
- [x] Logout ✓
- [x] GetSellerRating ✓
- [x] RegisterItemForSale ✓
- [x] ChangeItemPrice ✓
- [x] UpdateUnitsForSale ✓
- [x] DisplayItemsForSale ✓

**Buyer APIs (12/13 implemented - MakePurchase excluded as specified):**
- [x] CreateAccount ✓
- [x] Login ✓
- [x] Logout ✓
- [x] SearchItemsForSale ✓
- [x] GetItem ✓
- [x] AddItemToCart ✓
- [x] RemoveItemFromCart ✓
- [x] SaveCart ✓
- [x] ClearCart ✓
- [x] DisplayCart ✓
- [x] ProvideFeedback ✓
- [x] GetSellerRating ✓
- [x] GetBuyerPurchases ✓ (returns empty list as specified)
- [ ] MakePurchase (NOT REQUIRED - as specified in assignment)

#### Technical Requirements

- [x] **TCP/IP Socket Communication**
  - [x] Socket-based TCP/IP for ALL interprocess communication ✓
  - [x] No REST/RPC/middleware ✓

- [x] **Session Management**
  - [x] Separate TCP connection per buyer/seller ✓
  - [x] Session ID distinct from connection ✓
  - [x] Multiple simultaneous logins from different hosts ✓
  - [x] 5-minute session timeout ✓
  - [x] Automatic logout on timeout ✓

- [x] **Stateless Frontend**
  - [x] No persistent per-user state in frontend ✓
  - [x] No login/session state in frontend ✓
  - [x] No shopping cart state in frontend ✓
  - [x] No item metadata in frontend ✓
  - [x] All state in backend databases ✓
  - [x] Resilient to frontend restarts ✓

- [x] **Authentication**
  - [x] Simple username/password (plaintext) ✓
  - [x] Multiple simultaneous logins supported ✓

- [x] **User Interface**
  - [x] CLI interface for buyers ✓
  - [x] CLI interface for sellers ✓

- [x] **Search Semantics**
  - [x] Documented search algorithm ✓
  - [x] Keyword matching scoring system ✓
  - [x] Category-based filtering ✓

#### Performance Evaluation

- [x] **Evaluation Setup**
  - [x] Multiple concurrent buyer sessions ✓
  - [x] Multiple concurrent seller sessions ✓
  - [x] Independent connections ✓

- [x] **Metrics Collection**
  - [x] Average response time measurement ✓
  - [x] 10 runs per scenario ✓
  - [x] Average throughput measurement ✓
  - [x] 1000 operations per client ✓

- [x] **Test Scenarios**
  - [x] Scenario 1: 1 seller + 1 buyer ✓
  - [x] Scenario 2: 10 sellers + 10 buyers ✓
  - [x] Scenario 3: 100 sellers + 100 buyers ✓

- [x] **Performance Analysis**
  - [x] Results for each scenario ✓
  - [x] Explanations and insights ✓
  - [x] Comparison between scenarios ✓

### Additional Deliverables (Bonus)

- [x] **Quick Start Guide** (QUICKSTART.md)
- [x] **Architecture Documentation** (ARCHITECTURE.md)
- [x] **Automated Scripts** (start_all.sh, stop_all.sh)
- [x] **Comprehensive Testing** (performance_test.py)

### Code Quality ✓

- [x] **Clean Code**
  - [x] Well-commented ✓
  - [x] Modular design ✓
  - [x] Consistent naming ✓
  - [x] Proper error handling ✓

- [x] **Documentation**
  - [x] Function docstrings ✓
  - [x] Module documentation ✓
  - [x] Inline comments for complex logic ✓

- [x] **Extensibility**
  - [x] Easy to modify for future assignments ✓
  - [x] Modular protocol layer ✓
  - [x] Configurable parameters ✓

### Testing Verification ✓

Run through this checklist before submission:

1. [x] Extract tarball to fresh directory
2. [x] Run `./scripts/start_all.sh` - all servers start
3. [x] Run `python3 client/seller_client.py` - can create account and login
4. [x] Run `python3 client/buyer_client.py` - can create account and login
5. [x] Seller can register items
6. [x] Buyer can search and find items
7. [x] Buyer can add items to cart
8. [x] Buyer can save cart
9. [x] Buyer logout and login - cart persists
10. [x] Run `python3 tests/performance_test.py` - completes successfully
11. [x] Run `./scripts/stop_all.sh` - all servers stop cleanly

### File Structure Verification ✓

```
online-marketplace/
├── README.md ✓
├── QUICKSTART.md ✓
├── PERFORMANCE_REPORT.md ✓
├── ARCHITECTURE.md ✓
├── requirements.txt ✓
├── config.py ✓
├── shared/ ✓
│   ├── __init__.py
│   ├── protocol.py
│   ├── utils.py
│   └── constants.py
├── database/ ✓
│   ├── __init__.py
│   ├── customer_db.py
│   ├── product_db.py
│   └── init_db.py
├── frontend/ ✓
│   ├── __init__.py
│   ├── buyer_server.py
│   └── seller_server.py
├── client/ ✓
│   ├── __init__.py
│   ├── buyer_client.py
│   └── seller_client.py
├── tests/ ✓
│   ├── __init__.py
│   └── performance_test.py
└── scripts/ ✓
    ├── start_all.sh
    └── stop_all.sh
```

### Known Issues / Limitations

1. **As Specified in Assignment:**
   - MakePurchase API not implemented (assignment states "does not need to be implemented")
   - GetBuyerPurchases returns empty list (Piazza confirmed this is acceptable)

2. **By Design:**
   - Simple authentication (plaintext) - security will be addressed in later assignment
   - SQLite for databases - will upgrade to PostgreSQL in future if needed
   - No encryption - will be added in later assignment

3. **None Critical:**
   - All required functionality working
   - All APIs implemented (except MakePurchase which is excluded)
   - All test scenarios pass

### Final Checks

- [x] All Python files use proper imports
- [x] No hardcoded localhost (uses config.py)
- [x] Scripts have execute permissions
- [x] No absolute paths (all relative)
- [x] Works on fresh Python 3.7+ installation
- [x] No external dependencies required
- [x] Database files created automatically
- [x] Proper error messages for users
- [x] Clean shutdown of all servers
- [x] No orphan processes

### Submission Package

**File:** `online-marketplace.tar.gz`

**Contents:**
- All source code
- All documentation
- All scripts
- README with system description
- PERFORMANCE_REPORT with results
- Configuration files
- Testing scripts

**Size:** ~32KB (compressed)

**Format:** .tar.gz (as required)

**Submission Method:** Upload to Gradescope

---

## Ready for Submission ✓

All requirements met. System tested and verified working.

**Date:** January 30, 2026
**Assignment:** Programming Assignment 1
**Course:** CSCI/ECEN 5673 - Distributed Systems
