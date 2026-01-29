"""
Enhanced Database Client with Connection Pooling - FIXED VERSION
Supports context manager protocol for 'with' statements
"""

import socket
import queue
import threading
import time
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DBConnectionError(Exception):
    """Custom exception for database connection errors"""
    pass

class ConnectionPool:
    """Thread-safe connection pool for TCP connections"""
    
    def __init__(self, host, port, pool_size=20, max_overflow=10):
        self.host = host
        self.port = port
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        
        self.pool = queue.Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        self.active_connections = 0
        self.total_created = 0
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'pool_hits': 0,
            'pool_misses': 0,
            'connection_errors': 0
        }
        
        # Pre-populate pool
        self._initialize_pool()
        
        logger.info(f"ConnectionPool initialized for {host}:{port} (size={pool_size}, overflow={max_overflow})")
    
    def _initialize_pool(self):
        """Create initial pool of connections"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            if conn:
                try:
                    self.pool.put_nowait(conn)
                    with self.lock:
                        self.active_connections += 1
                except queue.Full:
                    conn.close()
    
    def _create_connection(self):
        """Create a new TCP connection"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.settimeout(30)
            sock.connect((self.host, self.port))
            
            with self.lock:
                self.total_created += 1
            
            logger.debug(f"Created new connection to {self.host}:{self.port}")
            return sock
        
        except Exception as e:
            logger.error(f"Failed to create connection to {self.host}:{self.port}: {e}")
            with self.lock:
                self.stats['connection_errors'] += 1
            return None
    
    def _is_connection_alive(self, conn):
        """Check if connection is still alive using non-blocking send"""
        try:
            # Try to send empty data with MSG_PEEK
            conn.setblocking(False)
            try:
                conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
            except BlockingIOError:
                # No data available, connection is alive
                pass
            conn.setblocking(True)
            return True
        except Exception:
            return False
    
    def get_connection(self, timeout=5):
        """
        Get a connection from the pool
        
        Args:
            timeout: Maximum time to wait for a connection (seconds)
            
        Returns:
            socket connection or None
        """
        with self.lock:
            self.stats['total_requests'] += 1
        
        start_time = time.time()
        
        # Try to get from pool first
        try:
            conn = self.pool.get(timeout=timeout)
            
            # Verify connection is alive
            if self._is_connection_alive(conn):
                with self.lock:
                    self.stats['pool_hits'] += 1
                return conn
            else:
                # Connection is dead, close it and create new one
                logger.debug("Stale connection detected, creating new one")
                conn.close()
                with self.lock:
                    self.active_connections -= 1
        
        except queue.Empty:
            # Pool is empty
            pass
        
        # Pool exhausted or connection was stale, try to create new one
        with self.lock:
            if self.active_connections < self.pool_size + self.max_overflow:
                self.stats['pool_misses'] += 1
                self.active_connections += 1
                conn = self._create_connection()
                
                if conn:
                    return conn
                else:
                    self.active_connections -= 1
        
        # Wait time exceeded
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            raise TimeoutError(f"Could not acquire connection within {timeout}s")
        
        # Recursive retry with remaining time
        return self.get_connection(timeout - elapsed)
    
    def return_connection(self, conn, close=False):
        """
        Return a connection to the pool
        
        Args:
            conn: The connection to return
            close: If True, force close the connection instead of pooling
        """
        if close or not conn:
            if conn:
                conn.close()
            with self.lock:
                self.active_connections -= 1
            return
        
        try:
            # Try to return to pool
            self.pool.put_nowait(conn)
        except queue.Full:
            # Pool is full, close the connection
            conn.close()
            with self.lock:
                self.active_connections -= 1
    
    def close_all(self):
        """Close all connections in the pool"""
        logger.info(f"Closing connection pool for {self.host}:{self.port}")
        
        # Close all pooled connections
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
        
        with self.lock:
            self.active_connections = 0
    
    def get_stats(self):
        """Get connection pool statistics"""
        with self.lock:
            stats = self.stats.copy()
            stats['pool_size'] = self.pool.qsize()
            stats['active_connections'] = self.active_connections
            stats['total_created'] = self.total_created
            
            if stats['total_requests'] > 0:
                stats['hit_rate'] = stats['pool_hits'] / stats['total_requests']
            else:
                stats['hit_rate'] = 0.0
        
        return stats


