"""
Seller CLI Client - PA3 version with frontend replica failover
"""

import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.constants import *
from shared.utils import format_feedback, format_item_display


class SellerClient:

    def __init__(self):
        self.session_id = None
        self.seller_id = None
        self.seller_name = None
        self.replicas = [
            f"http://{r['host']}:{r['port']}" for r in config.SELLER_FRONTEND_REPLICAS
        ]
        self.current_replica_idx = 0

    def _get_base_url(self):
        return self.replicas[self.current_replica_idx]

    def _failover(self):
        old = self.current_replica_idx
        self.current_replica_idx = (self.current_replica_idx + 1) % len(self.replicas)
        print(f"  (Switching from replica {old} to replica {self.current_replica_idx})")

    def _post(self, endpoint, data):
        for attempt in range(len(self.replicas)):
            try:
                url = f"{self._get_base_url()}{endpoint}"
                r = requests.post(url, json=data, timeout=30)
                return r.json()
            except Exception as e:
                print(f"  Connection error to replica {self.current_replica_idx}: {e}")
                self._failover()
        print("All replicas unavailable.")
        return None

    def _get(self, endpoint, params=None):
        for attempt in range(len(self.replicas)):
            try:
                url = f"{self._get_base_url()}{endpoint}"
                r = requests.get(url, params=params, timeout=30)
                return r.json()
            except Exception as e:
                print(f"  Connection error to replica {self.current_replica_idx}: {e}")
                self._failover()
        print("All replicas unavailable.")
        return None

    def restore_session(self):
        if not self.session_id:
            return False
        response = self._post("/seller/restore_session", {"session_id": self.session_id})
        if response and response.get('status') == 'success':
            self.seller_id = response['data']['seller_id']
            self.seller_name = response['data']['seller_name']
            print(f"\n✓ Session restored. Welcome back, {self.seller_name}!")
            return True
        self.session_id = None
        return False

    def create_account(self):
        print("\n=== Create Seller Account ===")
        username = input("Enter username: ").strip()
        password = input("Enter password: ").strip()
        seller_name = input("Enter your name (display name): ").strip()

        response = self._post("/seller/create_account", {
            'username': username, 'password': password, 'seller_name': seller_name
        })
        if response and response.get('status') == 'success':
            print(f"\n✓ Account created! Seller ID: {response['data']['seller_id']}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def login(self):
        print("\n=== Seller Login ===")
        username = input("Username: ").strip()
        password = input("Password: ").strip()

        response = self._post("/seller/login", {'username': username, 'password': password})
        if response and response.get('status') == 'success':
            self.session_id = response['data']['session_id']
            self.seller_id = response['data']['seller_id']
            self.seller_name = response['data']['seller_name']
            print(f"\n✓ Welcome, {self.seller_name}! Seller ID: {self.seller_id}")
            return True
        else:
            print(f"\n✗ Login failed: {response.get('message', 'Unknown error') if response else 'Connection error'}")
            return False

    def logout(self):
        if not self.session_id:
            print("Not logged in.")
            return
        self._post("/seller/logout", {"session_id": self.session_id})
        print("\n✓ Logged out successfully")
        self.session_id = None
        self.seller_id = None
        self.seller_name = None

    def get_rating(self):
        response = self._get("/seller/get_rating", {"session_id": self.session_id})
        if response and response.get('status') == 'success':
            d = response['data']
            print(f"\nYour Rating: {format_feedback(d['thumbs_up'], d['thumbs_down'])}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def register_item(self):
        print("\n=== Register New Item ===")
        name = input("Item name: ").strip()
        print("\nCategories:")
        for cat_id, cat_name in config.ITEM_CATEGORIES.items():
            print(f"  {cat_id}. {cat_name}")
        category = input("Select category (1-8): ").strip()
        keywords_input = input("Enter up to 5 keywords (comma-separated): ").strip()
        keywords = [k.strip() for k in keywords_input.split(',') if k.strip()][:5]
        print("\nCondition: 1. New  2. Used")
        condition_choice = input("Select (1 or 2): ").strip()
        condition = CONDITION_NEW if condition_choice == '1' else CONDITION_USED
        price = input("Price ($): ").strip()
        quantity = input("Quantity: ").strip()
        try:
            category = int(category)
            price = float(price)
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid input")
            return

        response = self._post("/seller/register_item", {
            'session_id': self.session_id, 'name': name, 'category': category,
            'keywords': keywords, 'condition': condition, 'price': price, 'quantity': quantity
        })
        if response and response.get('status') == 'success':
            print(f"\n✓ Item registered! Item ID: {response['data']['item_id']}")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def change_price(self):
        print("\n=== Change Item Price ===")
        item_id = input("Item ID: ").strip()
        new_price = input("New price ($): ").strip()
        try:
            new_price = float(new_price)
        except ValueError:
            print("\n✗ Invalid price")
            return
        response = self._post("/seller/change_price", {
            'session_id': self.session_id, 'item_id': item_id, 'new_price': new_price
        })
        if response and response.get('status') == 'success':
            print("\n✓ Price updated")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def update_units(self):
        print("\n=== Remove Units from Sale ===")
        item_id = input("Item ID: ").strip()
        quantity = input("Quantity to remove: ").strip()
        try:
            quantity = int(quantity)
        except ValueError:
            print("\n✗ Invalid quantity")
            return
        response = self._post("/seller/update_units", {
            'session_id': self.session_id, 'item_id': item_id, 'quantity': quantity
        })
        if response and response.get('status') == 'success':
            print("\n✓ Units updated")
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def display_items(self):
        response = self._get("/seller/display_items", {"session_id": self.session_id})
        if response and response.get('status') == 'success':
            items = response['data']['items']
            if not items:
                print("\nYou have no items for sale.")
            else:
                print(f"\n=== Your Items ({len(items)} total) ===")
                for i, item in enumerate(items, 1):
                    print(f"\n--- Item {i} ---")
                    print(format_item_display(item))
        else:
            print(f"\n✗ Error: {response.get('message', 'Unknown error') if response else 'Connection error'}")

    def show_menu(self):
        print(f"\n{'='*50}")
        print(f"SELLER MENU (connected to replica {self.current_replica_idx})")
        print("="*50)
        print("1. Get My Rating")
        print("2. Register Item for Sale")
        print("3. Change Item Price")
        print("4. Remove Units from Sale")
        print("5. Display My Items")
        print("6. Logout")
        print("0. Exit")
        print("="*50)

    def run(self):
        print("\n" + "="*50)
        print("ONLINE MARKETPLACE - SELLER CLIENT (PA3)")
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

                if choice == '1':    self.get_rating()
                elif choice == '2':  self.register_item()
                elif choice == '3':  self.change_price()
                elif choice == '4':  self.update_units()
                elif choice == '5':  self.display_items()
                elif choice == '6':
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
    client = SellerClient()
    client.run()


if __name__ == '__main__':
    main()
