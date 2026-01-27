import socket
import threading
from utils import send_message, recv_message

class TestServer:
    def __init__(self, host='0.0.0.0', port=5001):
        self.host = host
        self.port = port
        self.server_socket = None
    
    def handle_client(self, client_socket, addr):
        """Handle a single client connection"""
        print(f"[NEW CONNECTION] {addr} connected")
        
        try:
            while True:
                # Receive message from client
                request = recv_message(client_socket)
                
                if not request:
                    print(f"[DISCONNECTED] {addr}")
                    break
                
                # Process the request and send response
                response = self.process_request(request)
                send_message(client_socket, response)
                
        except Exception as e:
            print(f"[ERROR] {addr}: {e}")
        finally:
            client_socket.close()
    
    def process_request(self, request):
        """Process client request and return response"""
        api = request.get('api')
        params = request.get('params', {})
        
        print(f"[PROCESSING] API: {api}, Params: {params}")
        
        # Simple echo-like responses for testing
        if api == "CreateAccount":
            return {
                "type": "response",
                "status": "success",
                "data": {
                    "user_id": 123,
                    "message": f"Account created for {params.get('username')}"
                }
            }
        
        elif api == "Login":
            return {
                "type": "response",
                "status": "success",
                "data": {
                    "session_id": "test-session-abc-123",
                    "user_id": 123,
                    "message": f"Logged in as {params.get('username')}"
                }
            }
        
        elif api == "Echo":
            return {
                "type": "response",
                "status": "success",
                "data": {
                    "message": f"Echo: {params.get('message', 'No message')}"
                }
            }
        
        else:
            return {
                "type": "response",
                "status": "error",
                "error": {
                    "code": "UNKNOWN_API",
                    "message": f"Unknown API: {api}"
                }
            }
    
    def start(self):
        """Start the server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Allow reuse of address (helpful during development)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"[STARTED] Server listening on {self.host}:{self.port}")
        print(f"[INFO] Waiting for connections...")
        
        try:
            while True:
                # Accept new connection
                client_socket, addr = self.server_socket.accept()
                
                # Handle client in a new thread
                thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, addr)
                )
                thread.daemon = True
                thread.start()
                
                print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
                
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Server shutting down...")
        finally:
            if self.server_socket:
                self.server_socket.close()


if __name__ == '__main__':
    # You can change the port if needed
    server = TestServer(host='0.0.0.0', port=5001)
    server.start()