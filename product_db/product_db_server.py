"""
product_db_server.py - Product Database Server

This is a backend database server that stores and manages:
- Items for sale (all attributes)
- Item ID generation (category-based unique IDs)
- Item search functionality
- Item feedback tracking

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
import os
from typing import Dict, Optional, List, Callable
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
class Item:
    """Item for sale."""
    item_id: tuple           # (category, unique_id)
    name: str                # max 32 chars
    category: int
    keywords: List[str]      # up to 5, each max 8 chars
    condition: str           # "New" or "Used"
    sale_price: float
    quantity: int
    seller_id: int
    thumbs_up: int = 0
    thumbs_down: int = 0


# =============================================================================
# In-Memory Storage
# =============================================================================

class ProductStorage:
    """
    Thread-safe in-memory storage for product data.
    
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
        
        # Main item storage: item_id (as string "cat,id") -> Item
        self._items: Dict[str, Item] = {}
        
        # Index by seller for quick lookup
        self._seller_items: Dict[int, List[str]] = {}  # seller_id -> list of item_id strings
        
        # Index by category for search
        self._category_items: Dict[int, List[str]] = {}  # category -> list of item_id strings
        
        # ID counter per category
        self._next_item_id: Dict[int, int] = {}  # category -> next_id
        
        # Load persisted data if available
        if persistence_file and os.path.exists(persistence_file):
            self._load_data()
    
    def _item_id_to_str(self, item_id: tuple) -> str:
        """Convert item_id tuple to string key."""
        return f"{item_id[0]},{item_id[1]}"
    
    def _str_to_item_id(self, s: str) -> tuple:
        """Convert string key back to item_id tuple."""
        parts = s.split(',')
        return (int(parts[0]), int(parts[1]))
    
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
        with self._lock:
            # Generate unique ID within category
            if category not in self._next_item_id:
                self._next_item_id[category] = 1
            
            unique_id = self._next_item_id[category]
            self._next_item_id[category] += 1
            
            item_id = (category, unique_id)
            item_id_str = self._item_id_to_str(item_id)
            
            # Create item
            item = Item(
                item_id=item_id,
                name=name,
                category=category,
                keywords=keywords,
                condition=condition,
                sale_price=sale_price,
                quantity=quantity,
                seller_id=seller_id
            )
            
            # Store item
            self._items[item_id_str] = item
            
            # Update seller index
            if seller_id not in self._seller_items:
                self._seller_items[seller_id] = []
            self._seller_items[seller_id].append(item_id_str)
            
            # Update category index
            if category not in self._category_items:
                self._category_items[category] = []
            self._category_items[category].append(item_id_str)
            
            self._save_data()
            return item_id
    
    def get_item(self, item_id: tuple) -> Optional[Item]:
        """Get item by ID."""
        with self._lock:
            item_id_str = self._item_id_to_str(item_id)
            return self._items.get(item_id_str)
    
    def update_item_price(self, item_id: tuple, new_price: float) -> bool:
        """Update an item's price."""
        with self._lock:
            item_id_str = self._item_id_to_str(item_id)
            item = self._items.get(item_id_str)
            
            if not item:
                return False
            
            item.sale_price = new_price
            self._save_data()
            return True
    
    def update_item_quantity(self, item_id: tuple, quantity_change: int) -> Optional[int]:
        """
        Update an item's quantity.
        
        Args:
            item_id: The item to update
            quantity_change: Amount to add (positive) or remove (negative)
            
        Returns:
            New quantity if successful, None if item not found or invalid quantity
        """
        with self._lock:
            item_id_str = self._item_id_to_str(item_id)
            item = self._items.get(item_id_str)
            
            if not item:
                return None
            
            new_quantity = item.quantity + quantity_change
            if new_quantity < 0:
                return None
            
            item.quantity = new_quantity
            self._save_data()
            return new_quantity
    
    def update_item_feedback(self, item_id: tuple, thumbs_up: bool) -> bool:
        """Update an item's feedback."""
        with self._lock:
            item_id_str = self._item_id_to_str(item_id)
            item = self._items.get(item_id_str)
            
            if not item:
                return False
            
            if thumbs_up:
                item.thumbs_up += 1
            else:
                item.thumbs_down += 1
            
            self._save_data()
            return True
    
    def get_seller_items(self, seller_id: int) -> List[Item]:
        """Get all items for a seller."""
        with self._lock:
            item_ids = self._seller_items.get(seller_id, [])
            return [self._items[item_id] for item_id in item_ids if item_id in self._items]
    
    def search_items(self, category: int, keywords: List[str]) -> List[Item]:
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
        with self._lock:
            # Get all items in category
            item_ids = self._category_items.get(category, [])
            
            scored_items = []
            
            for item_id_str in item_ids:
                item = self._items.get(item_id_str)
                if not item or item.quantity <= 0:
                    continue
                
                # Calculate match score
                score = 0
                
                if keywords:
                    for search_kw in keywords:
                        search_kw_lower = search_kw.lower()
                        
                        # Check item keywords
                        for item_kw in item.keywords:
                            item_kw_lower = item_kw.lower()
                            
                            if search_kw_lower == item_kw_lower:
                                # Exact match
                                score += 3
                            elif search_kw_lower in item_kw_lower or item_kw_lower in search_kw_lower:
                                # Partial match
                                score += 1
                        
                        # Check item name
                        if search_kw_lower in item.name.lower():
                            score += 2
                else:
                    # No keywords - all items in category match
                    score = 1
                
                if score > 0 or not keywords:
                    scored_items.append((score, item.sale_price, item.item_id, item))
            
            # Sort by score (desc), then price (asc), then item_id
            scored_items.sort(key=lambda x: (-x[0], x[1], x[2]))
            
            return [item for _, _, _, item in scored_items]
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def _save_data(self) -> None:
        """Save data to persistence file."""
        if not self._persistence_file:
            return
        
        try:
            # Convert items to serializable format
            items_data = {}
            for item_id_str, item in self._items.items():
                item_dict = asdict(item)
                item_dict["item_id"] = list(item.item_id)  # Convert tuple to list
                items_data[item_id_str] = item_dict
            
            data = {
                "items": items_data,
                "seller_items": self._seller_items,
                "category_items": self._category_items,
                "next_item_id": self._next_item_id,
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
            
            # Restore items
            for item_id_str, item_data in data.get("items", {}).items():
                item_data["item_id"] = tuple(item_data["item_id"])
                self._items[item_id_str] = Item(**item_data)
            
            # Restore indexes
            self._seller_items = {int(k): v for k, v in data.get("seller_items", {}).items()}
            self._category_items = {int(k): v for k, v in data.get("category_items", {}).items()}
            self._next_item_id = {int(k): v for k, v in data.get("next_item_id", {}).items()}
            
            logger.info(f"Loaded {len(self._items)} items")
            
        except Exception as e:
            logger.error(f"Failed to load data: {e}")


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
        self._storage = ProductStorage(persistence_file)
        
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
    
    def _item_to_dict(self, item: Item) -> dict:
        """Convert Item to dictionary for JSON response."""
        return {
            "item_id": list(item.item_id),
            "name": item.name,
            "category": item.category,
            "keywords": item.keywords,
            "condition": item.condition,
            "sale_price": item.sale_price,
            "quantity": item.quantity,
            "seller_id": item.seller_id,
            "feedback": [item.thumbs_up, item.thumbs_down]
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
    parser.add_argument("--data-file", default=None, help="File for data persistence")
    
    args = parser.parse_args()
    
    server = ProductDBServer(
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