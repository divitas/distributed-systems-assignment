"""
Configuration file for the Online Marketplace Distributed System
Modify these settings to match your deployment environment
"""

# ============================================================================
# VM IP ADDRESSES
# ============================================================================
VM1 = "10.224.78.209"
VM2 = "10.224.79.164"
VM3 = "10.224.78.247"
VM4 = "10.224.79.170"
VM5 = "10.224.77.206"

# ============================================================================
# SINGLE INSTANCE BACKEND CONFIGURATIONS (PA2-compatible fallback)
# ============================================================================
CUSTOMER_DB_HOST = VM1
CUSTOMER_DB_PORT = 5001

PRODUCT_DB_HOST = VM2
PRODUCT_DB_PORT = 5002

# ============================================================================
# FRONTEND SERVER CONFIGURATIONS (legacy/single instance fallback)
# ============================================================================
BUYER_FRONTEND_HOST = VM3
BUYER_FRONTEND_PORT = 6001

SELLER_FRONTEND_HOST = VM4
SELLER_FRONTEND_PORT = 6002

# ============================================================================
# FRONTEND REPLICA CONFIGURATIONS (PA3 Step 1)
# ============================================================================
BUYER_FRONTEND_REPLICAS = [
    {"id": 0, "host": VM1, "port": 6001},
    {"id": 1, "host": VM2, "port": 6011},
    {"id": 2, "host": VM3, "port": 6021},
    {"id": 3, "host": VM4, "port": 6031},
]

SELLER_FRONTEND_REPLICAS = [
    {"id": 0, "host": VM1, "port": 6002},
    {"id": 1, "host": VM2, "port": 6012},
    {"id": 2, "host": VM3, "port": 6022},
    {"id": 3, "host": VM4, "port": 6032},
]

# ============================================================================
# CUSTOMER DB REPLICAS (PA3 - Rotating Sequencer Atomic Broadcast)
# ============================================================================
CUSTOMER_DB_REPLICAS = [
    {"id": 0, "host": VM1, "grpc_port": 5001, "udp_port": 5101, "db_file": "data/customer_0.db"},
    {"id": 1, "host": VM2, "grpc_port": 5003, "udp_port": 5103, "db_file": "data/customer_1.db"},
    {"id": 2, "host": VM3, "grpc_port": 5005, "udp_port": 5105, "db_file": "data/customer_2.db"},
    {"id": 3, "host": VM4, "grpc_port": 5007, "udp_port": 5107, "db_file": "data/customer_3.db"},
    {"id": 4, "host": VM5, "grpc_port": 5009, "udp_port": 5109, "db_file": "data/customer_4.db"},
]

ATOMIC_BROADCAST_SOCKET_TIMEOUT = 0.5
ATOMIC_BROADCAST_RETRANSMIT_INTERVAL = 0.5
ATOMIC_BROADCAST_DELIVERY_WAIT_TIMEOUT = 10
ATOMIC_BROADCAST_PENDING_SCAN_INTERVAL = 0.2

# ============================================================================
# PRODUCT DB REPLICAS (PA3 - Raft via PySyncObj)
# ============================================================================
PRODUCT_DB_REPLICAS = [
    {"id": 0, "host": VM1, "grpc_port": 5002, "raft_port": 5200, "db_file": "data/product_0.db"},
    {"id": 1, "host": VM2, "grpc_port": 5004, "raft_port": 5202, "db_file": "data/product_1.db"},
    {"id": 2, "host": VM3, "grpc_port": 5006, "raft_port": 5204, "db_file": "data/product_2.db"},
    {"id": 3, "host": VM4, "grpc_port": 5008, "raft_port": 5206, "db_file": "data/product_3.db"},
    {"id": 4, "host": VM5, "grpc_port": 5010, "raft_port": 5208, "db_file": "data/product_4.db"},
]

# ============================================================================
# FINANCIAL SERVICE CONFIGURATIONS
# ============================================================================
FINANCIAL_SERVICE_HOST = VM5
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
MAX_WORKERS = 500
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

DB_POOL_SIZE = 50
DB_MAX_OVERFLOW = 150

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