class DatabaseClient:
    """
    Client for communicating with backend database servers
    Uses connection pooling for better performance
    Supports context manager protocol for 'with' statements
    """
    
    def __init__(self, host, port, pool_size=20, max_overflow=10):
        self.host = host
        self.port = port
        self.connection_pool = ConnectionPool(host, port, pool_size=pool_size, max_overflow=max_overflow)
        logger.info(f"DatabaseClient initialized for {host}:{port}")
    
    def __enter__(self):
        """Context manager entry - returns self"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes connections"""
        # Don't close the pool on exit, just return
        # The pool should remain open for reuse
        return False  # Don't suppress exceptions
    
    def send_request(self, request_data, timeout=30):
        """
        Send a request to the database server
        
        Args:
            request_data: Dictionary to send as JSON
            timeout: Request timeout in seconds
            
        Returns:
            Response dictionary or None on error
        """
        conn = None
        close_conn = False
        
        try:
            # Get connection from pool
            conn = self.connection_pool.get_connection(timeout=5)
            
            if not conn:
                logger.error("Failed to acquire connection")
                return {'status': 'error', 'message': 'Connection pool exhausted'}
            
            # Serialize request
            request_json = json.dumps(request_data)
            request_bytes = request_json.encode('utf-8')
            
            # Send length prefix (4 bytes) + data
            length_prefix = len(request_bytes).to_bytes(4, byteorder='big')
            conn.sendall(length_prefix + request_bytes)
            
            # Receive length prefix
            length_data = self._recv_exact(conn, 4, timeout)
            if not length_data:
                logger.error("Connection closed while reading response length")
                close_conn = True
                return {'status': 'error', 'message': 'Connection closed'}
            
            response_length = int.from_bytes(length_data, byteorder='big')
            
            # Receive response data
            response_bytes = self._recv_exact(conn, response_length, timeout)
            if not response_bytes:
                logger.error("Connection closed while reading response data")
                close_conn = True
                return {'status': 'error', 'message': 'Connection closed'}
            
            # Deserialize response
            response_json = response_bytes.decode('utf-8')
            response_data = json.loads(response_json)
            
            return response_data
        
        except socket.timeout:
            logger.error(f"Request timeout after {timeout}s")
            close_conn = True
            return {'status': 'error', 'message': 'Request timeout'}
        
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            close_conn = True
            return {'status': 'error', 'message': str(e)}
        
        finally:
            if conn:
                self.connection_pool.return_connection(conn, close=close_conn)
    
    def query(self, operation, data, timeout=30):
        """
        Send a query to the database server (convenience method used by servers)
        
        Args:
            operation: Operation type (string)
            data: Data dictionary for the operation
            timeout: Request timeout in seconds
            
        Returns:
            Response dictionary
        """
        request_data = {
            'operation': operation,
            'data': data
        }
        return self.send_request(request_data, timeout)
    
    def _recv_exact(self, conn, num_bytes, timeout):
        """
        Receive exactly num_bytes from socket
        
        Args:
            conn: Socket connection
            num_bytes: Number of bytes to receive
            timeout: Timeout in seconds
            
        Returns:
            Received bytes or None on error
        """
        conn.settimeout(timeout)
        data = b''
        
        while len(data) < num_bytes:
            try:
                chunk = conn.recv(num_bytes - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                logger.error("Timeout while receiving data")
                return None
        
        return data
    
    def close(self):
        """Close the database client and all connections"""
        self.connection_pool.close_all()
    
    def get_stats(self):
        """Get connection pool statistics"""
        return self.connection_pool.get_stats()


# Convenience methods for common operations

class CustomerDatabaseClient(DatabaseClient):
    """Client specifically for Customer Database"""
    
    def create_seller(self, username, password):
        request = {
            'action': 'create_seller',
            'username': username,
            'password': password
        }
        return self.send_request(request)
    
    def create_buyer(self, username, password):
        request = {
            'action': 'create_buyer',
            'username': username,
            'password': password
        }
        return self.send_request(request)
    
    def login_seller(self, username, password):
        request = {
            'action': 'login_seller',
            'username': username,
            'password': password
        }
        return self.send_request(request)
    
    def login_buyer(self, username, password):
        request = {
            'action': 'login_buyer',
            'username': username,
            'password': password
        }
        return self.send_request(request)
    
    def validate_session(self, session_id, user_type):
        request = {
            'action': 'validate_session',
            'session_id': session_id,
            'user_type': user_type
        }
        return self.send_request(request)
    
    def get_session(self, session_id):
        request = {
            'action': 'get_session',
            'session_id': session_id
        }
        return self.send_request(request)
    
    def update_session(self, session_id, updates):
        request = {
            'action': 'update_session',
            'session_id': session_id,
            'updates': updates
        }
        return self.send_request(request)
    
    def delete_session(self, session_id):
        request = {
            'action': 'delete_session',
            'session_id': session_id
        }
        return self.send_request(request)
    
    def get_seller_info(self, seller_id):
        request = {
            'action': 'get_seller_info',
            'seller_id': seller_id
        }
        return self.send_request(request)
    
    def get_buyer_info(self, buyer_id):
        request = {
            'action': 'get_buyer_info',
            'buyer_id': buyer_id
        }
        return self.send_request(request)
    
    def update_seller_feedback(self, seller_id, thumbs_up_delta, thumbs_down_delta):
        request = {
            'action': 'update_seller_feedback',
            'seller_id': seller_id,
            'thumbs_up_delta': thumbs_up_delta,
            'thumbs_down_delta': thumbs_down_delta
        }
        return self.send_request(request)


class ProductDatabaseClient(DatabaseClient):
    """Client specifically for Product Database"""
    
    def register_item(self, seller_id, item_data):
        request = {
            'action': 'register_item',
            'seller_id': seller_id,
            'item_data': item_data
        }
        return self.send_request(request)
    
    def search_items(self, category=None, keywords=None):
        request = {
            'action': 'search_items',
            'category': category,
            'keywords': keywords
        }
        return self.send_request(request)
    
    def get_item(self, item_id):
        request = {
            'action': 'get_item',
            'item_id': item_id
        }
        return self.send_request(request)
    
    def update_item_price(self, seller_id, item_id, new_price):
        request = {
            'action': 'update_item_price',
            'seller_id': seller_id,
            'item_id': item_id,
            'new_price': new_price
        }
        return self.send_request(request)
    
    def update_item_quantity(self, item_id, quantity_delta):
        request = {
            'action': 'update_item_quantity',
            'item_id': item_id,
            'quantity_delta': quantity_delta
        }
        return self.send_request(request)
    
    def get_items_by_seller(self, seller_id):
        request = {
            'action': 'get_items_by_seller',
            'seller_id': seller_id
        }
        return self.send_request(request)


if __name__ == "__main__":
    # Test the connection pool
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python db_client.py <host> <port>")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    
    print(f"Testing connection to {host}:{port}")
    
    # Test context manager
    with DatabaseClient(host, port) as client:
        # Send test request
        response = client.send_request({'action': 'ping'})
        print(f"Response: {response}")
        
        # Print stats
        stats = client.get_stats()
        print(f"\nConnection Pool Stats:")
        for key, value in stats.items():
            print(f"  {key}: {value}")