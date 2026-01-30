"""
Seller Frontend Server
Stateless frontend that handles seller client requests
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


class SellerFrontend:
    """Seller Frontend Server - Stateless"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.running = False
        
        # Database connection info (no persistent connections, create per request)
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
        """
        Make a request to a database server
        Creates new connection for each request (stateless)
        """
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
        """Validate seller session with customer DB"""
        request = Protocol.create_request(
            OP_VALIDATE_SESSION_SELLER,
            data={'session_id': session_id}
        )
        response = self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
        return response
    
    def handle_request(self, request):
        """Handle incoming client request"""
        operation = request.get('operation')
        data = request.get('data', {})
        session_id = request.get('session_id')
        
        try:
            if operation == API_SELLER_CREATE_ACCOUNT:
                return self._create_account(data)
            elif operation == API_SELLER_LOGIN:
                return self._login(data)
            elif operation == API_SELLER_LOGOUT:
                return self._logout(session_id)
            
            # All operations below require valid session
            session_validation = self._validate_session(session_id)
            if session_validation['status'] != STATUS_SUCCESS:
                return session_validation
            
            seller_id = session_validation['data']['seller_id']
            
            if operation == API_SELLER_GET_RATING:
                return self._get_rating(seller_id)
            elif operation == API_SELLER_REGISTER_ITEM:
                return self._register_item(seller_id, data)
            elif operation == API_SELLER_CHANGE_PRICE:
                return self._change_price(seller_id, data)
            elif operation == API_SELLER_UPDATE_UNITS:
                return self._update_units(seller_id, data)
            elif operation == API_SELLER_DISPLAY_ITEMS:
                return self._display_items(seller_id)
            else:
                return Protocol.create_response(
                    STATUS_ERROR,
                    message=f"Unknown operation: {operation}"
                )
                
        except Exception as e:
            return Protocol.create_response(STATUS_ERROR, message=str(e))
    
    # ========== API Implementations ==========
    
    def _create_account(self, data):
        """Create new seller account"""
        username = data.get('username')
        password = data.get('password')
        seller_name = data.get('seller_name')
        
        # Validate input
        if not username or not password or not seller_name:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Username, password, and seller name are required"
            )
        
        if len(seller_name) > MAX_NAME_LENGTH:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message=f"Seller name must be <= {MAX_NAME_LENGTH} characters"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_CREATE_SELLER,
            data={
                'username': username,
                'password': password,
                'seller_name': seller_name
            }
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _login(self, data):
        """Login seller"""
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Username and password are required"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_LOGIN_SELLER,
            data={'username': username, 'password': password}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _logout(self, session_id):
        """Logout seller"""
        if not session_id:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Session ID required"
            )
        
        # Forward to customer DB
        request = Protocol.create_request(
            OP_LOGOUT_SELLER,
            data={'session_id': session_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _get_rating(self, seller_id):
        """Get seller rating"""
        request = Protocol.create_request(
            OP_GET_SELLER_RATING,
            data={'seller_id': seller_id}
        )
        
        return self._db_request(
            self.customer_db_host,
            self.customer_db_port,
            request
        )
    
    def _register_item(self, seller_id, data):
        """Register item for sale"""
        name = data.get('name')
        category = data.get('category')
        keywords = data.get('keywords', [])
        condition = data.get('condition')
        price = data.get('price')
        quantity = data.get('quantity')
        
        # Validate input
        if not name or category is None or condition is None or price is None or quantity is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Name, category, condition, price, and quantity are required"
            )
        
        if len(name) > MAX_NAME_LENGTH:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message=f"Item name must be <= {MAX_NAME_LENGTH} characters"
            )
        
        if len(keywords) > MAX_KEYWORDS:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message=f"Maximum {MAX_KEYWORDS} keywords allowed"
            )
        
        for keyword in keywords:
            if len(keyword) > MAX_KEYWORD_LENGTH:
                return Protocol.create_response(
                    STATUS_INVALID_REQUEST,
                    message=f"Each keyword must be <= {MAX_KEYWORD_LENGTH} characters"
                )
        
        if condition not in [CONDITION_NEW, CONDITION_USED]:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message=f"Condition must be '{CONDITION_NEW}' or '{CONDITION_USED}'"
            )
        
        try:
            price = float(price)
            quantity = int(quantity)
            category = int(category)
            if price < 0 or quantity < 0 or category < 1 or category > 8:
                raise ValueError()
        except:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Invalid price, quantity, or category"
            )
        
        # Forward to product DB
        request = Protocol.create_request(
            OP_REGISTER_ITEM,
            data={
                'seller_id': seller_id,
                'name': name,
                'category': category,
                'keywords': keywords,
                'condition': condition,
                'price': price,
                'quantity': quantity
            }
        )
        
        return self._db_request(
            self.product_db_host,
            self.product_db_port,
            request
        )
    
    def _change_price(self, seller_id, data):
        """Change item price"""
        item_id = data.get('item_id')
        new_price = data.get('new_price')
        
        if not item_id or new_price is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Item ID and new price are required"
            )
        
        try:
            new_price = float(new_price)
            if new_price < 0:
                raise ValueError()
        except:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Invalid price"
            )
        
        # Forward to product DB
        request = Protocol.create_request(
            OP_UPDATE_ITEM_PRICE,
            data={
                'item_id': item_id,
                'seller_id': seller_id,
                'new_price': new_price
            }
        )
        
        return self._db_request(
            self.product_db_host,
            self.product_db_port,
            request
        )
    
    def _update_units(self, seller_id, data):
        """Update units for sale (remove units)"""
        item_id = data.get('item_id')
        quantity_to_remove = data.get('quantity')
        
        if not item_id or quantity_to_remove is None:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Item ID and quantity are required"
            )
        
        try:
            quantity_to_remove = int(quantity_to_remove)
            if quantity_to_remove < 0:
                raise ValueError()
        except:
            return Protocol.create_response(
                STATUS_INVALID_REQUEST,
                message="Invalid quantity"
            )
        
        # Forward to product DB
        request = Protocol.create_request(
            OP_UPDATE_ITEM_QUANTITY,
            data={
                'item_id': item_id,
                'seller_id': seller_id,
                'quantity_to_remove': quantity_to_remove
            }
        )
        
        return self._db_request(
            self.product_db_host,
            self.product_db_port,
            request
        )
    
    def _display_items(self, seller_id):
        """Display all items for this seller"""
        request = Protocol.create_request(
            OP_GET_SELLER_ITEMS,
            data={'seller_id': seller_id}
        )
        
        return self._db_request(
            self.product_db_host,
            self.product_db_port,
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
        
        print(f"Seller Frontend Server started on {self.host}:{self.port}")
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
            print("\nShutting down Seller Frontend Server...")
        finally:
            server_socket.close()
            self.running = False


def main():
    """Main entry point"""
    frontend = SellerFrontend(
        host=config.SELLER_FRONTEND_HOST,
        port=config.SELLER_FRONTEND_PORT
    )
    frontend.start()


if __name__ == '__main__':
    main()
