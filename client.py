import socket
import sys
from utils import send_message, recv_message

class TestClient:
    def __init__(self, server_host, server_port=5001):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
    
    def connect(self):
        """Connect to the server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            print(f"[CONNECTED] Connected to {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            print(f"[ERROR] Could not connect: {e}")
            return False
    
    def send_request(self, api, params):
        """Send a request to the server and get response"""
        request = {
            "type": "request",
            "api": api,
            "session_id": None,
            "params": params
        }
        
        try:
            send_message(self.socket, request)
            response = recv_message(self.socket)
            return response
        except Exception as e:
            print(f"[ERROR] Communication error: {e}")
            return None
    
    def close(self):
        """Close the connection"""
        if self.socket:
            self.socket.close()
            print("[DISCONNECTED] Connection closed")
    
    def run_tests(self):
        """Run a series of test requests"""
        print("\n" + "="*50)
        print("Running Test Requests")
        print("="*50 + "\n")
        
        # Test 1: CreateAccount
        print("[TEST 1] CreateAccount")
        response = self.send_request("CreateAccount", {
            "account_type": "seller",
            "username": "alice",
            "password": "pass123"
        })
        if response:
            print(f"Response: {response}\n")
        
        # Test 2: Login
        print("[TEST 2] Login")
        response = self.send_request("Login", {
            "username": "alice",
            "password": "pass123"
        })
        if response:
            print(f"Response: {response}\n")
        
        # Test 3: Echo (custom test)
        print("[TEST 3] Echo")
        response = self.send_request("Echo", {
            "message": "Hello from client!"
        })
        if response:
            print(f"Response: {response}\n")
        
        # Test 4: Unknown API (error test)
        print("[TEST 4] Unknown API (should return error)")
        response = self.send_request("NonExistentAPI", {})
        if response:
            print(f"Response: {response}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_client.py <server_ip> [server_port]")
        print("Example: python3 test_client.py 192.168.1.100")
        print("Example: python3 test_client.py 192.168.1.100 5001")
        sys.exit(1)
    
    server_host = sys.argv[1]
    server_port = int(sys.argv[2]) if len(sys.argv) > 2 else 5001
    
    client = TestClient(server_host, server_port)
    
    if client.connect():
        client.run_tests()
        client.close()


if __name__ == '__main__':
    main()