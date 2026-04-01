"""
Protocol module for message serialization and deserialization
Handles conversion between Python objects and network messages
"""

import json
import pickle
from shared.constants import MESSAGE_DELIMITER


class Protocol:
    """
    Handles message serialization/deserialization for TCP communication
    Uses JSON for better readability and debugging
    """
    
    @staticmethod
    def encode_message(message_dict):
        """
        Encode a dictionary message to bytes for network transmission
        
        Args:
            message_dict: Dictionary containing message data
            
        Returns:
            bytes: Encoded message with delimiter
        """
        try:
            # Convert to JSON string
            json_str = json.dumps(message_dict)
            # Add delimiter and encode to bytes
            message = (json_str + MESSAGE_DELIMITER).encode('utf-8')
            return message
        except Exception as e:
            raise ValueError(f"Failed to encode message: {e}")
    
    @staticmethod
    def decode_message(message_bytes):
        """
        Decode bytes message to dictionary
        
        Args:
            message_bytes: Bytes containing message data
            
        Returns:
            dict: Decoded message dictionary
        """
        try:
            # Decode bytes to string
            message_str = message_bytes.decode('utf-8')
            # Remove delimiter if present
            message_str = message_str.replace(MESSAGE_DELIMITER, '')
            # Parse JSON
            message_dict = json.loads(message_str)
            return message_dict
        except Exception as e:
            raise ValueError(f"Failed to decode message: {e}")
    
    @staticmethod
    def send_message(sock, message_dict):
        """
        Send a message through a socket
        
        Args:
            sock: Socket object
            message_dict: Dictionary to send
            
        Returns:
            bool: True if successful
        """
        try:
            encoded = Protocol.encode_message(message_dict)
            sock.sendall(encoded)
            return True
        except Exception as e:
            raise IOError(f"Failed to send message: {e}")
    
    @staticmethod
    def receive_message(sock, buffer_size=8192):
        """
        Receive a complete message from socket
        Handles partial receives by accumulating data until delimiter is found
        
        Args:
            sock: Socket object
            buffer_size: Size of receive buffer
            
        Returns:
            dict: Decoded message dictionary
        """
        try:
            accumulated_data = b''
            delimiter_bytes = MESSAGE_DELIMITER.encode('utf-8')
            
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    raise ConnectionError("Connection closed by peer")
                
                accumulated_data += chunk
                
                # Check if we have received the complete message
                if delimiter_bytes in accumulated_data:
                    # Extract the message (everything before delimiter)
                    message_bytes = accumulated_data.split(delimiter_bytes)[0]
                    return Protocol.decode_message(message_bytes)
                    
        except Exception as e:
            raise IOError(f"Failed to receive message: {e}")
    
    @staticmethod
    def create_response(status, data=None, message=""):
        """
        Create a standardized response message
        
        Args:
            status: Response status (SUCCESS, ERROR, etc.)
            data: Optional data payload
            message: Optional message string
            
        Returns:
            dict: Response message dictionary
        """
        response = {
            'status': status,
            'message': message
        }
        if data is not None:
            response['data'] = data
        return response
    
    @staticmethod
    def create_request(operation, data=None, session_id=None):
        """
        Create a standardized request message
        
        Args:
            operation: Operation code
            data: Optional data payload
            session_id: Optional session ID
            
        Returns:
            dict: Request message dictionary
        """
        request = {
            'operation': operation
        }
        if data is not None:
            request['data'] = data
        if session_id is not None:
            request['session_id'] = session_id
        return request


def test_protocol():
    """Test the protocol encoding/decoding"""
    # Test message
    test_msg = {
        'operation': 'TEST',
        'data': {'key': 'value', 'number': 42},
        'status': 'SUCCESS'
    }
    
    # Encode
    encoded = Protocol.encode_message(test_msg)
    print(f"Encoded: {encoded}")
    
    # Decode
    decoded = Protocol.decode_message(encoded)
    print(f"Decoded: {decoded}")
    
    assert decoded == test_msg, "Protocol test failed!"
    print("Protocol test passed!")


if __name__ == '__main__':
    test_protocol()
