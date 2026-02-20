"""
Buyer CLI Client - REST version
"""

import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.constants import *
from shared.utils import format_feedback, format_item_display

BASE_URL = f"http://{config.BUYER_FRONTEND_HOST}:{config.BUYER_FRONTEND_PORT}"


class BuyerClient:

    def __init__(self):
        self.session_id = None
        self.buyer_id = None
        self.buyer_name = None

    def _post(self, endpoint, data):
        try:
            r = requests.post(f"{BASE_URL}{endpoint}", json=data, timeout=30)
            return r.json()
        except Exception as e:
            print(f"Connection error: {e}")
            return None

    def _get(self, endpoint, params=None):
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=30)
            return r.json()
        except Exception as e:
            print(f"Connection error: {e}")
            return None

    def restore_session(self):
        if not self.session_id:
            return False
        response = self._post("/buyer/restore_session", {"session_id": self.session_id})
        if response and response.get('status') == 'success':
            self.buyer_id = response['data']['buyer_id']
            self.buyer_name = response['data']['buyer_name']
            print(f"\n✓ Session restored. Welcome back, {self.buyer_name}!")
            return True
        self.session_id = None
        return False

    def create_account(self):
        print("\n=== Create Buyer Account ===")
        username = input("Enter username: ").strip()
        password = input("Enter password: ").strip()
        buyer_name = input("Enter your name (display name): ").strip()

        response = self._post("/buyer/create_account", {
            'username': username, 'password': password, 'buyer_name': buyer_name
        })

        if response and response.get('status') == 'success':
            print(f"\n✓ Account created! Buyer ID: {response['data']['buyer_id']}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def login(self):
        print("\n=== Buyer Login ===")
        username = input("Username: ").strip()
        password = input("Password: ").strip()

        response = self._post("/buyer/login", {'username': username, 'password': password})

        if response and response.get('status') == 'success':
            self.session_id = response['data']['session_id']
            self.buyer_id = response['data']['buyer_id']
            self.buyer_name = response['data']['buyer_name']
            print(f"\n✓ Welcome, {self.buyer_name}! Buyer ID: {self.buyer_id}")
            return True
        else:
            print(f"\n✗ Login failed: {response.get('message', 'Unknown error') if response else 'Connection error'}")
            return False

    def logout(self):
        if not self.session_id:
            print("Not logged in.")
            return
        self._post("/buyer/logout", {"session_id": self.session_id})
        print("\n✓ Logged out successfully")
        print("Note: Your cart has been cleared. Use 'Save Cart' before logging out to persist your cart.")
        self.session_id = None
        self.buyer_id = None
        self.buyer_name = None

    def search_items(self):
        print("\n=== Search Items ===")
        print("\nCategories:")
        for cat_id, cat_name in config.ITEM_CATEGORIES.items():
            print(f"  {cat_id}. {cat_name}")
        category = input("Select category (1-8): ").strip()

        keywords_input = input("Enter keywords (comma-separated, optional): ").strip()
        keywords = [k.strip() for k in keywords_input.split(',') if k.strip()][:5]

        try:
            category = int(category)
        except ValueError:
            print("\n✗ Invalid category")
            return None

        response = self._post("/buyer/search_items", {
            'session_id': self.session_id, 'category': category, 'keywords': keywords
        })

        if response and response.get('status') == 'success':
            items = response['data']['items']
            if not items:
                print("\nNo items found.")
            else:
                print(f"\n=== Search Results ({len(items)} items found) ===")
                for i, item in enumerate(items, 1):
                    print(f"\n--- Item {i} ---")
                    print(format_item_display(item))
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def get_item(self):
        print("\n=== Get Item Details ===")
        item_id = input("Item ID: ").strip()

        response = self._get("/buyer/get_item", {"session_id": self.session_id, "item_id": item_id})

        if response and response.get('status') == 'success':
            print("\n" + format_item_display(response['data']['item']))
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def add_to_cart(self):
        print("\n=== Add Item to Cart ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity: ").strip()

        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return None

        response = self._post("/buyer/add_to_cart", {
            'session_id': self.session_id, 'item_id': item_id, 'quantity': quantity
        })

        if response and response.get('status') == 'success':
            print(f"\n✓ Added {quantity} unit(s) to cart")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def remove_from_cart(self):
        print("\n=== Remove Item from Cart ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity to remove: ").strip()

        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return None

        response = self._post("/buyer/remove_from_cart", {
            'session_id': self.session_id, 'item_id': item_id, 'quantity': quantity
        })

        if response and response.get('status') == 'success':
            print(f"\n✓ Removed {quantity} unit(s) from cart")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def save_cart(self):
        response = self._post("/buyer/save_cart", {"session_id": self.session_id})

        if response and response.get('status') == 'success':
            print("\n✓ Cart saved successfully")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def clear_cart(self):
        confirm = input("\nAre you sure you want to clear your cart? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Cancelled.")
            return None

        response = self._post("/buyer/clear_cart", {"session_id": self.session_id})

        if response and response.get('status') == 'success':
            print("\n✓ Cart cleared")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def display_cart(self):
        response = self._get("/buyer/display_cart", {"session_id": self.session_id})

        if response and response.get('status') == 'success':
            cart = response['data']['cart']
            if not cart:
                print("\nYour shopping cart is empty.")
            else:
                print(f"\n=== Shopping Cart ({len(cart)} items) ===")
                for i, item in enumerate(cart, 1):
                    print(f"{i}. Item ID: {item['item_id']}, Quantity: {item['quantity']}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def provide_feedback(self):
        print("\n=== Provide Feedback ===")
        item_id = input("Item ID: ").strip()
        seller_id = input("Seller ID: ").strip()

        print("\n1. Thumbs Up 👍\n2. Thumbs Down 👎")
        feedback_choice = input("Select (1 or 2): ").strip()

        if feedback_choice == '1':
            thumbs = 1
        elif feedback_choice == '2':
            thumbs = 0
        else:
            print("\n✗ Invalid choice")
            return None

        response = self._post("/buyer/provide_feedback", {
            'session_id': self.session_id,
            'item_id': item_id,
            'seller_id': seller_id,
            'thumbs': thumbs
        })

        if response and response.get('status') == 'success':
            print("\n✓ Feedback recorded")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def get_seller_rating(self):
        print("\n=== Get Seller Rating ===")
        seller_id = input("Seller ID: ").strip()

        response = self._get("/buyer/get_seller_rating", {
            "session_id": self.session_id, "seller_id": seller_id
        })

        if response and response.get('status') == 'success':
            d = response['data']
            print(f"\nSeller {seller_id} Rating: {format_feedback(d['thumbs_up'], d['thumbs_down'])}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def get_purchases(self):
        response = self._get("/buyer/get_purchases", {"session_id": self.session_id})

        if response and response.get('status') == 'success':
            purchases = response['data']['purchases']
            if not purchases:
                print("\nNo purchase history.")
            else:
                print(f"\n=== Purchase History ({len(purchases)} items) ===")
                for i, p in enumerate(purchases, 1):
                    print(f"{i}. Item ID: {p['item_id']}, Quantity: {p['quantity']}, Date: {p.get('purchase_date', 'N/A')}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def make_purchase(self):
        print("\n=== Make Purchase ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity: ").strip()

        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return None

        print("\n--- Payment Information ---")
        card_name = input("Name on card: ").strip()
        card_number = input("Card number: ").strip()
        expiration_date = input("Expiration date (MM/YY): ").strip()
        security_code = input("Security code: ").strip()

        response = self._post("/buyer/make_purchase", {
            'session_id': self.session_id,
            'item_id': item_id,
            'quantity': quantity,
            'card_name': card_name,
            'card_number': card_number,
            'expiration_date': expiration_date,
            'security_code': security_code
        })

        if response and response.get('status') == 'success':
            print("\n✓ Purchase completed successfully!")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

        return response

    def show_menu(self):
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
        print("8.  Make Purchase")
        print("9.  Provide Feedback")
        print("10. Get Seller Rating")
        print("11. View Purchase History")
        print("12. Logout")
        print("0.  Exit")
        print("="*50)

    def run(self):
        print("\n" + "="*50)
        print("ONLINE MARKETPLACE - BUYER CLIENT")
        print("="*50)

        while True:
            if self.session_id and self.restore_session():
                pass
            else:
                while True:
                    print("\n1. Login\n2. Create Account\n0. Exit")
                    choice = input("\nChoice: ").strip()
                    if choice == '1':
                        if self.login():
                            break
                    elif choice == '2':
                        self.create_account()
                    elif choice == '0':
                        print("\nGoodbye!")
                        return

            while True:
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
                    self.make_purchase()
                elif choice == '9':
                    self.provide_feedback()
                elif choice == '10':
                    self.get_seller_rating()
                elif choice == '11':
                    self.get_purchases()
                elif choice == '12':
                    self.logout()
                    break
                elif choice == '0':
                    if self.session_id:
                        self.logout()
                    print("\nGoodbye!")
                    return
                else:
                    print("\nInvalid choice")


def main():
    client = BuyerClient()
    client.run()


if __name__ == '__main__':
    main()