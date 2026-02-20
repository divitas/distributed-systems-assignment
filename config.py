"""
Configuration file for the Online Marketplace Distributed System
Modify these settings to match your deployment environment
"""

# ============================================================================
# DATABASE SERVER CONFIGURATIONS
# ============================================================================
CUSTOMER_DB_HOST = "10.224.76.209" # vm1 "localhost"
CUSTOMER_DB_PORT = 5001

PRODUCT_DB_HOST = "10.224.79.164" # vm2 "localhost"
PRODUCT_DB_PORT = 5002

# ============================================================================
# FRONTEND SERVER CONFIGURATIONS
# ============================================================================
BUYER_FRONTEND_HOST = "10.224.78.247" # vm3 "localhost"
BUYER_FRONTEND_PORT = 6001

SELLER_FRONTEND_HOST = "10.224.79.170" # vm4 "localhost"
SELLER_FRONTEND_PORT = 6002

# ============================================================================
# FINANCIAL SERVICE CONFIGURATIONS
# ============================================================================

FINANCIAL_SERVICE_HOST = "10.224.77.206" # vm5 "localhost"
FINANCIAL_SERVICE_PORT = 7000

# ============================================================================
# SESSION CONFIGURATION
# ============================================================================
SESSION_TIMEOUT = 300  # 5 minutes in seconds
SESSION_CHECK_INTERVAL = 60  # Check for expired sessions every 60 seconds

# ============================================================================
# PERFORMANCE CONFIGURATION
# ============================================================================
BUFFER_SIZE = 8192  # Socket buffer size (8KB for better performance)
MAX_WORKERS = 100  # Thread pool size for handling requests
SOCKET_TIMEOUT = 30  # Socket timeout in seconds
BACKLOG = 100  # Socket listen backlog

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
CUSTOMER_DB_FILE = "data/customer.db"
PRODUCT_DB_FILE = "data/product.db"

# Connection pool settings
DB_POOL_SIZE = 20  # Number of connections to maintain in pool
DB_MAX_OVERFLOW = 30  # Additional connections allowed beyond pool size

# ==================t==========================================================
# SEARCH CONFIGURATION
# ============================================================================
MAX_SEARCH_RESULTS = 100

# Search scoring weights (for keyword matching)
EXACT_MATCH_WEIGHT = 10
PARTIAL_MATCH_WEIGHT = 5
KEYWORD_MATCH_WEIGHT = 3

# ============================================================================
# ITEM CATEGORIES
# ============================================================================
ITEM_CATEGORIES = {
    1: "Electronics",
    2: "Clothing",
    3: "Books",
    4: "Home & Garden",
    5: "Sports",
    6: "Toys",
    7: "Food",
    8: "Other"
}

# ============================================================================
# DEPLOYMENT CONFIGURATIONS FOR 5 VMs
# Uncomment and modify these when deploying to separate VMs
# ============================================================================
"""
Example VM deployment:
VM1 (10.0.0.1): Customer Database
VM2 (10.0.0.2): Product Database
VM3 (10.0.0.3): Buyer Frontend Server
VM4 (10.0.0.4): Seller Frontend Server
VM5 (10.0.0.5): Client machine (for testing)

CUSTOMER_DB_HOST = "10.0.0.1"
CUSTOMER_DB_PORT = 5001

PRODUCT_DB_HOST = "10.0.0.2"
PRODUCT_DB_PORT = 5002

BUYER_FRONTEND_HOST = "10.0.0.3"
BUYER_FRONTEND_PORT = 6001

SELLER_FRONTEND_HOST = "10.0.0.4"
SELLER_FRONTEND_PORT = 6002
"""
