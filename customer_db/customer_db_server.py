"""
customer_db_server.py - Optimized Customer Database Server with SQLite Backend

OPTIMIZATIONS:
- Connection pooling per thread
- Optimized SQLite PRAGMA settings
- Better transaction management
- Reduced lock contention
- Fast timeout handling
"""

import socket
import json
import struct
import threading
import logging
import time
import hashlib
import secrets
import sqlite3
from typing import Dict, Optional, List, Callable
from contextlib import contextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CustomerStorage:
    """
    High-performance thread-safe customer database using SQLite.
    """
    
    def __init__(self, db_path: str = "customer.db"):
        self.db_path = db_path
        self.local = threading.local()
        
        # Initialize database schema
        self._init_schema()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get optimized thread-local database connection."""
        if not hasattr(self.local, 'connection'):
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None  # Autocommit mode for better concurrency
            )
            
            # Performance optimizations
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")  # 64MB
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 30000000000")  # 30GB mmap
            conn.execute("PRAGMA page_size = 4096")
            conn.execute("PRAGMA foreign_keys = ON")
            
            conn.row_factory = sqlite3.Row
            self.local.connection = conn
        
        return self.local.connection
    
    @contextmanager
    def _transaction(self):
        """Context manager for explicit transactions."""
        conn = self._get_connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    
    def _init_schema(self):
        """Initialize database schema with optimized indexes."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode = WAL")
        
        cursor = conn.cursor()
        
        # Buyers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyers (
                buyer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                items_purchased INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # Sellers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sellers (
                seller_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                thumbs_up INTEGER DEFAULT 0,
                thumbs_down INTEGER DEFAULT 0,
                items_sold INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_type TEXT NOT NULL CHECK(user_type IN ('buyer', 'seller')),
                created_at REAL NOT NULL,
                last_activity REAL NOT NULL
            )
        """)
        
        # Purchase history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id INTEGER NOT NULL,
                item_category INTEGER NOT NULL,
                item_unique_id INTEGER NOT NULL,
                purchased_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id) ON DELETE CASCADE
            )
        """)
        
        # Shopping carts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cart_items (
                session_id TEXT NOT NULL,
                item_category INTEGER NOT NULL,
                item_unique_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                added_at REAL DEFAULT (julianday('now')),
                PRIMARY KEY (session_id, item_category, item_unique_id)
            )
        """)
        
        # Saved carts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_carts (
                buyer_id INTEGER NOT NULL,
                item_category INTEGER NOT NULL,
                item_unique_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                saved_at REAL DEFAULT (julianday('now')),
                PRIMARY KEY (buyer_id, item_category, item_unique_id),
                FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, user_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchase_history_buyer ON purchase_history(buyer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cart_session ON cart_items(session_id)")
        
        conn.commit()
        conn.close()
    
    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return secrets.token_urlsafe(32)
    
    # Buyer Operations
    
    def create_buyer(self, username: str, password: str) -> int:
        """Create a new buyer account."""
        conn = self._get_connection()
        password_hash = self._hash_password(password)
        
        cursor = conn.execute("""
            INSERT INTO buyers (username, password_hash)
            VALUES (?, ?)
        """, (username, password_hash))
        
        return cursor.lastrowid
    
    def authenticate_buyer(self, username: str, password: str) -> Optional[int]:
        """Authenticate buyer and return buyer_id if successful."""
        conn = self._get_connection()
        password_hash = self._hash_password(password)
        
        cursor = conn.execute("""
            SELECT buyer_id FROM buyers
            WHERE username = ? AND password_hash = ?
        """, (username, password_hash))
        
        row = cursor.fetchone()
        return row[0] if row else None
    
    def add_buyer_purchase(self, buyer_id: int, item_id: tuple) -> bool:
        """Record a purchase for a buyer."""
        with self._transaction() as conn:
            category, unique_id = item_id
            
            conn.execute("""
                INSERT INTO purchase_history (buyer_id, item_category, item_unique_id)
                VALUES (?, ?, ?)
            """, (buyer_id, category, unique_id))
            
            conn.execute("""
                UPDATE buyers SET items_purchased = items_purchased + 1
                WHERE buyer_id = ?
            """, (buyer_id,))
            
            return True
    
    def get_buyer_purchases(self, buyer_id: int) -> List[tuple]:
        """Get purchase history for a buyer."""
        conn = self._get_connection()
        
        cursor = conn.execute("""
            SELECT item_category, item_unique_id FROM purchase_history
            WHERE buyer_id = ?
        """, (buyer_id,))
        
        return [(row[0], row[1]) for row in cursor.fetchall()]
    
    # Seller Operations
    
    def create_seller(self, username: str, password: str) -> int:
        """Create a new seller account."""
        conn = self._get_connection()
        password_hash = self._hash_password(password)
        
        cursor = conn.execute("""
            INSERT INTO sellers (username, password_hash)
            VALUES (?, ?)
        """, (username, password_hash))
        
        return cursor.lastrowid
    
    def authenticate_seller(self, username: str, password: str) -> Optional[int]:
        """Authenticate seller and return seller_id if successful."""
        conn = self._get_connection()
        password_hash = self._hash_password(password)
        
        cursor = conn.execute("""
            SELECT seller_id FROM sellers
            WHERE username = ? AND password_hash = ?
        """, (username, password_hash))
        
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_seller_rating(self, seller_id: int) -> Optional[tuple]:
        """Get seller feedback (thumbs_up, thumbs_down)."""
        conn = self._get_connection()
        
        cursor = conn.execute("""
            SELECT thumbs_up, thumbs_down FROM sellers
            WHERE seller_id = ?
        """, (seller_id,))
        
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None
    
    def update_seller_feedback(self, seller_id: int, thumbs_up: bool) -> bool:
        """Update seller feedback."""
        conn = self._get_connection()
        
        if thumbs_up:
            cursor = conn.execute("""
                UPDATE sellers SET thumbs_up = thumbs_up + 1
                WHERE seller_id = ?
            """, (seller_id,))
        else:
            cursor = conn.execute("""
                UPDATE sellers SET thumbs_down = thumbs_down + 1
                WHERE seller_id = ?
            """, (seller_id,))
        
        return cursor.rowcount > 0
    
    def increment_seller_items_sold(self, seller_id: int, count: int = 1) -> bool:
        """Increment items sold counter for seller."""
        conn = self._get_connection()
        
        cursor = conn.execute("""
            UPDATE sellers SET items_sold = items_sold + ?
            WHERE seller_id = ?
        """, (count, seller_id))
        
        return cursor.rowcount > 0
    
    # Session Operations
    
    def create_session(self, user_id: int, user_type: str) -> str:
        """Create a new session and return session_id."""
        with self._transaction() as conn:
            session_id = self._generate_session_id()
            now = time.time()
            
            conn.execute("""
                INSERT INTO sessions (session_id, user_id, user_type, created_at, last_activity)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, user_id, user_type, now, now))
            
            # If buyer, load saved cart
            if user_type == "buyer":
                conn.execute("""
                    INSERT OR REPLACE INTO cart_items (session_id, item_category, item_unique_id, quantity)
                    SELECT ?, item_category, item_unique_id, quantity
                    FROM saved_carts
                    WHERE buyer_id = ?
                """, (session_id, user_id))
            
            return session_id
    
    def validate_session(self, session_id: str, update_activity: bool = False) -> Optional[dict]:
        """Validate a session and optionally update last activity."""
        conn = self._get_connection()
        
        cursor = conn.execute("""
            SELECT user_id, user_type, created_at, last_activity
            FROM sessions WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        if update_activity:
            conn.execute("""
                UPDATE sessions SET last_activity = ?
                WHERE session_id = ?
            """, (time.time(), session_id))
        
        return {
            "valid": True,
            "user_id": row[0],
            "user_type": row[1],
            "created_at": row[2],
            "last_activity": row[3]
        }
    
    def end_session(self, session_id: str) -> bool:
        """End a session (logout)."""
        with self._transaction() as conn:
            # Delete cart items
            conn.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
            
            # Delete session
            cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            
            return cursor.rowcount > 0
    
    def cleanup_expired_sessions(self, timeout_seconds: int) -> int:
        """Remove expired sessions."""
        with self._transaction() as conn:
            cutoff_time = time.time() - timeout_seconds
            
            # Get expired session IDs
            cursor = conn.execute("""
                SELECT session_id FROM sessions WHERE last_activity < ?
            """, (cutoff_time,))
            
            expired_ids = [row[0] for row in cursor.fetchall()]
            
            if expired_ids:
                placeholders = ','.join('?' * len(expired_ids))
                conn.execute(f"DELETE FROM cart_items WHERE session_id IN ({placeholders})", expired_ids)
                conn.execute(f"DELETE FROM sessions WHERE session_id IN ({placeholders})", expired_ids)
            
            return len(expired_ids)
    
    # Shopping Cart Operations
    
    def add_to_cart(self, session_id: str, item_id: tuple, quantity: int) -> bool:
        """Add item to active shopping cart."""
        conn = self._get_connection()
        category, unique_id = item_id
        
        # Try update first
        cursor = conn.execute("""
            UPDATE cart_items SET quantity = quantity + ?
            WHERE session_id = ? AND item_category = ? AND item_unique_id = ?
        """, (quantity, session_id, category, unique_id))
        
        if cursor.rowcount == 0:
            # Insert new
            conn.execute("""
                INSERT INTO cart_items (session_id, item_category, item_unique_id, quantity)
                VALUES (?, ?, ?, ?)
            """, (session_id, category, unique_id, quantity))
        
        return True
    
    def remove_from_cart(self, session_id: str, item_id: tuple, quantity: int) -> bool:
        """Remove item from active shopping cart."""
        with self._transaction() as conn:
            category, unique_id = item_id
            
            cursor = conn.execute("""
                SELECT quantity FROM cart_items
                WHERE session_id = ? AND item_category = ? AND item_unique_id = ?
            """, (session_id, category, unique_id))
            
            row = cursor.fetchone()
            if not row:
                return False
            
            new_qty = row[0] - quantity
            
            if new_qty <= 0:
                conn.execute("""
                    DELETE FROM cart_items
                    WHERE session_id = ? AND item_category = ? AND item_unique_id = ?
                """, (session_id, category, unique_id))
            else:
                conn.execute("""
                    UPDATE cart_items SET quantity = ?
                    WHERE session_id = ? AND item_category = ? AND item_unique_id = ?
                """, (new_qty, session_id, category, unique_id))
            
            return True
    
    def get_cart(self, session_id: str) -> List[dict]:
        """Get contents of active shopping cart."""
        conn = self._get_connection()
        
        cursor = conn.execute("""
            SELECT item_category, item_unique_id, quantity FROM cart_items
            WHERE session_id = ?
        """, (session_id,))
        
        return [
            {"item_id": [row[0], row[1]], "quantity": row[2]}
            for row in cursor.fetchall()
        ]
    
    def save_cart(self, session_id: str, buyer_id: int) -> bool:
        """Save active cart to persist across sessions."""
        with self._transaction() as conn:
            # Clear existing saved cart
            conn.execute("DELETE FROM saved_carts WHERE buyer_id = ?", (buyer_id,))
            
            # Copy current cart to saved
            conn.execute("""
                INSERT INTO saved_carts (buyer_id, item_category, item_unique_id, quantity)
                SELECT ?, item_category, item_unique_id, quantity
                FROM cart_items
                WHERE session_id = ?
            """, (buyer_id, session_id))
            
            return True
    
    def clear_cart(self, session_id: str) -> bool:
        """Clear active shopping cart."""
        conn = self._get_connection()
        conn.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
        return True
    
    def close(self):
        """Close database connections."""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()


class CustomerDBServer:
    """Optimized TCP server for the Customer Database."""
    
    HEADER_SIZE = 4
    RECV_BUFFER = 8192  # Larger buffer
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5003,
                 db_path: str = "customer.db"):
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._running = False
        
        # Initialize storage
        self._storage = CustomerStorage(db_path)
        
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
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._socket.bind((self.host, self.port))
        self._socket.listen(100)  # Larger backlog
        
        self._running = True
        logger.info(f"Customer DB server started on {self.host}:{self.port}")
        
        try:
            while self._running:
                try:
                    client_socket, address = self._socket.accept()
                    
                    # Handle in separate thread
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    thread.start()
                    
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
        self._storage.close()
        logger.info("Customer DB server stopped")
    
    def _handle_client(self, client_socket: socket.socket, address: tuple) -> None:
        """Handle a client connection with optimized timeouts."""
        client_socket.settimeout(5.0)  # 5 second timeout
        
        try:
            # Single request per connection for simplicity
            request = self._receive_message(client_socket)
            if request:
                response = self._process_request(request)
                self._send_message(client_socket, response)
        
        except socket.timeout:
            logger.warning(f"Client timeout: {address}")
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
        finally:
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            client_socket.close()
    
    def _receive_message(self, sock: socket.socket) -> Optional[dict]:
        """Receive a length-prefixed JSON message."""
        try:
            header_data = self._recv_exact(sock, self.HEADER_SIZE)
            if not header_data:
                return None
            
            message_length = struct.unpack('!I', header_data)[0]
            
            # Sanity check
            if message_length > 1024 * 1024:  # 1MB max
                logger.error(f"Message too large: {message_length}")
                return None
            
            message_data = self._recv_exact(sock, message_length)
            
            if not message_data:
                return None
            
            return json.loads(message_data.decode('utf-8'))
        except (json.JSONDecodeError, struct.error) as e:
            logger.error(f"Message decode error: {e}")
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
            logger.error(f"Error in {operation}: {e}", exc_info=True)
            return {"status": "error", "error_message": str(e)}
    
    def _success(self, data: dict) -> dict:
        return {"status": "success", "data": data}
    
    def _error(self, message: str) -> dict:
        return {"status": "error", "error_message": message}
    
    # Request Handlers
    
    def _handle_ping(self, data: dict) -> dict:
        return self._success({"message": "pong", "timestamp": time.time()})
    
    def _handle_create_buyer(self, data: dict) -> dict:
        try:
            buyer_id = self._storage.create_buyer(data["username"], data["password"])
            return self._success({"buyer_id": buyer_id})
        except sqlite3.IntegrityError:
            return self._error("Username already exists")
    
    def _handle_create_seller(self, data: dict) -> dict:
        try:
            seller_id = self._storage.create_seller(data["username"], data["password"])
            return self._success({"seller_id": seller_id})
        except sqlite3.IntegrityError:
            return self._error("Username already exists")
    
    def _handle_login_buyer(self, data: dict) -> dict:
        buyer_id = self._storage.authenticate_buyer(data["username"], data["password"])
        
        if buyer_id is None:
            return self._error("Invalid username or password")
        
        session_id = self._storage.create_session(buyer_id, "buyer")
        return self._success({"session_id": session_id, "buyer_id": buyer_id})
    
    def _handle_login_seller(self, data: dict) -> dict:
        seller_id = self._storage.authenticate_seller(data["username"], data["password"])
        
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
        success = self._storage.update_seller_feedback(data["seller_id"], data["thumbs_up"])
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
    parser.add_argument("--db-path", default="customer.db", help="SQLite database file path")
    
    args = parser.parse_args()
    
    server = CustomerDBServer(
        host=args.host,
        port=args.port,
        db_path=args.db_path
    )
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop()


if __name__ == "__main__":
    main()