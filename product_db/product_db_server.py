"""
product_db_server.py - Product Database Server with SQLite Backend

This is a backend database server that stores and manages:
- Items for sale (all attributes)
- Item ID generation (auto-incremented unique IDs)
- Item search functionality
- Item feedback tracking

This server receives requests from the frontend servers (Buyer Server,
Seller Server) and performs data operations.

Storage: SQLite database with proper connection pooling and thread-safety.
"""

import socket
import json
import struct
import threading
import logging
import time
import sqlite3
from typing import Dict, Optional, List, Callable
from contextlib import contextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# SQLite Storage Backend
# =============================================================================

class ProductStorage:
    """
    Thread-safe product database using SQLite.
    """
    
    def __init__(self, db_path: str = "products.db"):
        """
        Initialize the database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.local = threading.local()
        
        # Initialize database schema
        self._init_schema()
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a thread-local database connection.
        Each thread gets its own connection for thread-safety.
        """
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            # Enable foreign keys
            self.local.connection.execute("PRAGMA foreign_keys = ON")
            # Use WAL mode for better concurrency
            self.local.connection.execute("PRAGMA journal_mode = WAL")
            # Row factory for dict-like access
            self.local.connection.row_factory = sqlite3.Row
        
        return self.local.connection
    
    @contextmanager
    def _get_cursor(self):
        """Context manager for database cursor with automatic commit/rollback."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
    
    def _init_schema(self):
        """Initialize database schema."""
        with self._get_cursor() as cursor:
            # Items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category INTEGER NOT NULL,
                    unique_id INTEGER NOT NULL,
                    seller_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    condition TEXT NOT NULL CHECK(condition IN ('New', 'Used')),
                    sale_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    thumbs_up INTEGER DEFAULT 0,
                    thumbs_down INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (julianday('now')),
                    UNIQUE(category, unique_id)
                )
            """)
            
            # Keywords table (for item search)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_keywords (
                    item_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    PRIMARY KEY (item_id, keyword),
                    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_seller 
                ON items(seller_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_category 
                ON items(category)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_category_unique 
                ON items(category, unique_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_keywords_keyword 
                ON item_keywords(keyword)
            """)
    
    def _get_next_unique_id(self, cursor, category: int) -> int:
        """Get the next unique_id for a given category."""
        cursor.execute("""
            SELECT MAX(unique_id) FROM items WHERE category = ?
        """, (category,))
        
        row = cursor.fetchone()
        max_id = row[0] if row[0] is not None else 0
        return max_id + 1
    
    # =========================================================================
    # Item Operations
    # =========================================================================
    
    def register_item(
        self,
        seller_id: int,
        name: str,
        category: int,
        keywords: List[str],
        condition: str,
        sale_price: float,
        quantity: int
    ) -> tuple:
        """
        Register a new item for sale.
        
        Returns the assigned item_id (category, unique_id).
        """
        with self._get_cursor() as cursor:
            # Generate unique ID within category
            unique_id = self._get_next_unique_id(cursor, category)
            
            # Insert item
            cursor.execute("""
                INSERT INTO items (category, unique_id, seller_id, name, condition, sale_price, quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (category, unique_id, seller_id, name, condition, sale_price, quantity))
            
            item_id = cursor.lastrowid
            
            # Insert keywords
            for keyword in keywords:
                cursor.execute("""
                    INSERT INTO item_keywords (item_id, keyword)
                    VALUES (?, ?)
                """, (item_id, keyword.lower()))
            
            return (category, unique_id)
    
    def get_item(self, item_id: tuple) -> Optional[Dict]:
        """Get item by ID."""
        with self._get_cursor() as cursor:
            category, unique_id = item_id
            
            cursor.execute("""
                SELECT item_id, category, unique_id, seller_id, name, condition, 
                       sale_price, quantity, thumbs_up, thumbs_down
                FROM items
                WHERE category = ? AND unique_id = ?
            """, (category, unique_id))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get keywords
            cursor.execute("""
                SELECT keyword FROM item_keywords WHERE item_id = ?
            """, (row[0],))
            keywords = [kw[0] for kw in cursor.fetchall()]
            
            return {
                'item_id': (row[1], row[2]),
                'name': row[4],
                'category': row[1],
                'keywords': keywords,
                'condition': row[5],
                'sale_price': row[6],
                'quantity': row[7],
                'seller_id': row[3],
                'thumbs_up': row[8],
                'thumbs_down': row[9]
            }
    
    def update_item_price(self, item_id: tuple, new_price: float) -> bool:
        """Update an item's price."""
        with self._get_cursor() as cursor:
            category, unique_id = item_id
            
            cursor.execute("""
                UPDATE items SET sale_price = ?
                WHERE category = ? AND unique_id = ?
            """, (new_price, category, unique_id))
            
            return cursor.rowcount > 0
    
    def update_item_quantity(self, item_id: tuple, quantity_change: int) -> Optional[int]:
        """
        Update an item's quantity.
        
        Args:
            item_id: The item to update
            quantity_change: Amount to add (positive) or remove (negative)
            
        Returns:
            New quantity if successful, None if item not found or invalid quantity
        """
        with self._get_cursor() as cursor:
            category, unique_id = item_id
            
            # Get current quantity
            cursor.execute("""
                SELECT quantity FROM items 
                WHERE category = ? AND unique_id = ?
            """, (category, unique_id))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            current_qty = row[0]
            new_qty = current_qty + quantity_change
            
            if new_qty < 0:
                return None
            
            # Update quantity
            cursor.execute("""
                UPDATE items SET quantity = ?
                WHERE category = ? AND unique_id = ?
            """, (new_qty, category, unique_id))
            
            return new_qty
    
    def update_item_feedback(self, item_id: tuple, thumbs_up: bool) -> bool:
        """Update an item's feedback."""
        with self._get_cursor() as cursor:
            category, unique_id = item_id
            
            if thumbs_up:
                cursor.execute("""
                    UPDATE items SET thumbs_up = thumbs_up + 1
                    WHERE category = ? AND unique_id = ?
                """, (category, unique_id))
            else:
                cursor.execute("""
                    UPDATE items SET thumbs_down = thumbs_down + 1
                    WHERE category = ? AND unique_id = ?
                """, (category, unique_id))
            
            return cursor.rowcount > 0
    
    def get_seller_items(self, seller_id: int) -> List[Dict]:
        """Get all items for a seller."""
        with self._get_cursor() as cursor:
            cursor.execute("""
                SELECT item_id, category, unique_id, seller_id, name, condition,
                       sale_price, quantity, thumbs_up, thumbs_down
                FROM items
                WHERE seller_id = ?
            """, (seller_id,))
            
            items = []
            for row in cursor.fetchall():
                # Get keywords
                cursor.execute("""
                    SELECT keyword FROM item_keywords WHERE item_id = ?
                """, (row[0],))
                keywords = [kw[0] for kw in cursor.fetchall()]
                
                items.append({
                    'item_id': (row[1], row[2]),
                    'name': row[4],
                    'category': row[1],
                    'keywords': keywords,
                    'condition': row[5],
                    'sale_price': row[6],
                    'quantity': row[7],
                    'seller_id': row[3],
                    'thumbs_up': row[8],
                    'thumbs_down': row[9]
                })
            
            return items
    
    def search_items(self, category: int, keywords: List[str]) -> List[Dict]:
        """
        Search for items by category and keywords.
        
        Search Semantics:
        1. Items must match the specified category exactly
        2. Keyword matching uses a scoring system:
           - Exact keyword match: 3 points
           - Partial match (keyword is substring of item keyword): 1 point
           - Keyword found in item name: 2 points
        3. Results sorted by total score (descending)
        4. Ties broken by: price (ascending), then item_id
        5. Only items with quantity > 0 are returned
        """
        with self._get_cursor() as cursor:
            # Get all items in category with quantity > 0
            cursor.execute("""
                SELECT item_id, category, unique_id, seller_id, name, condition,
                       sale_price, quantity, thumbs_up, thumbs_down
                FROM items
                WHERE category = ? AND quantity > 0
            """, (category,))
            
            items_data = cursor.fetchall()
            scored_items = []
            
            for row in items_data:
                db_item_id = row[0]
                item_id = (row[1], row[2])
                name = row[4]
                price = row[6]
                
                # Get keywords for this item
                cursor.execute("""
                    SELECT keyword FROM item_keywords WHERE item_id = ?
                """, (db_item_id,))
                item_keywords = [kw[0] for kw in cursor.fetchall()]
                
                # Calculate match score
                score = 0
                
                if keywords:
                    for search_kw in keywords:
                        search_kw_lower = search_kw.lower()
                        
                        # Check item keywords
                        for item_kw in item_keywords:
                            item_kw_lower = item_kw.lower()
                            
                            if search_kw_lower == item_kw_lower:
                                # Exact match
                                score += 3
                            elif search_kw_lower in item_kw_lower or item_kw_lower in search_kw_lower:
                                # Partial match
                                score += 1
                        
                        # Check item name
                        if search_kw_lower in name.lower():
                            score += 2
                else:
                    # No keywords - all items in category match
                    score = 1
                
                if score > 0 or not keywords:
                    item_dict = {
                        'item_id': item_id,
                        'name': name,
                        'category': row[1],
                        'keywords': item_keywords,
                        'condition': row[5],
                        'sale_price': price,
                        'quantity': row[7],
                        'seller_id': row[3],
                        'thumbs_up': row[8],
                        'thumbs_down': row[9]
                    }
                    scored_items.append((score, price, item_id, item_dict))
            
            # Sort by score (desc), then price (asc), then item_id
            scored_items.sort(key=lambda x: (-x[0], x[1], x[2]))
            
            return [item for _, _, _, item in scored_items]
    
    def close(self):
        """Close database connections."""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()


# =============================================================================
# Database Server
# =============================================================================

class ProductDBServer:
    """
    TCP server for the Product Database.
    
    Handles requests from frontend servers (Buyer Server, Seller Server).
    """
    
    HEADER_SIZE = 4
    RECV_BUFFER = 4096
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5004,
                 db_path: str = "products.db"):
        """
        Initialize the database server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            db_path: Path to SQLite database file
        """
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._running = False
        
        # Initialize storage
        self._storage = ProductStorage(db_path)
        
        # Operation handlers
        self._handlers: Dict[str, Callable] = {
            "PING": self._handle_ping,
            "REGISTER_ITEM": self._handle_register_item,
            "GET_ITEM": self._handle_get_item,
            "UPDATE_ITEM_PRICE": self._handle_update_price,
            "UPDATE_ITEM_QUANTITY": self._handle_update_quantity,
            "UPDATE_ITEM_FEEDBACK": self._handle_update_feedback,
            "GET_SELLER_ITEMS": self._handle_get_seller_items,
            "SEARCH_ITEMS": self._handle_search_items,
        }
    
    def start(self) -> None:
        """Start the database server."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.listen(50)
        
        self._running = True
        logger.info(f"Product DB server started on {self.host}:{self.port}")
        
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
        self._storage.close()
        logger.info("Product DB server stopped")
    
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
    
    def _item_to_dict(self, item: Dict) -> dict:
        """Convert Item dict to response format."""
        return {
            "item_id": list(item["item_id"]),
            "name": item["name"],
            "category": item["category"],
            "keywords": item["keywords"],
            "condition": item["condition"],
            "sale_price": item["sale_price"],
            "quantity": item["quantity"],
            "seller_id": item["seller_id"],
            "feedback": [item["thumbs_up"], item["thumbs_down"]]
        }
    
    # =========================================================================
    # Request Handlers
    # =========================================================================
    
    def _handle_ping(self, data: dict) -> dict:
        return self._success({"message": "pong", "timestamp": time.time()})
    
    def _handle_register_item(self, data: dict) -> dict:
        item_id = self._storage.register_item(
            seller_id=data["seller_id"],
            name=data["name"],
            category=data["category"],
            keywords=data.get("keywords", []),
            condition=data["condition"],
            sale_price=data["sale_price"],
            quantity=data["quantity"]
        )
        return self._success({"item_id": list(item_id)})
    
    def _handle_get_item(self, data: dict) -> dict:
        item_id = tuple(data["item_id"])
        item = self._storage.get_item(item_id)
        
        if not item:
            return self._error("Item not found")
        
        return self._success({"item": self._item_to_dict(item)})
    
    def _handle_update_price(self, data: dict) -> dict:
        item_id = tuple(data["item_id"])
        success = self._storage.update_item_price(item_id, data["new_price"])
        
        if success:
            return self._success({"updated": True})
        return self._error("Item not found")
    
    def _handle_update_quantity(self, data: dict) -> dict:
        item_id = tuple(data["item_id"])
        new_quantity = self._storage.update_item_quantity(item_id, data["quantity_change"])
        
        if new_quantity is not None:
            return self._success({"updated": True, "new_quantity": new_quantity})
        return self._error("Item not found or invalid quantity")
    
    def _handle_update_feedback(self, data: dict) -> dict:
        item_id = tuple(data["item_id"])
        success = self._storage.update_item_feedback(item_id, data["thumbs_up"])
        
        if success:
            return self._success({"updated": True})
        return self._error("Item not found")
    
    def _handle_get_seller_items(self, data: dict) -> dict:
        items = self._storage.get_seller_items(data["seller_id"])
        return self._success({
            "items": [self._item_to_dict(item) for item in items]
        })
    
    def _handle_search_items(self, data: dict) -> dict:
        items = self._storage.search_items(
            category=data["category"],
            keywords=data.get("keywords", [])
        )
        return self._success({
            "items": [self._item_to_dict(item) for item in items]
        })


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Product Database Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5004, help="Port to listen on")
    parser.add_argument("--db-path", default="products.db", help="SQLite database file path")
    
    args = parser.parse_args()
    
    server = ProductDBServer(
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