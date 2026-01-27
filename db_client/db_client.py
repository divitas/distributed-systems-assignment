"""
db_client.py - Database Client for Backend Communication

This module provides a TCP client for the frontend servers (Buyer Server,
Seller Server) to communicate with the backend databases (Customer DB,
Product DB).

The protocol is the same length-prefixed JSON used throughout the system.
"""

import socket
import json
import struct
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DBConnectionError(Exception):
    """Raised when database connection fails."""
    pass


class DatabaseClient:
    """
    TCP client for communicating with backend database servers.
    
    Used by frontend servers to query Customer DB and Product DB.
    Supports context manager for automatic connection handling.
    """
    
    HEADER_SIZE = 4
    RECV_BUFFER = 4096
    
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        """
        Initialize database client.
        
        Args:
            host: Database server hostname
            port: Database server port
            timeout: Socket timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
    
    def connect(self) -> None:
        """Establish connection to database server."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            logger.debug(f"Connected to database at {self.host}:{self.port}")
        except socket.error as e:
            raise DBConnectionError(f"Failed to connect to database: {e}")
    
    def disconnect(self) -> None:
        """Close connection to database server."""
        if self._socket:
            try:
                self._socket.close()
            except socket.error:
                pass
            finally:
                self._socket = None
    
    def query(self, operation: str, data: dict) -> dict:
        """
        Send a query to the database and return the response.
        
        Args:
            operation: The database operation to perform
            data: Operation parameters
            
        Returns:
            Response dictionary from the database
            
        Raises:
            DBConnectionError: If communication fails
        """
        if not self._socket:
            raise DBConnectionError("Not connected to database")
        
        try:
            # Build request
            request = {
                "operation": operation,
                "data": data
            }
            
            # Send request
            request_bytes = json.dumps(request).encode('utf-8')
            header = struct.pack('!I', len(request_bytes))
            self._socket.sendall(header + request_bytes)
            
            # Receive response
            response_header = self._recv_exact(self.HEADER_SIZE)
            if not response_header:
                raise DBConnectionError("Database closed connection")
            
            response_length = struct.unpack('!I', response_header)[0]
            response_data = self._recv_exact(response_length)
            
            if not response_data:
                raise DBConnectionError("Database closed connection")
            
            return json.loads(response_data.decode('utf-8'))
            
        except socket.timeout:
            raise DBConnectionError("Database request timed out")
        except socket.error as e:
            raise DBConnectionError(f"Database communication error: {e}")
        except json.JSONDecodeError as e:
            raise DBConnectionError(f"Invalid response from database: {e}")
    
    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        """Receive exactly num_bytes from socket."""
        chunks = []
        bytes_received = 0
        
        while bytes_received < num_bytes:
            chunk = self._socket.recv(min(num_bytes - bytes_received, self.RECV_BUFFER))
            if not chunk:
                return None
            chunks.append(chunk)
            bytes_received += len(chunk)
        
        return b''.join(chunks)
    
    def __enter__(self):
        """Context manager entry - connect to database."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect from database."""
        self.disconnect()
        return False


# Example usage
if __name__ == "__main__":
    # Test connection to Customer DB
    logging.basicConfig(level=logging.DEBUG)
    
    with DatabaseClient("localhost", 5003) as db:
        result = db.query("PING", {})
        print(f"Customer DB response: {result}")
    
    with DatabaseClient("localhost", 5004) as db:
        result = db.query("PING", {})
        print(f"Product DB response: {result}")