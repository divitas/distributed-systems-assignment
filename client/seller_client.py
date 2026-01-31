"""
Seller CLI Client
Interactive command-line interface for sellers
"""

import socket
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.protocol import Protocol
from shared.constants import *
from shared.utils import format_feedback, format_item_display


class SellerClient:
    """Seller CLI Client"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.session_id = None
        self.seller_id = None
        self.seller_name = None
    
    def connect(self):
        """Connect to seller frontend server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"Error connecting to server: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from server"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def restore_session(self): #JN added
        """Try to restore existing session using session_id"""
        if not self.session_id:
            return False
        
        response = self.send_request(
            API_SELLER_RESTORE_SESSION,
            {'session_id': self.session_id}
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            self.seller_id = response['data']['seller_id']
            self.seller_name = response['data']['seller_name']
            print(f"\n✓ Session restored. Welcome back, {self.seller_name}!")
            return True
        else:
            # Session invalid/expired, clear it
            self.session_id = None
            return False
    
    def send_request(self, operation, data=None):
        """Send request to server and receive response"""
        try:
            request = Protocol.create_request(operation, data, self.session_id)
            Protocol.send_message(self.socket, request)
            response = Protocol.receive_message(self.socket)
            return response
        except Exception as e:
            print(f"Communication error: {e}")
            return None
    
    def is_session_expired(self, response):
        """Check if response indicates session expired"""
        if response and response.get('status') != STATUS_SUCCESS:
            message = response.get('message', '').lower()
            if 'session expired' in message or 'invalid session' in message:
                return True
        return False
    
    # ========== API Methods ==========
    
    def create_account(self):
        """Create a new seller account"""
        print("\n=== Create Seller Account ===")
        username = input("Enter username: ").strip()
        password = input("Enter password: ").strip()
        seller_name = input("Enter your name (display name): ").strip()
        
        response = self.send_request(
            API_SELLER_CREATE_ACCOUNT,
            {
                'username': username,
                'password': password,
                'seller_name': seller_name
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            seller_id = response['data']['seller_id']
            print(f"\n✓ Account created successfully!")
            print(f"Your Seller ID: {seller_id}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
        
        return response
    
    def login(self):
        """Login to seller account"""
        print("\n=== Seller Login ===")
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        
        response = self.send_request(
            API_SELLER_LOGIN,
            {
                'username': username,
                'password': password
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            self.session_id = response['data']['session_id']
            self.seller_id = response['data']['seller_id']
            self.seller_name = response['data']['seller_name']
            print(f"\n✓ Welcome, {self.seller_name}!")
            print(f"Seller ID: {self.seller_id}")
            return True
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Login failed: {message}")
            return False
    
    def logout(self):
        """Logout from seller account"""
        if not self.session_id:
            print("Not logged in.")
            return
        
        response = self.send_request(API_SELLER_LOGOUT)
        
        if response and response['status'] == STATUS_SUCCESS:
            print("\n✓ Logged out successfully")
            self.session_id = None
            self.seller_id = None
            self.seller_name = None
        else:
            print("\n✗ Logout failed")
    
    def get_rating(self):
        """Get seller rating"""
        response = self.send_request(API_SELLER_GET_RATING)
        
        if response and response['status'] == STATUS_SUCCESS:
            thumbs_up = response['data']['thumbs_up']
            thumbs_down = response['data']['thumbs_down']
            print(f"\nYour Rating: {format_feedback(thumbs_up, thumbs_down)}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
        
        return response
    
    def register_item(self):
        """Register a new item for sale"""
        print("\n=== Register New Item ===")
        
        name = input("Item name: ").strip()
        
        print("\nCategories:")
        for cat_id, cat_name in config.ITEM_CATEGORIES.items():
            print(f"  {cat_id}. {cat_name}")
        category = input("Select category (1-8): ").strip()
        
        print("Enter up to 5 keywords (comma-separated):")
        keywords_input = input("Keywords: ").strip()
        keywords = [k.strip() for k in keywords_input.split(',') if k.strip()][:5]
        
        print("\nCondition:")
        print("  1. New")
        print("  2. Used")
        condition_choice = input("Select condition (1 or 2): ").strip()
        condition = CONDITION_NEW if condition_choice == '1' else CONDITION_USED
        
        price = input("Price ($): ").strip()
        quantity = input("Quantity: ").strip()
        
        try:
            category = int(category)
            price = float(price)
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid input for category, price, or quantity")
            return None
        
        response = self.send_request(
            API_SELLER_REGISTER_ITEM,
            {
                'name': name,
                'category': category,
                'keywords': keywords,
                'condition': condition,
                'price': price,
                'quantity': quantity
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            item_id = response['data']['item_id']
            print(f"\n✓ Item registered successfully!")
            print(f"Item ID: {item_id}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
        
        return response
    
    def change_price(self):
        """Change price of an item"""
        print("\n=== Change Item Price ===")
        item_id = input("Item ID: ").strip()
        new_price = input("New price ($): ").strip()
        
        try:
            new_price = float(new_price)
        except ValueError:
            print("\n✗ Invalid price")
            return None
        
        response = self.send_request(
            API_SELLER_CHANGE_PRICE,
            {
                'item_id': item_id,
                'new_price': new_price
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            print(f"\n✓ Price updated successfully")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
        
        return response
    
    def update_units(self):
        """Update (remove) units for sale"""
        print("\n=== Remove Units from Sale ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity to remove: ").strip()
        
        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return None
        
        response = self.send_request(
            API_SELLER_UPDATE_UNITS,
            {
                'item_id': item_id,
                'quantity': quantity
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            print(f"\n✓ {response.get('message', 'Units updated')}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
        
        return response
    
    def display_items(self):
        """Display all items for sale"""
        response = self.send_request(API_SELLER_DISPLAY_ITEMS)
        
        if response and response['status'] == STATUS_SUCCESS:
            items = response['data']['items']
            
            if not items:
                print("\nYou have no items for sale.")
            else:
                print(f"\n=== Your Items ({len(items)} total) ===")
                for i, item in enumerate(items, 1):
                    print(f"\n--- Item {i} ---")
                    print(format_item_display(item))
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
        
        return response
    
    # ========== Main Menu ==========
    
    def show_menu(self):
        """Show main menu"""
        print("\n" + "="*50)
        print("SELLER MENU")
        print("="*50)
        print("1. Get My Rating")
        print("2. Register Item for Sale")
        print("3. Change Item Price")
        print("4. Remove Units from Sale")
        print("5. Display My Items")
        print("6. Logout")
        print("0. Exit")
        print("="*50)
    
    def run(self): #JN modified
        """Run the seller client"""
        print("\n" + "="*50)
        print("ONLINE MARKETPLACE - SELLER CLIENT")
        print("="*50)
        
        if not self.connect():
            return
        
        while True:  # Outer loop to handle session expiration
            # Try to restore existing session first
            if self.session_id and self.restore_session():
                pass  # Session restored, go to main menu
            else:
                # Login or create account
                while True:
                    print("\n1. Login")
                    print("2. Create Account")
                    print("0. Exit")
                    choice = input("\nChoice: ").strip()
                    
                    if choice == '1':
                        if self.login():
                            break
                    elif choice == '2':
                        self.create_account()
                    elif choice == '0':
                        self.disconnect()
                        print("\nGoodbye!")
                        return
            
            # Main menu
            session_active = True
            while session_active:
                self.show_menu()
                choice = input("\nChoice: ").strip()
                
                response = None
                
                if choice == '1':
                    response = self.get_rating()
                elif choice == '2':
                    response = self.register_item()
                elif choice == '3':
                    response = self.change_price()
                elif choice == '4':
                    response = self.update_units()
                elif choice == '5':
                    response = self.display_items()
                elif choice == '6':
                    self.logout()
                    session_active = False
                elif choice == '0':
                    if self.session_id:
                        self.logout()
                    self.disconnect()
                    print("\nGoodbye!")
                    return
                else:
                    print("\nInvalid choice")
                
                # Check if session expired - return to outer loop to try restore
                if response is not None and self.is_session_expired(response):
                    print("\nSession expired. Attempting to restore...")
                    session_active = False
        
        self.disconnect()
        print("\nGoodbye!")


def main():
    """Main entry point"""
    client = SellerClient(
        host=config.SELLER_FRONTEND_HOST,
        port=config.SELLER_FRONTEND_PORT
    )
    client.run()


if __name__ == '__main__':
    main()