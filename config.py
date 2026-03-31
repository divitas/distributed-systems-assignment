"""
Configuration file for the Online Marketplace Distributed System
Modify these settings to match your deployment environment
"""

# ============================================================================
# SINGLE INSTANCE BACKEND CONFIGURATIONS (PA2-compatible fallback)
# ============================================================================
CUSTOMER_DB_HOST = "10.224.76.209"
CUSTOMER_DB_PORT = 5001

PRODUCT_DB_HOST = "10.224.79.164"
PRODUCT_DB_PORT = 5002

# ============================================================================
# FRONTEND SERVER CONFIGURATIONS (legacy/single instance fallback)
# ============================================================================
BUYER_FRONTEND_HOST = "10.224.78.247"
BUYER_FRONTEND_PORT = 6001

SELLER_FRONTEND_HOST = "10.224.79.170"
SELLER_FRONTEND_PORT = 6002

# ============================================================================
# FRONTEND REPLICA CONFIGURATIONS (PA3 Step 1)
# You can run multiple replicas on the same VM using different ports
# ============================================================================
BUYER_FRONTEND_REPLICAS = [
    {"id": 0, "host": "10.224.78.247", "port": 6001},
    {"id": 1, "host": "10.224.78.247", "port": 6003},
    {"id": 2, "host": "10.224.79.170", "port": 6005},
    {"id": 3, "host": "10.224.79.170", "port": 6007},
]

SELLER_FRONTEND_REPLICAS = [
    {"id": 0, "host": "10.224.79.170", "port": 6002},
    {"id": 1, "host": "10.224.79.170", "port": 6004},
    {"id": 2, "host": "10.224.78.247", "port": 6006},
    {"id": 3, "host": "10.224.78.247", "port": 6008},
]

# ============================================================================
# CUSTOMER DB REPLICAS (PA3 - Rotating Sequencer Atomic Broadcast)
# ============================================================================
CUSTOMER_DB_REPLICAS = [
    {"id": 0, "host": "10.224.76.209", "grpc_port": 5001, "udp_port": 5101, "db_file": "data/customer_0.db"},
    {"id": 1, "host": "10.224.78.247",  "grpc_port": 5003, "udp_port": 5103, "db_file": "data/customer_1.db"},
    {"id": 2, "host": "10.224.79.170", "grpc_port": 5005, "udp_port": 5105, "db_file": "data/customer_2.db"},
    {"id": 3, "host": "10.224.77.206", "grpc_port": 5007, "udp_port": 5107, "db_file": "data/customer_3.db"},
    {"id": 4, "host": "10.224.79.164", "grpc_port": 5009, "udp_port": 5109, "db_file": "data/customer_4.db"},
]

ATOMIC_BROADCAST_SOCKET_TIMEOUT = 0.5
ATOMIC_BROADCAST_RETRANSMIT_INTERVAL = 0.5
ATOMIC_BROADCAST_DELIVERY_WAIT_TIMEOUT = 10
ATOMIC_BROADCAST_PENDING_SCAN_INTERVAL = 0.2

# ============================================================================
# FINANCIAL SERVICE CONFIGURATIONS
# ============================================================================
FINANCIAL_SERVICE_HOST = "10.224.77.206"
FINANCIAL_SERVICE_PORT = 7000

# ============================================================================
# SESSION CONFIGURATION
# ============================================================================
SESSION_TIMEOUT = 300
SESSION_CHECK_INTERVAL = 60

# ============================================================================
# PERFORMANCE CONFIGURATION
# ============================================================================
BUFFER_SIZE = 8192
MAX_WORKERS = 100
SOCKET_TIMEOUT = 30
BACKLOG = 100

# Client failover / retries
HTTP_REQUEST_TIMEOUT = 5
HTTP_RETRY_ALL_REPLICAS = True

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
CUSTOMER_DB_FILE = "data/customer.db"
PRODUCT_DB_FILE = "data/product.db"

DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 30

# ============================================================================
# SEARCH CONFIGURATION
# ============================================================================
MAX_SEARCH_RESULTS = 100
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