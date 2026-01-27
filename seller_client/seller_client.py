"""
seller_client.py - Low-Level TCP Connection Management for Sellers

This module handles all TCP socket operations for seller clients:
- Establishing connections to the seller server
- Sending/receiving raw bytes
- Connection lifecycle (connect, disconnect, reconnect)
- Message framing (length-prefixed protocol)

This layer knows NOTHING about business logic - it just sends and receives data.
Note: This is nearly identical to buyer_client.py - in practice, you might
create a shared BaseClient class that both inherit from.
"""

import socket
import json
import struct
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Raised when connection to server fails."""
    pass


class SellerClient:
    """
    Low-level TCP client for seller-server communication.
    
    Handles the raw socket operations and message protocol.
    Does NOT know about specific APIs like Login, RegisterItem, etc.
    """
    
    HEADER_SIZE = 4  # 4 bytes for message length (unsigned int)
    RECV_BUFFER = 4096
    
    def __init__(self, host: str, port: int, timeout: float = 30.0):
        """
        Initialize the client with server address.
        
        Args:
            host: Server hostname or IP address
            port: Server port number
            timeout: Socket timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._connected = False
    
    def connect(self) -> None:
        """
        Establish TCP connection to the seller server.
        
        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            logger.warning("Already connected, disconnecting first")
            self.disconnect()
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._connected = True
            logger.info(f"Connected to seller server at {self.host}:{self.port}")
        except socket.error as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")
    
    def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._socket:
            try:
                self._socket.close()
            except socket.error:
                pass  # Ignore errors during close
            finally:
                self._socket = None
                self._connected = False
                logger.info("Disconnected from seller server")
    
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connected and self._socket is not None
    
    def send_request(self, request: dict) -> dict:
        """
        Send a request and receive the response.
        
        This is the core method that other layers use.
        Handles message serialization and the length-prefix protocol.
        
        Args:
            request: Dictionary containing the request data
            
        Returns:
            Dictionary containing the server response
            
        Raises:
            ConnectionError: If not connected or communication fails
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to server")
        
        try:
            # Serialize request to JSON bytes
            request_bytes = json.dumps(request).encode('utf-8')
            
            # Send length header + message
            header = struct.pack('!I', len(request_bytes))
            self._socket.sendall(header + request_bytes)
            logger.debug(f"Sent request: {request['type']}")
            
            # Receive response
            response = self._receive_message()
            logger.debug(f"Received response for: {request['type']}")
            return response
            
        except socket.timeout:
            raise ConnectionError("Request timed out")
        except socket.error as e:
            self._connected = False
            raise ConnectionError(f"Communication error: {e}")
    
    def _receive_message(self) -> dict:
        """
        Receive a length-prefixed message from the server.
        
        Returns:
            Parsed JSON response as dictionary
        """
        # First, receive the 4-byte length header
        header_data = self._recv_exact(self.HEADER_SIZE)
        message_length = struct.unpack('!I', header_data)[0]
        
        # Then receive the actual message
        message_data = self._recv_exact(message_length)
        
        # Parse JSON
        return json.loads(message_data.decode('utf-8'))
    
    def _recv_exact(self, num_bytes: int) -> bytes:
        """
        Receive exactly num_bytes from the socket.
        
        Args:
            num_bytes: Number of bytes to receive
            
        Returns:
            Received bytes
            
        Raises:
            ConnectionError: If connection closed prematurely
        """
        chunks = []
        bytes_received = 0
        
        while bytes_received < num_bytes:
            chunk = self._socket.recv(min(num_bytes - bytes_received, self.RECV_BUFFER))
            if not chunk:
                raise ConnectionError("Connection closed by server")
            chunks.append(chunk)
            bytes_received += len(chunk)
        
        return b''.join(chunks)
    
    def __enter__(self):
        """Context manager entry - connect to server."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect from server."""
        self.disconnect()
        return False


# Example usage (if run directly for testing)
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Example: Connect and send a raw request
    client = SellerClient("localhost", 5002)
    
    try:
        client.connect()
        
        # Send a raw request (normally API layer does this)
        response = client.send_request({
            "type": "PING",
            "data": {}
        })
        print(f"Response: {response}")
        
    finally:
        client.disconnect()