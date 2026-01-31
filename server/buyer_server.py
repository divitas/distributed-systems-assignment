"""
Buyer Frontend Server
Stateless frontend that handles buyer client requests
Communicates with Customer DB and Product DB via TCP
"""

import socket
import threading
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.protocol import Protocol
from shared.constants import *


class BuyerFrontend:
    """Buyer Frontend Server - Stateless"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.running = False
        
        # Database connection info
        self.customer_db_host = config.CUSTOMER_DB_HOST
        self.customer_db_port = config.CUSTOMER_DB_PORT
        self.product_db_host = config.PRODUCT_DB_HOST
        self.product_db_port = config.PRODUCT_DB_PORT
    
    def _connect_to_db(self, host, port):
        """Create a new connection to a database server"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(config.SOCKET_TIMEOUT)
        sock.connect((host, port))
        return sock
    
    def _db_request(self, db_host, db_port, request):
        """Make a request to a database server"""
        sock = None
        try:
            sock = self._connect_to_db(db_host, db_port)
            Protocol.send_message(sock, request)
            response = Protocol.receive_message(sock)
            return response
        finally:
            if sock:
                sock.close()
    
    def _validate_session(self, session_id):
        """Validate buyer session with customer DB"""
        request = Protocol.create_request(
            OP_VALIDATE_SESSION_BUYER,
            data={'session_id': session_id}
        )
        response = self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
        return response

    def _restore_session(self, session_id): #JN added
        """Restore an existing session using session_id"""
        if not session_id:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Session ID is required"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_RESTORE_SESSION_BUYER,
            data={'session_id': session_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
        
    def handle_request(self, request):
        """Handle incoming client request"""
        operation = request.get('operation')
        data = request.get('data', {})
        session_id = request.get('session_id')
        
        try:
            if operation == API_BUYER_CREATE_ACCOUNT:
                return self._create_account(data)
            elif operation == API_BUYER_LOGIN:
                return self._login(data)
            elif operation == API_BUYER_LOGOUT:
                return self._logout(session_id)
            elif operation == API_BUYER_RESTORE_SESSION: #JN added
                return self._restore_session(session_id)

            
            # All operations below require valid session
            session_validation = self._validate_session(session_id)
            if session_validation['status'] != STATUS_SUCCESS:
                return session_validation
            
            buyer_id = session_validation['data']['buyer_id']
            
            if operation == API_BUYER_SEARCH_ITEMS:
                return self._search_items(data)
            elif operation == API_BUYER_GET_ITEM:
                return self._get_item(data)
            elif operation == API_BUYER_ADD_TO_CART:
                return self._add_to_cart(session_id, buyer_id, data)
            elif operation == API_BUYER_REMOVE_FROM_CART:
                return self._remove_from_cart(session_id, data)
            elif operation == API_BUYER_SAVE_CART:
                return self._save_cart(session_id, buyer_id)
            elif operation == API_BUYER_CLEAR_CART:
                return self._clear_cart(session_id)
            elif operation == API_BUYER_DISPLAY_CART:
                return self._display_cart(session_id)
            elif operation == API_BUYER_PROVIDE_FEEDBACK:
                return self._provide_feedback(data)
            elif operation == API_BUYER_GET_SELLER_RATING:
                return self._get_seller_rating(data)
            elif operation == API_BUYER_GET_PURCHASES:
                return self._get_purchases(buyer_id)
            else:
                return Protocol.create_response(
                    STATUS_ERROR,
                    message=f"Unknown operation: {operation}"
                )
                
        except Exception as e:
            return Protocol.create_response(STATUS_ERROR, message=str(e))
    
    # ========== API Implementations ==========
    
    def _create_account(self, data):
        """Create new buyer account"""
        username = data.get('username')
        password = data.get('password')
        buyer_name = data.get('buyer_name')
        
        # Validate input
        if not username or not password or not buyer_name:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Username, password, and buyer name are required"
            )
        
        if len(buyer_name) > MAX_NAME_LENGTH:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message=f"Buyer name must be <= {MAX_NAME_LENGTH} characters"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_CREATE_BUYER,
            data={
                'username': username,
                'password': password,
                'buyer_name': buyer_name
            }
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _login(self, data):
        """Login buyer"""
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Username and password are required"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_LOGIN_BUYER,
            data={'username': username, 'password': password}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _logout(self, session_id):
        """Logout buyer"""
        if not session_id:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Session ID required"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_LOGOUT_BUYER,
            data={'session_id': session_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _search_items(self, data):
        """Search for items"""
        category = data.get('category')
        keywords = data.get('keywords', [])
        
        if category is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Category is required"
            )
        
        try:
            category = int(category)
            if category < 1 or category > 8:
                raise ValueError()
        except:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Category must be an integer between 1 and 8"
            )
        
        if not isinstance(keywords, list):
            keywords = []
        
        keywords = keywords[:MAX_KEYWORDS]  # Limit to max keywords
        
        # Forward to product DB
        request = Protocol.create_request(
            OP_SEARCH_ITEMS,
            data={'category': category, 'keywords': keywords}
        )
        
        return self._db_request(
            self.product_db_host,
            self.product_db_port,
            request
        )
    
    def _get_item(self, data):
        """Get item details"""
        item_id = data.get('item_id')
        
        if not item_id:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Item ID is required"
            )
        
        # Forward to product DB
        request = Protocol.create_request(
            OP_GET_ITEM,
            data={'item_id': item_id}
        )
        
        return self._db_request(
            self.product_db_host,
            self.product_db_port,
            request
        )
    
    def _add_to_cart(self, session_id, buyer_id, data):
        """Add item to shopping cart"""
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        
        if not item_id or quantity is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Item ID and quantity are required"
            )
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError()
        except:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Quantity must be a positive integer"
            )
        
        # Check item availability
        availability_request = Protocol.create_request(
            OP_CHECK_ITEM_AVAILABILITY,
            data={'item_id': item_id, 'quantity': quantity}
        )
        
        availability_response = self._db_request(
            self.product_db_host,
            self.product_db_port,
            availability_request
        )
        
        if availability_response['status'] != STATUS_SUCCESS:
            return availability_response
        
        # Add to cart in customer DB
        cart_request = Protocol.create_request(
            OP_ADD_TO_CART,
            data={
                'session_id': session_id,
                'buyer_id': buyer_id,
                'item_id': item_id,
                'quantity': quantity
            }
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            cart_request
        )
    
    def _remove_from_cart(self, session_id, data):
        """Remove item from shopping cart"""
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        
        if not item_id or quantity is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Item ID and quantity are required"
            )
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError()
        except:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Quantity must be a positive integer"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_REMOVE_FROM_CART,
            data={
                'session_id': session_id,
                'item_id': item_id,
                'quantity': quantity
            }
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _save_cart(self, session_id, buyer_id):
        """Save cart to persist across sessions"""
        request = Protocol.create_request(
            OP_SAVE_CART,
            data={
                'session_id': session_id,
                'buyer_id': buyer_id
            }
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _clear_cart(self, session_id):
        """Clear shopping cart"""
        request = Protocol.create_request(
            OP_CLEAR_CART,
            data={'session_id': session_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _display_cart(self, session_id):
        """Display shopping cart"""
        request = Protocol.create_request(
            OP_GET_CART,
            data={'session_id': session_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _provide_feedback(self, data):
        """Provide feedback for an item"""
        item_id = data.get('item_id')
        feedback = data.get('feedback')
        
        if not item_id or feedback is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Item ID and feedback are required"
            )
        
        if feedback not in [FEEDBACK_THUMBS_UP, FEEDBACK_THUMBS_DOWN]:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Feedback must be 1 (thumbs up) or -1 (thumbs down)"
            )
        
        # Provide feedback for item
        item_request = Protocol.create_request(
            OP_PROVIDE_ITEM_FEEDBACK,
            data={
                'item_id': item_id,
                'feedback_type': feedback
            }
        )
        
        item_response = self._db_request(
            self.product_db_host,
            self.product_db_port,
            item_request
        )
        
        if item_response['status'] != STATUS_SUCCESS:
            return item_response
        
        # Get item to find seller
        get_item_request = Protocol.create_request(
            OP_GET_ITEM,
            data={'item_id': item_id}
        )
        
        get_item_response = self._db_request(
            self.product_db_host,
            self.product_db_port,
            get_item_request
        )
        
        if get_item_response['status'] == STATUS_SUCCESS:
            seller_id = get_item_response['data']['item']['seller_id']
            
            # Update seller feedback
            seller_request = Protocol.create_request(
                OP_UPDATE_SELLER_FEEDBACK,
                data={
                    'seller_id': seller_id,
                    'feedback_type': feedback
                }
            )
            
            self._db_request(
                self.customer_db_host,
                self.customer_db_port,
                seller_request
            )
        
        return Protocol.create_response(
            STATUS_SUCCESS,
            message="Feedback recorded for item and seller"
        )
    
    def _get_seller_rating(self, data):
        """Get seller rating"""
        seller_id = data.get('seller_id')
        
        if seller_id is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Seller ID is required"
            )
        
        request = Protocol.create_request(
            OP_GET_SELLER_RATING,
            data={'seller_id': seller_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _get_purchases(self, buyer_id):
        """Get purchase history"""
        request = Protocol.create_request(
            OP_GET_BUYER_PURCHASES,
            data={'buyer_id': buyer_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    # ========== Server Management ==========
    
    def handle_client(self, client_socket, client_address):
        """Handle individual client connection"""
        try:
            while True:
                # Receive request
                request = Protocol.receive_message(client_socket)
                
                # Process request
                response = self.handle_request(request)
                
                # Send response
                Protocol.send_message(client_socket, response)
                
        except Exception as e:
            print(f"Client {client_address} disconnected: {e}")
        finally:
            client_socket.close()
    
    def start(self):
        """Start the frontend server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(config.BACKLOG)
        
        self.running = True
        
        print(f"Buyer Frontend Server started on {self.host}:{self.port}")
        print(f"Connected to Customer DB: {self.customer_db_host}:{self.customer_db_port}")
        print(f"Connected to Product DB: {self.product_db_host}:{self.product_db_port}")
        
        try:
            while self.running:
                client_socket, client_address = server_socket.accept()
                
                # Handle each client in a separate thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
        except KeyboardInterrupt:
            print("\nShutting down Buyer Frontend Server...")
        finally:
            server_socket.close()
            self.running = False


def main():
    """Main entry point"""
    frontend = BuyerFrontend(
        host=config.BUYER_FRONTEND_HOST,
        port=config.BUYER_FRONTEND_PORT
    )
    frontend.start()


if __name__ == '__main__':
    main()
