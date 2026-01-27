"""
buyer_server.py - Server-Side Buyer Interface

This is the "frontend" server that handles buyer client connections.
It is STATELESS - all persistent data is stored in the backend databases.

Responsibilities:
- Accept TCP connections from buyer clients
- Parse and validate incoming requests
- Route requests to appropriate backend databases (Customer DB, Product DB)
- Handle session timeout monitoring
- Return responses to clients

Key Design Principle: STATELESS
- No session data stored in memory
- No shopping cart data stored in memory
- All state persists in backend databases
- Server can restart without affecting client sessions
"""

import socket
import json
import struct
import threading
import logging
import time
from typing import Dict, Optional, Callable
from dataclasses import dataclass
import sys
import os

# Add project root (parent folder) to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Import the database client to communicate with backends
from db_client.db_client import DatabaseClient, DBConnectionError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Configuration for the buyer server."""
    host: str = "0.0.0.0"
    port: int = 5001
    customer_db_host: str = "localhost"
    customer_db_port: int = 5003
    product_db_host: str = "localhost"
    product_db_port: int = 5004
    session_timeout: int = 300  # 5 minutes
    max_connections: int = 100


class BuyerServer:
    """
    TCP server that handles buyer client connections.
    
    This server is stateless - it forwards all data operations to
    the backend databases and does not store any per-user state.
    """
    
    HEADER_SIZE = 4
    RECV_BUFFER = 4096
    
    def __init__(self, config: ServerConfig):
        """
        Initialize the buyer server.
        
        Args:
            config: Server configuration
        """
        self.config = config
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._client_threads: list[threading.Thread] = []
        
        # Database clients (created per-request to avoid connection issues)
        self._customer_db_config = (config.customer_db_host, config.customer_db_port)
        self._product_db_config = (config.product_db_host, config.product_db_port)
        
        # Request handlers map
        self._handlers: Dict[str, Callable] = {
            "CREATE_ACCOUNT": self._handle_create_account,
            "LOGIN": self._handle_login,
            "LOGOUT": self._handle_logout,
            "SEARCH_ITEMS": self._handle_search_items,
            "GET_ITEM": self._handle_get_item,
            "ADD_TO_CART": self._handle_add_to_cart,
            "REMOVE_FROM_CART": self._handle_remove_from_cart,
            "DISPLAY_CART": self._handle_display_cart,
            "SAVE_CART": self._handle_save_cart,
            "CLEAR_CART": self._handle_clear_cart,
            "PROVIDE_FEEDBACK": self._handle_provide_feedback,
            "GET_SELLER_RATING": self._handle_get_seller_rating,
            "GET_BUYER_PURCHASES": self._handle_get_buyer_purchases,
            "PING": self._handle_ping,
        }
    
    def start(self) -> None:
        """Start the server and begin accepting connections."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.config.host, self.config.port))
        self._socket.listen(self.config.max_connections)
        
        self._running = True
        logger.info(f"Buyer server started on {self.config.host}:{self.config.port}")
        
        # Start session timeout monitor thread
        timeout_thread = threading.Thread(target=self._session_timeout_monitor, daemon=True)
        timeout_thread.start()
        
        try:
            while self._running:
                try:
                    client_socket, address = self._socket.accept()
                    logger.info(f"New connection from {address}")
                    
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    self._client_threads.append(client_thread)
                    
                except socket.timeout:
                    continue
                except OSError:
                    if self._running:
                        raise
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the server."""
        self._running = False
        if self._socket:
            self._socket.close()
        logger.info("Buyer server stopped")
    
    def _handle_client(self, client_socket: socket.socket, address: tuple) -> None:
        """
        Handle a single client connection.
        
        This runs in a separate thread for each connected client.
        """
        client_socket.settimeout(30.0)
        
        try:
            while self._running:
                try:
                    # Receive request
                    request = self._receive_message(client_socket)
                    if request is None:
                        break
                    
                    logger.debug(f"Received request from {address}: {request.get('type')}")
                    
                    # Process request
                    response = self._process_request(request)
                    
                    # Send response
                    self._send_message(client_socket, response)
                    
                except socket.timeout:
                    continue
                except ConnectionError as e:
                    logger.info(f"Client {address} disconnected: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
        finally:
            client_socket.close()
            logger.info(f"Connection closed for {address}")
    
    def _receive_message(self, sock: socket.socket) -> Optional[dict]:
        """Receive a length-prefixed JSON message."""
        try:
            # Receive header
            header_data = self._recv_exact(sock, self.HEADER_SIZE)
            if not header_data:
                return None
            
            message_length = struct.unpack('!I', header_data)[0]
            
            # Receive message body
            message_data = self._recv_exact(sock, message_length)
            if not message_data:
                return None
            
            return json.loads(message_data.decode('utf-8'))
            
        except (json.JSONDecodeError, struct.error) as e:
            logger.error(f"Failed to parse message: {e}")
            return None
    
    def _recv_exact(self, sock: socket.socket, num_bytes: int) -> Optional[bytes]:
        """Receive exactly num_bytes from socket."""
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
        """
        Process an incoming request and return a response.
        
        Routes to appropriate handler based on request type.
        """
        request_type = request.get("type", "")
        handler = self._handlers.get(request_type)
        
        if not handler:
            return self._error_response(f"Unknown request type: {request_type}")
        
        try:
            return handler(request)
        except DBConnectionError as e:
            logger.error(f"Database connection error: {e}")
            return self._error_response("Database temporarily unavailable")
        except Exception as e:
            logger.error(f"Error processing {request_type}: {e}")
            return self._error_response(str(e))
    
    def _success_response(self, data: dict) -> dict:
        """Create a success response."""
        return {"status": "success", "data": data}
    
    def _error_response(self, message: str) -> dict:
        """Create an error response."""
        return {"status": "error", "error_message": message}
    
    # =========================================================================
    # Database Communication Helpers
    # =========================================================================
    
    def _query_customer_db(self, operation: str, data: dict) -> dict:
        """Send a query to the Customer Database."""
        with DatabaseClient(*self._customer_db_config) as db:
            return db.query(operation, data)
    
    def _query_product_db(self, operation: str, data: dict) -> dict:
        """Send a query to the Product Database."""
        with DatabaseClient(*self._product_db_config) as db:
            return db.query(operation, data)
    
    def _validate_session(self, session_id: str) -> Optional[dict]:
        """
        Validate a session and update last activity time.
        
        Returns session data if valid, None if invalid/expired.
        """
        result = self._query_customer_db("VALIDATE_SESSION", {
            "session_id": session_id,
            "update_activity": True
        })
        
        if result.get("status") == "success" and result.get("data", {}).get("valid"):
            return result["data"]
        return None
    
    # =========================================================================
    # Request Handlers
    # =========================================================================
    
    def _handle_ping(self, request: dict) -> dict:
        """Handle ping request for connection testing."""
        return self._success_response({"message": "pong", "timestamp": time.time()})
    
    def _handle_create_account(self, request: dict) -> dict:
        """Handle buyer account creation."""
        data = request.get("data", {})
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        # Validation
        if not username:
            return self._error_response("Username cannot be empty")
        if len(username) > 32:
            return self._error_response("Username must be 32 characters or less")
        if not password:
            return self._error_response("Password cannot be empty")
        
        # Forward to Customer DB
        result = self._query_customer_db("CREATE_BUYER", {
            "username": username,
            "password": password  # In production, hash this!
        })
        
        if result.get("status") == "success":
            return self._success_response({"buyer_id": result["data"]["buyer_id"]})
        else:
            return self._error_response(result.get("error_message", "Account creation failed"))
    
    def _handle_login(self, request: dict) -> dict:
        """Handle buyer login."""
        data = request.get("data", {})
        username = data.get("username", "")
        password = data.get("password", "")
        
        # Forward to Customer DB
        result = self._query_customer_db("LOGIN_BUYER", {
            "username": username,
            "password": password
        })
        
        if result.get("status") == "success":
            return self._success_response({
                "session_id": result["data"]["session_id"],
                "buyer_id": result["data"]["buyer_id"]
            })
        else:
            return self._error_response(result.get("error_message", "Login failed"))
    
    def _handle_logout(self, request: dict) -> dict:
        """Handle buyer logout."""
        session_id = request.get("session_id")
        
        if not session_id:
            return self._error_response("No session ID provided")
        
        # Forward to Customer DB
        result = self._query_customer_db("LOGOUT", {"session_id": session_id})
        
        return self._success_response({"logged_out": True})
    
    def _handle_search_items(self, request: dict) -> dict:
        """Handle item search."""
        session_id = request.get("session_id")
        
        # Validate session
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        data = request.get("data", {})
        category = data.get("category")
        keywords = data.get("keywords", [])
        
        if category is None:
            return self._error_response("Category is required")
        
        # Forward to Product DB
        result = self._query_product_db("SEARCH_ITEMS", {
            "category": category,
            "keywords": keywords
        })
        
        if result.get("status") == "success":
            return self._success_response({"items": result["data"]["items"]})
        else:
            return self._error_response(result.get("error_message", "Search failed"))
    
    def _handle_get_item(self, request: dict) -> dict:
        """Handle get item details."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        data = request.get("data", {})
        item_id = data.get("item_id")
        
        if not item_id:
            return self._error_response("Item ID is required")
        
        # Forward to Product DB
        result = self._query_product_db("GET_ITEM", {"item_id": item_id})
        
        if result.get("status") == "success":
            return self._success_response({"item": result["data"]["item"]})
        else:
            return self._error_response(result.get("error_message", "Item not found"))
    
    def _handle_add_to_cart(self, request: dict) -> dict:
        """Handle add item to cart."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        buyer_id = session.get("user_id")
        data = request.get("data", {})
        item_id = data.get("item_id")
        quantity = data.get("quantity", 1)
        
        if not item_id:
            return self._error_response("Item ID is required")
        if quantity < 1:
            return self._error_response("Quantity must be at least 1")
        
        # Check item availability in Product DB
        item_result = self._query_product_db("GET_ITEM", {"item_id": item_id})
        if item_result.get("status") != "success":
            return self._error_response("Item not found")
        
        available_qty = item_result["data"]["item"]["quantity"]
        if available_qty < quantity:
            return self._error_response(f"Only {available_qty} units available")
        
        # Add to cart in Customer DB (cart is stored in backend!)
        result = self._query_customer_db("ADD_TO_CART", {
            "buyer_id": buyer_id,
            "session_id": session_id,
            "item_id": item_id,
            "quantity": quantity
        })
        
        if result.get("status") == "success":
            return self._success_response({"added": True})
        else:
            return self._error_response(result.get("error_message", "Failed to add to cart"))
    
    def _handle_remove_from_cart(self, request: dict) -> dict:
        """Handle remove item from cart."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        buyer_id = session.get("user_id")
        data = request.get("data", {})
        item_id = data.get("item_id")
        quantity = data.get("quantity", 1)
        
        if not item_id:
            return self._error_response("Item ID is required")
        
        # Remove from cart in Customer DB
        result = self._query_customer_db("REMOVE_FROM_CART", {
            "buyer_id": buyer_id,
            "session_id": session_id,
            "item_id": item_id,
            "quantity": quantity
        })
        
        if result.get("status") == "success":
            return self._success_response({"removed": True})
        else:
            return self._error_response(result.get("error_message", "Failed to remove from cart"))
    
    def _handle_display_cart(self, request: dict) -> dict:
        """Handle display cart contents."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        buyer_id = session.get("user_id")
        
        # Get cart from Customer DB
        result = self._query_customer_db("GET_CART", {
            "buyer_id": buyer_id,
            "session_id": session_id
        })
        
        if result.get("status") == "success":
            return self._success_response({"cart_items": result["data"]["cart_items"]})
        else:
            return self._error_response(result.get("error_message", "Failed to get cart"))
    
    def _handle_save_cart(self, request: dict) -> dict:
        """Handle save cart for persistence across sessions."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        buyer_id = session.get("user_id")
        
        # Save cart in Customer DB
        result = self._query_customer_db("SAVE_CART", {
            "buyer_id": buyer_id,
            "session_id": session_id
        })
        
        if result.get("status") == "success":
            return self._success_response({"saved": True})
        else:
            return self._error_response(result.get("error_message", "Failed to save cart"))
    
    def _handle_clear_cart(self, request: dict) -> dict:
        """Handle clear cart."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        buyer_id = session.get("user_id")
        
        # Clear cart in Customer DB
        result = self._query_customer_db("CLEAR_CART", {
            "buyer_id": buyer_id,
            "session_id": session_id
        })
        
        if result.get("status") == "success":
            return self._success_response({"cleared": True})
        else:
            return self._error_response(result.get("error_message", "Failed to clear cart"))
    
    def _handle_provide_feedback(self, request: dict) -> dict:
        """Handle item feedback."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        data = request.get("data", {})
        item_id = data.get("item_id")
        thumbs_up = data.get("thumbs_up", True)
        
        if not item_id:
            return self._error_response("Item ID is required")
        
        # Update feedback in Product DB
        result = self._query_product_db("UPDATE_ITEM_FEEDBACK", {
            "item_id": item_id,
            "thumbs_up": thumbs_up
        })
        
        if result.get("status") == "success":
            # Also update seller feedback
            item_result = self._query_product_db("GET_ITEM", {"item_id": item_id})
            if item_result.get("status") == "success":
                seller_id = item_result["data"]["item"]["seller_id"]
                self._query_customer_db("UPDATE_SELLER_FEEDBACK", {
                    "seller_id": seller_id,
                    "thumbs_up": thumbs_up
                })
            
            return self._success_response({"feedback_recorded": True})
        else:
            return self._error_response(result.get("error_message", "Failed to record feedback"))
    
    def _handle_get_seller_rating(self, request: dict) -> dict:
        """Handle get seller rating."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        data = request.get("data", {})
        seller_id = data.get("seller_id")
        
        if seller_id is None:
            return self._error_response("Seller ID is required")
        
        # Get seller rating from Customer DB
        result = self._query_customer_db("GET_SELLER_RATING", {"seller_id": seller_id})
        
        if result.get("status") == "success":
            return self._success_response({
                "thumbs_up": result["data"]["thumbs_up"],
                "thumbs_down": result["data"]["thumbs_down"]
            })
        else:
            return self._error_response(result.get("error_message", "Seller not found"))
    
    def _handle_get_buyer_purchases(self, request: dict) -> dict:
        """Handle get buyer purchase history."""
        session_id = request.get("session_id")
        
        session = self._validate_session(session_id)
        if not session:
            return self._error_response("Invalid or expired session")
        
        buyer_id = session.get("user_id")
        
        # Get purchase history from Customer DB
        result = self._query_customer_db("GET_BUYER_PURCHASES", {"buyer_id": buyer_id})
        
        if result.get("status") == "success":
            return self._success_response({"purchases": result["data"]["purchases"]})
        else:
            return self._error_response(result.get("error_message", "Failed to get purchases"))
    
    # =========================================================================
    # Session Timeout Monitor
    # =========================================================================
    
    def _session_timeout_monitor(self) -> None:
        """
        Background thread that periodically checks for expired sessions.
        
        Runs every 60 seconds and asks Customer DB to expire old sessions.
        """
        while self._running:
            try:
                # Ask Customer DB to clean up expired sessions
                self._query_customer_db("CLEANUP_EXPIRED_SESSIONS", {
                    "timeout_seconds": self.config.session_timeout
                })
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
            
            # Sleep for 60 seconds before next check
            time.sleep(60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Buyer Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5001, help="Port to listen on")
    parser.add_argument("--customer-db-host", default="localhost", help="Customer DB host")
    parser.add_argument("--customer-db-port", type=int, default=5003, help="Customer DB port")
    parser.add_argument("--product-db-host", default="localhost", help="Product DB host")
    parser.add_argument("--product-db-port", type=int, default=5004, help="Product DB port")
    
    args = parser.parse_args()
    
    config = ServerConfig(
        host=args.host,
        port=args.port,
        customer_db_host=args.customer_db_host,
        customer_db_port=args.customer_db_port,
        product_db_host=args.product_db_host,
        product_db_port=args.product_db_port
    )
    
    server = BuyerServer(config)
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop()


if __name__ == "__main__":
    main()