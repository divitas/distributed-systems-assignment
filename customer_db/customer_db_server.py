"""
customer_db_server.py - Customer Database Server

This is a backend database server that stores and manages:
- Buyer accounts (id, name, password, purchase history)
- Seller accounts (id, name, password, feedback, items sold)
- Active sessions (session_id, user_id, user_type, timestamps)
- Shopping carts (active and saved)

This server receives requests from the frontend servers (Buyer Server,
Seller Server) and performs data operations.

Storage: In-memory with optional file persistence.
In production, you would use a real database (PostgreSQL, etc.)
"""

import socket
import json
import struct
import threading
import logging
import time
import uuid
import os
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass, field, asdict
from threading import Lock

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class Buyer:
    """Buyer account data."""
    buyer_id: int
    username: str
    password: str  # In production, store hashed!
    items_purchased: int = 0
    purchase_history: List[tuple] = field(default_factory=list)  # List of item_ids


@dataclass
class Seller:
    """Seller account data."""
    seller_id: int
    username: str
    password: str  # In production, store hashed!
    thumbs_up: int = 0
    thumbs_down: int = 0
    items_sold: int = 0


@dataclass
class Session:
    """Active session data."""
    session_id: str
    user_id: int
    user_type: str  # "buyer" or "seller"
    created_at: float
    last_activity: float


@dataclass
class CartItem:
    """Item in shopping cart."""
    item_id: tuple  # (category, unique_id)
    quantity: int


# =============================================================================
# In-Memory Storage
# =============================================================================

