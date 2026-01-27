import json
import struct
import socket

def send_message(sock, message_dict):
    """
    Send a JSON message over TCP with length prefix.
    
    Args:
        sock: socket object
        message_dict: Python dictionary to send
    """
    json_str = json.dumps(message_dict)
    json_bytes = json_str.encode('utf-8')
    length = len(json_bytes)
    
    # Send 4-byte length prefix + message
    data = struct.pack('I', length) + json_bytes
    sock.sendall(data)
    print(f"[SENT] {message_dict}")


def recv_message(sock):
    """
    Receive a length-prefixed JSON message from TCP.
    
    Args:
        sock: socket object
    
    Returns:
        Python dictionary, or None if connection closed
    """
    # Read 4-byte length prefix
    length_bytes = b''
    while len(length_bytes) < 4:
        chunk = sock.recv(4 - len(length_bytes))
        if not chunk:
            return None  # Connection closed
        length_bytes += chunk
    
    length = struct.unpack('I', length_bytes)[0]
    
    # Read the JSON message
    json_bytes = b''
    while len(json_bytes) < length:
        chunk = sock.recv(length - len(json_bytes))
        if not chunk:
            return None  # Connection closed
        json_bytes += chunk
    
    message = json.loads(json_bytes.decode('utf-8'))
    print(f"[RECV] {message}")
    return message