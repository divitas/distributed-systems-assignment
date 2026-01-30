"""
Buyer CLI Client
Interactive command-line interface for buyers
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


class BuyerClient:
    """Buyer CLI Client"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.session_id = None
        self.buyer_id = None
        self.buyer_name = None
    
    def connect(self):
        """Connect to buyer frontend server"""
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
    
    # ========== API Methods ==========
    
    def create_account(self):
        """Create a new buyer account"""
        print("\n=== Create Buyer Account ===")
        username = input("Enter username: ").strip()
        password = input("Enter password: ").strip()
        buyer_name = input("Enter your name (display name): ").strip()
        
        response = self.send_request(
            API_BUYER_CREATE_ACCOUNT,
            {
                'username': username,
                'password': password,
                'buyer_name': buyer_name
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            buyer_id = response['data']['buyer_id']
            print(f"\n✓ Account created successfully!")
            print(f"Your Buyer ID: {buyer_id}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def login(self):
        """Login to buyer account"""
        print("\n=== Buyer Login ===")
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        
        response = self.send_request(
            API_BUYER_LOGIN,
            {
                'username': username,
                'password': password
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            self.session_id = response['data']['session_id']
            self.buyer_id = response['data']['buyer_id']
            self.buyer_name = response['data']['buyer_name']
            print(f"\n✓ Welcome, {self.buyer_name}!")
            print(f"Buyer ID: {self.buyer_id}")
            return True
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Login failed: {message}")
            return False
    
    def logout(self):
        """Logout from buyer account"""
        if not self.session_id:
            print("Not logged in.")
            return
        
        response = self.send_request(API_BUYER_LOGOUT)
        
        if response and response['status'] == STATUS_SUCCESS:
            print("\n✓ Logged out successfully")
            print("Note: Your cart has been cleared. Use 'Save Cart' before logging out to persist your cart.")
            self.session_id = None
            self.buyer_id = None
            self.buyer_name = None
        else:
            print("\n✗ Logout failed")
    
    def search_items(self):
        """Search for items"""
        print("\n=== Search Items ===")
        
        print("\nCategories:")
        for cat_id, cat_name in config.ITEM_CATEGORIES.items():
            print(f"  {cat_id}. {cat_name}")
        category = input("Select category (1-8): ").strip()
        
        print("Enter keywords to search (comma-separated, optional):")
        keywords_input = input("Keywords: ").strip()
        keywords = [k.strip() for k in keywords_input.split(',') if k.strip()][:5]
        
        try:
            category = int(category)
        except ValueError:
            print("\n✗ Invalid category")
            return
        
        response = self.send_request(
            API_BUYER_SEARCH_ITEMS,
            {
                'category': category,
                'keywords': keywords
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            items = response['data']['items']
            
            if not items:
                print("\nNo items found matching your search.")
            else:
                print(f"\n=== Search Results ({len(items)} items found) ===")
                for i, item in enumerate(items, 1):
                    print(f"\n--- Item {i} ---")
                    print(format_item_display(item))
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def get_item(self):
        """Get details of a specific item"""
        print("\n=== Get Item Details ===")
        item_id = input("Item ID: ").strip()
        
        response = self.send_request(
            API_BUYER_GET_ITEM,
            {'item_id': item_id}
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            item = response['data']['item']
            print("\n" + format_item_display(item))
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def add_to_cart(self):
        """Add item to shopping cart"""
        print("\n=== Add Item to Cart ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity: ").strip()
        
        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return
        
        response = self.send_request(
            API_BUYER_ADD_TO_CART,
            {
                'item_id': item_id,
                'quantity': quantity
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            print(f"\n✓ Added {quantity} unit(s) to cart")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def remove_from_cart(self):
        """Remove item from shopping cart"""
        print("\n=== Remove Item from Cart ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity to remove: ").strip()
        
        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return
        
        response = self.send_request(
            API_BUYER_REMOVE_FROM_CART,
            {
                'item_id': item_id,
                'quantity': quantity
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            print(f"\n✓ Removed {quantity} unit(s) from cart")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def save_cart(self):
        """Save cart to persist across sessions"""
        response = self.send_request(API_BUYER_SAVE_CART)
        
        if response and response['status'] == STATUS_SUCCESS:
            print("\n✓ Cart saved successfully")
            print("Your cart will be available in all your sessions.")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def clear_cart(self):
        """Clear shopping cart"""
        confirm = input("\nAre you sure you want to clear your cart? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Cancelled.")
            return
        
        response = self.send_request(API_BUYER_CLEAR_CART)
        
        if response and response['status'] == STATUS_SUCCESS:
            print("\n✓ Cart cleared")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def display_cart(self):
        """Display shopping cart"""
        response = self.send_request(API_BUYER_DISPLAY_CART)
        
        if response and response['status'] == STATUS_SUCCESS:
            cart = response['data']['cart']
            
            if not cart:
                print("\nYour shopping cart is empty.")
            else:
                print(f"\n=== Shopping Cart ({len(cart)} items) ===")
                for i, item in enumerate(cart, 1):
                    print(f"{i}. Item ID: {item['item_id']}, Quantity: {item['quantity']}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def provide_feedback(self):
        """Provide feedback for an item"""
        print("\n=== Provide Feedback ===")
        item_id = input("Item ID: ").strip()
        
        print("\nFeedback:")
        print("  1. Thumbs Up 👍")
        print("  2. Thumbs Down 👎")
        feedback_choice = input("Select (1 or 2): ").strip()
        
        if feedback_choice == '1':
            feedback = FEEDBACK_THUMBS_UP
        elif feedback_choice == '2':
            feedback = FEEDBACK_THUMBS_DOWN
        else:
            print("\n✗ Invalid choice")
            return
        
        response = self.send_request(
            API_BUYER_PROVIDE_FEEDBACK,
            {
                'item_id': item_id,
                'feedback': feedback
            }
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            print(f"\n✓ Feedback recorded")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def get_seller_rating(self):
        """Get seller rating"""
        print("\n=== Get Seller Rating ===")
        seller_id = input("Seller ID: ").strip()
        
        try:
            seller_id = int(seller_id)
        except ValueError:
            print("\n✗ Invalid seller ID")
            return
        
        response = self.send_request(
            API_BUYER_GET_SELLER_RATING,
            {'seller_id': seller_id}
        )
        
        if response and response['status'] == STATUS_SUCCESS:
            thumbs_up = response['data']['thumbs_up']
            thumbs_down = response['data']['thumbs_down']
            print(f"\nSeller {seller_id} Rating: {format_feedback(thumbs_up, thumbs_down)}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    def get_purchases(self):
        """Get purchase history"""
        response = self.send_request(API_BUYER_GET_PURCHASES)
        
        if response and response['status'] == STATUS_SUCCESS:
            purchases = response['data']['purchases']
            
            if not purchases:
                print("\nNo purchase history.")
            else:
                print(f"\n=== Purchase History ({len(purchases)} items) ===")
                for i, purchase in enumerate(purchases, 1):
                    print(f"{i}. Item ID: {purchase['item_id']}, "
                          f"Quantity: {purchase['quantity']}, "
                          f"Date: {purchase.get('purchase_date', 'N/A')}")
        else:
            message = response.get('message', 'Unknown error') if response else 'Connection error'
            print(f"\n✗ Error: {message}")
    
    # ========== Main Menu ==========
    
    def show_menu(self):
        """Show main menu"""
        print("\n" + "="*50)
        print("BUYER MENU")
        print("="*50)
        print("1.  Search Items")
        print("2.  Get Item Details")
        print("3.  Add Item to Cart")
        print("4.  Remove Item from Cart")
        print("5.  Display Cart")
        print("6.  Save Cart")
        print("7.  Clear Cart")
        print("8.  Provide Feedback")
        print("9.  Get Seller Rating")
        print("10. View Purchase History")
        print("11. Logout")
        print("0.  Exit")
        print("="*50)
    
    def run(self):
        """Run the buyer client"""
        print("\n" + "="*50)
        print("ONLINE MARKETPLACE - BUYER CLIENT")
        print("="*50)
        
        if not self.connect():
            return
        
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
                return
        
        # Main menu
        while self.session_id:
            self.show_menu()
            choice = input("\nChoice: ").strip()
            
            if choice == '1':
                self.search_items()
            elif choice == '2':
                self.get_item()
            elif choice == '3':
                self.add_to_cart()
            elif choice == '4':
                self.remove_from_cart()
            elif choice == '5':
                self.display_cart()
            elif choice == '6':
                self.save_cart()
            elif choice == '7':
                self.clear_cart()
            elif choice == '8':
                self.provide_feedback()
            elif choice == '9':
                self.get_seller_rating()
            elif choice == '10':
                self.get_purchases()
            elif choice == '11':
                self.logout()
            elif choice == '0':
                if self.session_id:
                    self.logout()
                break
            else:
                print("\nInvalid choice")
        
        self.disconnect()
        print("\nGoodbye!")


def main():
    """Main entry point"""
    client = BuyerClient(
        host=config.BUYER_FRONTEND_HOST,
        port=config.BUYER_FRONTEND_PORT
    )
    client.run()


if __name__ == '__main__':
    main()