class CustomerStorage:
    """
    Thread-safe in-memory storage for customer data.
    
    Uses locks to ensure thread safety for concurrent access.
    """
    
    def __init__(self, persistence_file: Optional[str] = None):
        """
        Initialize storage.
        
        Args:
            persistence_file: Optional file path for data persistence
        """
        self._lock = Lock()
        self._persistence_file = persistence_file
        
        # Data stores
        self._buyers: Dict[int, Buyer] = {}
        self._sellers: Dict[int, Seller] = {}
        self._sessions: Dict[str, Session] = {}
        self._active_carts: Dict[str, List[CartItem]] = {}  # session_id -> cart
        self._saved_carts: Dict[int, List[CartItem]] = {}   # buyer_id -> cart
        
        # Username to ID mappings for login lookup
        self._buyer_usernames: Dict[str, int] = {}
        self._seller_usernames: Dict[str, int] = {}
        
        # ID counters
        self._next_buyer_id = 1
        self._next_seller_id = 1
        
        # Load persisted data if available
        if persistence_file and os.path.exists(persistence_file):
            self._load_data()
    
    # =========================================================================
    # Buyer Operations
    # =========================================================================
    
    def create_buyer(self, username: str, password: str) -> int:
        """Create a new buyer account."""
        with self._lock:
            if username in self._buyer_usernames:
                raise ValueError("Username already exists")
            
            buyer_id = self._next_buyer_id
            self._next_buyer_id += 1
            
            buyer = Buyer(
                buyer_id=buyer_id,
                username=username,
                password=password
            )
            
            self._buyers[buyer_id] = buyer
            self._buyer_usernames[username] = buyer_id
            
            self._save_data()
            return buyer_id
    
    def get_buyer(self, buyer_id: int) -> Optional[Buyer]:
        """Get buyer by ID."""
        with self._lock:
            return self._buyers.get(buyer_id)
    
    def authenticate_buyer(self, username: str, password: str) -> Optional[int]:
        """Authenticate buyer and return buyer_id if successful."""
        with self._lock:
            buyer_id = self._buyer_usernames.get(username)
            if buyer_id is None:
                return None
            
            buyer = self._buyers.get(buyer_id)
            if buyer and buyer.password == password:
                return buyer_id
            return None
    
    def add_buyer_purchase(self, buyer_id: int, item_id: tuple) -> bool:
        """Record a purchase for a buyer."""
        with self._lock:
            buyer = self._buyers.get(buyer_id)
            if not buyer:
                return False
            
            buyer.purchase_history.append(item_id)
            buyer.items_purchased += 1
            self._save_data()
            return True
    
    def get_buyer_purchases(self, buyer_id: int) -> List[tuple]:
        """Get purchase history for a buyer."""
        with self._lock:
            buyer = self._buyers.get(buyer_id)
            if not buyer:
                return []
            return list(buyer.purchase_history)
    
    # =========================================================================
    # Seller Operations
    # =========================================================================
    
    def create_seller(self, username: str, password: str) -> int:
        """Create a new seller account."""
        with self._lock:
            if username in self._seller_usernames:
                raise ValueError("Username already exists")
            
            seller_id = self._next_seller_id
            self._next_seller_id += 1
            
            seller = Seller(
                seller_id=seller_id,
                username=username,
                password=password
            )
            
            self._sellers[seller_id] = seller
            self._seller_usernames[username] = seller_id
            
            self._save_data()
            return seller_id
    
    def get_seller(self, seller_id: int) -> Optional[Seller]:
        """Get seller by ID."""
        with self._lock:
            return self._sellers.get(seller_id)
    
    def authenticate_seller(self, username: str, password: str) -> Optional[int]:
        """Authenticate seller and return seller_id if successful."""
        with self._lock:
            seller_id = self._seller_usernames.get(username)
            if seller_id is None:
                return None
            
            seller = self._sellers.get(seller_id)
            if seller and seller.password == password:
                return seller_id
            return None
    
    def get_seller_rating(self, seller_id: int) -> Optional[tuple]:
        """Get seller feedback (thumbs_up, thumbs_down)."""
        with self._lock:
            seller = self._sellers.get(seller_id)
            if not seller:
                return None
            return (seller.thumbs_up, seller.thumbs_down)
    
    def update_seller_feedback(self, seller_id: int, thumbs_up: bool) -> bool:
        """Update seller feedback."""
        with self._lock:
            seller = self._sellers.get(seller_id)
            if not seller:
                return False
            
            if thumbs_up:
                seller.thumbs_up += 1
            else:
                seller.thumbs_down += 1
            
            self._save_data()
            return True
    
    def increment_seller_items_sold(self, seller_id: int, count: int = 1) -> bool:
        """Increment items sold counter for seller."""
        with self._lock:
            seller = self._sellers.get(seller_id)
            if not seller:
                return False
            seller.items_sold += count
            self._save_data()
            return True
    
    # =========================================================================
    # Session Operations
    # =========================================================================
    
    def create_session(self, user_id: int, user_type: str) -> str:
        """Create a new session and return session_id."""
        with self._lock:
            session_id = str(uuid.uuid4())
            now = time.time()
            
            session = Session(
                session_id=session_id,
                user_id=user_id,
                user_type=user_type,
                created_at=now,
                last_activity=now
            )
            
            self._sessions[session_id] = session
            
            # Initialize empty cart for this session
            self._active_carts[session_id] = []
            
            # If buyer has a saved cart, load it
            if user_type == "buyer":
                saved_cart = self._saved_carts.get(user_id, [])
                if saved_cart:
                    self._active_carts[session_id] = list(saved_cart)
            
            return session_id
    
    def validate_session(self, session_id: str, update_activity: bool = False) -> Optional[dict]:
        """
        Validate a session and optionally update last activity.
        
        Returns session info dict if valid, None if invalid.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            
            if update_activity:
                session.last_activity = time.time()
            
            return {
                "valid": True,
                "user_id": session.user_id,
                "user_type": session.user_type,
                "created_at": session.created_at,
                "last_activity": session.last_activity
            }
    
    def end_session(self, session_id: str) -> bool:
        """End a session (logout)."""
        with self._lock:
            if session_id in self._sessions:
                # Remove active cart (unless saved)
                if session_id in self._active_carts:
                    del self._active_carts[session_id]
                
                del self._sessions[session_id]
                return True
            return False
    
    def cleanup_expired_sessions(self, timeout_seconds: int) -> int:
        """
        Remove sessions that have been inactive for longer than timeout.
        
        Returns number of sessions removed.
        """
        with self._lock:
            now = time.time()
            expired = []
            
            for session_id, session in self._sessions.items():
                if now - session.last_activity > timeout_seconds:
                    expired.append(session_id)
            
            for session_id in expired:
                if session_id in self._active_carts:
                    del self._active_carts[session_id]
                del self._sessions[session_id]
                logger.info(f"Expired session: {session_id[:8]}...")
            
            return len(expired)
    
    # =========================================================================
    # Shopping Cart Operations
    # =========================================================================
    
    def add_to_cart(self, session_id: str, item_id: tuple, quantity: int) -> bool:
        """Add item to active shopping cart."""
        with self._lock:
            if session_id not in self._active_carts:
                return False
            
            cart = self._active_carts[session_id]
            
            # Check if item already in cart
            for cart_item in cart:
                if tuple(cart_item.item_id) == tuple(item_id):
                    cart_item.quantity += quantity
                    return True
            
            # Add new item
            cart.append(CartItem(item_id=item_id, quantity=quantity))
            return True
    
    def remove_from_cart(self, session_id: str, item_id: tuple, quantity: int) -> bool:
        """Remove item from active shopping cart."""
        with self._lock:
            if session_id not in self._active_carts:
                return False
            
            cart = self._active_carts[session_id]
            
            for i, cart_item in enumerate(cart):
                if tuple(cart_item.item_id) == tuple(item_id):
                    cart_item.quantity -= quantity
                    if cart_item.quantity <= 0:
                        cart.pop(i)
                    return True
            
            return False  # Item not in cart
    
    def get_cart(self, session_id: str) -> List[dict]:
        """Get contents of active shopping cart."""
        with self._lock:
            if session_id not in self._active_carts:
                return []
            
            return [
                {"item_id": list(item.item_id), "quantity": item.quantity}
                for item in self._active_carts[session_id]
            ]
    
    def save_cart(self, session_id: str, buyer_id: int) -> bool:
        """Save active cart to persist across sessions."""
        with self._lock:
            if session_id not in self._active_carts:
                return False
            
            # Copy active cart to saved cart
            self._saved_carts[buyer_id] = list(self._active_carts[session_id])
            self._save_data()
            return True
    
    def clear_cart(self, session_id: str) -> bool:
        """Clear active shopping cart."""
        with self._lock:
            if session_id not in self._active_carts:
                return False
            
            self._active_carts[session_id] = []
            return True
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def _save_data(self) -> None:
        """Save data to persistence file."""
        if not self._persistence_file:
            return
        
        try:
            data = {
                "buyers": {k: asdict(v) for k, v in self._buyers.items()},
                "sellers": {k: asdict(v) for k, v in self._sellers.items()},
                "buyer_usernames": self._buyer_usernames,
                "seller_usernames": self._seller_usernames,
                "saved_carts": {
                    k: [{"item_id": list(i.item_id), "quantity": i.quantity} for i in v]
                    for k, v in self._saved_carts.items()
                },
                "next_buyer_id": self._next_buyer_id,
                "next_seller_id": self._next_seller_id,
            }
            
            with open(self._persistence_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
    
    def _load_data(self) -> None:
        """Load data from persistence file."""
        try:
            with open(self._persistence_file, 'r') as f:
                data = json.load(f)
            
            # Restore buyers
            for buyer_id, buyer_data in data.get("buyers", {}).items():
                self._buyers[int(buyer_id)] = Buyer(**buyer_data)
            
            # Restore sellers
            for seller_id, seller_data in data.get("sellers", {}).items():
                self._sellers[int(seller_id)] = Seller(**seller_data)
            
            # Restore username mappings
            self._buyer_usernames = data.get("buyer_usernames", {})
            self._seller_usernames = data.get("seller_usernames", {})
            
            # Restore saved carts
            for buyer_id, cart_data in data.get("saved_carts", {}).items():
                self._saved_carts[int(buyer_id)] = [
                    CartItem(item_id=tuple(item["item_id"]), quantity=item["quantity"])
                    for item in cart_data
                ]
            
            # Restore counters
            self._next_buyer_id = data.get("next_buyer_id", 1)
            self._next_seller_id = data.get("next_seller_id", 1)
            
            logger.info(f"Loaded {len(self._buyers)} buyers, {len(self._sellers)} sellers")
            
        except Exception as e:
            logger.error(f"Failed to load data: {e}")


# =============================================================================
# Database Server
# =============================================================================

class CustomerDBServer:
    """
    TCP server for the Customer Database.
    
    Handles requests from frontend servers (Buyer Server, Seller Server).
    """
    
    HEADER_SIZE = 4
    RECV_BUFFER = 4096
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5003,
                 persistence_file: Optional[str] = None):
        """
        Initialize the database server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            persistence_file: Optional file for data persistence
        """
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._running = False
        
        # Initialize storage
        self._storage = CustomerStorage(persistence_file)
        
        # Operation handlers
        self._handlers: Dict[str, Callable] = {
            "PING": self._handle_ping,
            "CREATE_BUYER": self._handle_create_buyer,
            "CREATE_SELLER": self._handle_create_seller,
            "LOGIN_BUYER": self._handle_login_buyer,
            "LOGIN_SELLER": self._handle_login_seller,
            "LOGOUT": self._handle_logout,
            "VALIDATE_SESSION": self._handle_validate_session,
            "CLEANUP_EXPIRED_SESSIONS": self._handle_cleanup_sessions,
            "GET_SELLER_RATING": self._handle_get_seller_rating,
            "UPDATE_SELLER_FEEDBACK": self._handle_update_seller_feedback,
            "GET_BUYER_PURCHASES": self._handle_get_buyer_purchases,
            "ADD_TO_CART": self._handle_add_to_cart,
            "REMOVE_FROM_CART": self._handle_remove_from_cart,
            "GET_CART": self._handle_get_cart,
            "SAVE_CART": self._handle_save_cart,
            "CLEAR_CART": self._handle_clear_cart,
        }
    
    def start(self) -> None:
        """Start the database server."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.listen(50)
        
        self._running = True
        logger.info(f"Customer DB server started on {self.host}:{self.port}")
        
        try:
            while self._running:
                try:
                    client_socket, address = self._socket.accept()
                    logger.debug(f"Connection from {address}")
                    
                    # Handle in separate thread
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    thread.start()
                    
                except socket.timeout:
                    continue
                except OSError:
                    if self._running:
                        raise
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the database server."""
        self._running = False
        if self._socket:
            self._socket.close()
        logger.info("Customer DB server stopped")
    
    def _handle_client(self, client_socket: socket.socket, address: tuple) -> None:
        """Handle a client connection."""
        client_socket.settimeout(30.0)
        
        try:
            while self._running:
                try:
                    request = self._receive_message(client_socket)
                    if request is None:
                        break
                    
                    response = self._process_request(request)
                    self._send_message(client_socket, response)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error handling request: {e}")
                    break
        finally:
            client_socket.close()
    
    def _receive_message(self, sock: socket.socket) -> Optional[dict]:
        """Receive a length-prefixed JSON message."""
        try:
            header_data = self._recv_exact(sock, self.HEADER_SIZE)
            if not header_data:
                return None
            
            message_length = struct.unpack('!I', header_data)[0]
            message_data = self._recv_exact(sock, message_length)
            
            if not message_data:
                return None
            
            return json.loads(message_data.decode('utf-8'))
        except (json.JSONDecodeError, struct.error):
            return None
    
    def _recv_exact(self, sock: socket.socket, num_bytes: int) -> Optional[bytes]:
        """Receive exactly num_bytes."""
        chunks = []
        bytes_received = 0
        
        while bytes_received < num_bytes:
            chunk = sock.recv(min(num_bytes - bytes_received, self.RECV_BUFFER))
            if not chunk:
                return None
            chunks.append(chunk)
            bytes_received += len(chunk)
        
        return b''.join(chunks)
    
    def _send_message(self, sock: socket.socket, message: dict) -> None:
        """Send a length-prefixed JSON message."""
        message_bytes = json.dumps(message).encode('utf-8')
        header = struct.pack('!I', len(message_bytes))
        sock.sendall(header + message_bytes)
    
    def _process_request(self, request: dict) -> dict:
        """Process a database request."""
        operation = request.get("operation", "")
        handler = self._handlers.get(operation)
        
        if not handler:
            return {"status": "error", "error_message": f"Unknown operation: {operation}"}
        
        try:
            return handler(request.get("data", {}))
        except Exception as e:
            logger.error(f"Error in {operation}: {e}")
            return {"status": "error", "error_message": str(e)}
    
    def _success(self, data: dict) -> dict:
        return {"status": "success", "data": data}
    
    def _error(self, message: str) -> dict:
        return {"status": "error", "error_message": message}
    
    # =========================================================================
    # Request Handlers
    # =========================================================================
    
    def _handle_ping(self, data: dict) -> dict:
        return self._success({"message": "pong", "timestamp": time.time()})
    
    def _handle_create_buyer(self, data: dict) -> dict:
        try:
            buyer_id = self._storage.create_buyer(
                data["username"],
                data["password"]
            )
            return self._success({"buyer_id": buyer_id})
        except ValueError as e:
            return self._error(str(e))
    
    def _handle_create_seller(self, data: dict) -> dict:
        try:
            seller_id = self._storage.create_seller(
                data["username"],
                data["password"]
            )
            return self._success({"seller_id": seller_id})
        except ValueError as e:
            return self._error(str(e))
    
    def _handle_login_buyer(self, data: dict) -> dict:
        buyer_id = self._storage.authenticate_buyer(
            data["username"],
            data["password"]
        )
        
        if buyer_id is None:
            return self._error("Invalid username or password")
        
        session_id = self._storage.create_session(buyer_id, "buyer")
        return self._success({"session_id": session_id, "buyer_id": buyer_id})
    
    def _handle_login_seller(self, data: dict) -> dict:
        seller_id = self._storage.authenticate_seller(
            data["username"],
            data["password"]
        )
        
        if seller_id is None:
            return self._error("Invalid username or password")
        
        session_id = self._storage.create_session(seller_id, "seller")
        return self._success({"session_id": session_id, "seller_id": seller_id})
    
    def _handle_logout(self, data: dict) -> dict:
        self._storage.end_session(data["session_id"])
        return self._success({"logged_out": True})
    
    def _handle_validate_session(self, data: dict) -> dict:
        session_info = self._storage.validate_session(
            data["session_id"],
            data.get("update_activity", False)
        )
        
        if session_info:
            return self._success(session_info)
        return self._success({"valid": False})
    
    def _handle_cleanup_sessions(self, data: dict) -> dict:
        count = self._storage.cleanup_expired_sessions(data["timeout_seconds"])
        return self._success({"expired_count": count})
    
    def _handle_get_seller_rating(self, data: dict) -> dict:
        rating = self._storage.get_seller_rating(data["seller_id"])
        if rating is None:
            return self._error("Seller not found")
        return self._success({"thumbs_up": rating[0], "thumbs_down": rating[1]})
    
    def _handle_update_seller_feedback(self, data: dict) -> dict:
        success = self._storage.update_seller_feedback(
            data["seller_id"],
            data["thumbs_up"]
        )
        if success:
            return self._success({"updated": True})
        return self._error("Seller not found")
    
    def _handle_get_buyer_purchases(self, data: dict) -> dict:
        purchases = self._storage.get_buyer_purchases(data["buyer_id"])
        return self._success({"purchases": purchases})
    
    def _handle_add_to_cart(self, data: dict) -> dict:
        success = self._storage.add_to_cart(
            data["session_id"],
            tuple(data["item_id"]),
            data["quantity"]
        )
        if success:
            return self._success({"added": True})
        return self._error("Failed to add to cart")
    
    def _handle_remove_from_cart(self, data: dict) -> dict:
        success = self._storage.remove_from_cart(
            data["session_id"],
            tuple(data["item_id"]),
            data["quantity"]
        )
        if success:
            return self._success({"removed": True})
        return self._error("Item not in cart")
    
    def _handle_get_cart(self, data: dict) -> dict:
        cart_items = self._storage.get_cart(data["session_id"])
        return self._success({"cart_items": cart_items})
    
    def _handle_save_cart(self, data: dict) -> dict:
        success = self._storage.save_cart(data["session_id"], data["buyer_id"])
        if success:
            return self._success({"saved": True})
        return self._error("Failed to save cart")
    
    def _handle_clear_cart(self, data: dict) -> dict:
        success = self._storage.clear_cart(data["session_id"])
        if success:
            return self._success({"cleared": True})
        return self._error("Failed to clear cart")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Customer Database Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5003, help="Port to listen on")
    parser.add_argument("--data-file", default=None, help="File for data persistence")
    
    args = parser.parse_args()
    
    server = CustomerDBServer(
        host=args.host,
        port=args.port,
        persistence_file=args.data_file
    )
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop()


if __name__ == "__main__":
    main()