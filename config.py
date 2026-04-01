"""
Configuration file for PA3 - Replicated Online Marketplace Distributed System
"""

# ============================================================================
# CUSTOMER DATABASE REPLICAS (5 replicas, rotating sequencer atomic broadcast)
# Each replica runs the gRPC customer DB + atomic broadcast on UDP
# ============================================================================
CUSTOMER_DB_REPLICAS = [
    {"host": "10.224.78.211", "grpc_port": 5001, "udp_port": 9001, "id": 0},
    {"host": "10.224.78.211", "grpc_port": 5011, "udp_port": 9011, "id": 1},
    {"host": "10.224.76.57",  "grpc_port": 5021, "udp_port": 9021, "id": 2},
    {"host": "10.224.76.57",  "grpc_port": 5031, "udp_port": 9031, "id": 3},
    {"host": "10.224.79.148", "grpc_port": 5041, "udp_port": 9041, "id": 4},
]

# Legacy single-server config (used by frontends to pick a replica)
CUSTOMER_DB_HOST = CUSTOMER_DB_REPLICAS[0]["host"]
CUSTOMER_DB_PORT = CUSTOMER_DB_REPLICAS[0]["grpc_port"]

# ============================================================================
# PRODUCT DATABASE REPLICAS (5 replicas, Raft via PySyncObj)
# ============================================================================
PRODUCT_DB_REPLICAS = [
    {"host": "10.224.76.57",  "grpc_port": 5002, "raft_port": 8001},
    {"host": "10.224.76.57",  "grpc_port": 5012, "raft_port": 8011},
    {"host": "10.224.78.211", "grpc_port": 5022, "raft_port": 8021},
    {"host": "10.224.79.148", "grpc_port": 5032, "raft_port": 8031},
    {"host": "10.224.79.250", "grpc_port": 5042, "raft_port": 8041},
]

PRODUCT_DB_HOST = PRODUCT_DB_REPLICAS[0]["host"]
PRODUCT_DB_PORT = PRODUCT_DB_REPLICAS[0]["grpc_port"]

# ============================================================================
# SELLER FRONTEND REPLICAS (4 replicas, stateless)
# ============================================================================
SELLER_FRONTEND_REPLICAS = [
    {"host": "10.224.79.250", "port": 6002},
    {"host": "10.224.79.148", "port": 6012},
    {"host": "10.224.78.211", "port": 6022},
    {"host": "10.224.76.57",  "port": 6032},
]

SELLER_FRONTEND_HOST = SELLER_FRONTEND_REPLICAS[0]["host"]
SELLER_FRONTEND_PORT = SELLER_FRONTEND_REPLICAS[0]["port"]

# ============================================================================
# BUYER FRONTEND REPLICAS (4 replicas, stateless)
# ============================================================================
BUYER_FRONTEND_REPLICAS = [
    {"host": "10.224.79.148", "port": 6001},
    {"host": "10.224.79.250", "port": 6011},
    {"host": "10.224.78.211", "port": 6021},
    {"host": "10.224.76.57",  "port": 6031},
]

BUYER_FRONTEND_HOST = BUYER_FRONTEND_REPLICAS[0]["host"]
BUYER_FRONTEND_PORT = BUYER_FRONTEND_REPLICAS[0]["port"]

# ============================================================================
# FINANCIAL SERVICE
# ============================================================================
FINANCIAL_SERVICE_HOST = "10.224.76.228"
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

# ============================================================================
# ATOMIC BROADCAST CONFIGURATION
# ============================================================================
AB_RETRANSMIT_TIMEOUT = 2.0    # seconds before requesting retransmit
AB_RETRANSMIT_INTERVAL = 1.0   # how often to check for missing messages
AB_MAX_UDP_SIZE = 65000         # max UDP datagram payload
