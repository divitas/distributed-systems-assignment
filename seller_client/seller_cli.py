"""
seller_cli.py - Command Line Interface for Sellers

This module provides the user-facing interface for sellers:
- Parses user commands from stdin
- Displays formatted output
- Handles user interaction flow
- Provides help and error messages

This layer uses SellerAPI for operations but handles all user interaction.
"""

import sys
import argparse
import getpass
from typing import Optional, List

import sys
import os

# Add project root (parent folder) to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from seller_client.seller_client import SellerClient, ConnectionError
from seller_client.seller_api import SellerAPI, APIError, Item


class SellerCLI:
    """
    Interactive command-line interface for sellers.
    
    Provides a REPL (Read-Eval-Print Loop) for seller operations.
    """
    
    COMMANDS = {
        "help": "Show available commands",
        "register": "Create a new seller account",
        "login": "Log in to your account",
        "logout": "Log out of current session",
        "rating": "View your seller rating",
        "sell": "Register a new item for sale",
        "price": "Change item price (usage: price <category> <id> <new_price>)",
        "remove": "Remove units from sale (usage: remove <category> <id> <quantity>)",
        "items": "Display all your items for sale",
        "status": "Show connection and session status",
        "quit": "Exit the application",
    }
    
    # Predefined categories for user convenience
    CATEGORIES = {
        1: "Electronics",
        2: "Clothing",
        3: "Home & Garden",
        4: "Sports",
        5: "Books",
        6: "Toys",
        7: "Automotive",
        8: "Other"
    }
    
    def __init__(self, host: str, port: int):
        """
        Initialize CLI with server connection info.
        
        Args:
            host: Server hostname
            port: Server port
        """
        self.host = host
        self.port = port
        self._client: Optional[SellerClient] = None
        self._api: Optional[SellerAPI] = None
        self._running = False
    
    def start(self) -> None:
        """Start the interactive CLI session."""
        print("=" * 60)
        print("  Online Marketplace - Seller Interface")
        print("=" * 60)
        print(f"Connecting to server at {self.host}:{self.port}...")
        
        try:
            self._client = SellerClient(self.host, self.port)
            self._client.connect()
            self._api = SellerAPI(self._client)
            print("Connected successfully!")
            print("Type 'help' for available commands.\n")
        except ConnectionError as e:
            print(f"Failed to connect: {e}")
            return
        
        self._running = True
        self._run_loop()
    
    def _run_loop(self) -> None:
        """Main command loop."""
        while self._running:
            try:
                # Show prompt with login status
                prompt = self._get_prompt()
                user_input = input(prompt).strip()
                
                if not user_input:
                    continue
                
                self._process_command(user_input)
                
            except KeyboardInterrupt:
                print("\nUse 'quit' to exit.")
            except EOFError:
                self._running = False
            except ConnectionError as e:
                print(f"\nConnection error: {e}")
                print("Attempting to reconnect...")
                self._reconnect()
    
    def _get_prompt(self) -> str:
        """Generate command prompt showing current status."""
        if self._api and self._api.is_logged_in:
            return f"seller [{self._api.seller_id}] > "
        return "seller > "
    
    def _process_command(self, user_input: str) -> None:
        """Parse and execute a user command."""
        parts = user_input.split()
        command = parts[0].lower()
        args = parts[1:]
        
        # Map commands to handler methods
        handlers = {
            "help": self._cmd_help,
            "register": self._cmd_register,
            "login": self._cmd_login,
            "logout": self._cmd_logout,
            "rating": self._cmd_rating,
            "sell": self._cmd_sell,
            "price": self._cmd_price,
            "remove": self._cmd_remove,
            "items": self._cmd_items,
            "status": self._cmd_status,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }
        
        handler = handlers.get(command)
        if handler:
            try:
                handler(args)
            except APIError as e:
                print(f"Error: {e}")
        else:
            print(f"Unknown command: {command}")
            print("Type 'help' for available commands.")
    
    # =========================================================================
    # Command Handlers
    # =========================================================================
    
    def _cmd_help(self, args: List[str]) -> None:
        """Display help information."""
        print("\nAvailable Commands:")
        print("-" * 50)
        for cmd, description in self.COMMANDS.items():
            print(f"  {cmd:12} - {description}")
        print()
    
    def _cmd_register(self, args: List[str]) -> None:
        """Handle account registration."""
        print("\n--- Create New Seller Account ---")
        username = input("Shop/Seller Name: ").strip()
        if not username:
            print("Username cannot be empty.")
            return
        
        if len(username) > 32:
            print("Username must be 32 characters or less.")
            return
        
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("Passwords do not match.")
            return
        
        seller_id = self._api.create_account(username, password)
        print(f"\nAccount created successfully!")
        print(f"Your Seller ID: {seller_id}")
        print("You can now log in with your credentials.\n")
    
    def _cmd_login(self, args: List[str]) -> None:
        """Handle user login."""
        if self._api.is_logged_in:
            print("Already logged in. Use 'logout' first.")
            return
        
        print("\n--- Seller Login ---")
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        
        session_id = self._api.login(username, password)
        print(f"Login successful!")
        print(f"Session ID: {session_id[:8]}...")
        print(f"Seller ID: {self._api.seller_id}\n")
    
    def _cmd_logout(self, args: List[str]) -> None:
        """Handle user logout."""
        if not self._api.is_logged_in:
            print("Not logged in.")
            return
        
        self._api.logout()
        print("Logged out successfully.\n")
    
    def _cmd_rating(self, args: List[str]) -> None:
        """Display seller's rating."""
        thumbs_up, thumbs_down = self._api.get_seller_rating()
        
        print(f"\n--- Your Seller Rating ---")
        print(f"  👍 Thumbs Up:   {thumbs_up}")
        print(f"  👎 Thumbs Down: {thumbs_down}")
        
        total = thumbs_up + thumbs_down
        if total > 0:
            ratio = thumbs_up / total * 100
            print(f"  📊 Positive:    {ratio:.1f}%")
        else:
            print("  📊 No ratings yet")
        print()
    
    def _cmd_sell(self, args: List[str]) -> None:
        """Register a new item for sale - interactive wizard."""
        print("\n--- Register New Item for Sale ---")
        
        # Item name
        name = input("Item name (max 32 chars): ").strip()
        if not name:
            print("Item name cannot be empty.")
            return
        if len(name) > 32:
            print("Item name too long.")
            return
        
        # Category selection
        print("\nCategories:")
        for cat_id, cat_name in self.CATEGORIES.items():
            print(f"  {cat_id}. {cat_name}")
        
        try:
            category = int(input("Select category number: ").strip())
        except ValueError:
            print("Invalid category.")
            return
        
        # Keywords
        print("\nEnter keywords (up to 5, max 8 chars each)")
        print("Enter each keyword on a new line, empty line to finish:")
        keywords = []
        for i in range(5):
            kw = input(f"  Keyword {i+1}: ").strip()
            if not kw:
                break
            if len(kw) > 8:
                print(f"  Keyword too long, truncating to: {kw[:8]}")
                kw = kw[:8]
            keywords.append(kw)
        
        # Condition
        print("\nCondition:")
        print("  1. New")
        print("  2. Used")
        cond_input = input("Select (1/2): ").strip()
        if cond_input == "1":
            condition = "New"
        elif cond_input == "2":
            condition = "Used"
        else:
            print("Invalid condition.")
            return
        
        # Price
        try:
            price = float(input("\nSale price: $").strip())
            if price < 0:
                print("Price cannot be negative.")
                return
        except ValueError:
            print("Invalid price.")
            return
        
        # Quantity
        try:
            quantity = int(input("Quantity available: ").strip())
            if quantity < 1:
                print("Quantity must be at least 1.")
                return
        except ValueError:
            print("Invalid quantity.")
            return
        
        # Confirm
        print("\n--- Confirm Item Details ---")
        print(f"  Name:      {name}")
        print(f"  Category:  {self.CATEGORIES.get(category, category)}")
        print(f"  Keywords:  {', '.join(keywords) or 'None'}")
        print(f"  Condition: {condition}")
        print(f"  Price:     ${price:.2f}")
        print(f"  Quantity:  {quantity}")
        
        confirm = input("\nRegister this item? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            return
        
        # Register the item
        item_id = self._api.register_item(
            name=name,
            category=category,
            keywords=keywords,
            condition=condition,
            sale_price=price,
            quantity=quantity
        )
        
        print(f"\n✓ Item registered successfully!")
        print(f"  Item ID: ({item_id[0]}, {item_id[1]})\n")
    
    def _cmd_price(self, args: List[str]) -> None:
        """Change item price."""
        if len(args) < 3:
            print("Usage: price <category> <id> <new_price>")
            print("Example: price 1 5 999.99")
            return
        
        try:
            item_id = (int(args[0]), int(args[1]))
            new_price = float(args[2])
        except ValueError:
            print("Invalid arguments. Category and ID must be integers, price must be a number.")
            return
        
        if new_price < 0:
            print("Price cannot be negative.")
            return
        
        self._api.change_item_price(item_id, new_price)
        print(f"✓ Price updated for item {item_id} to ${new_price:.2f}\n")
    
    def _cmd_remove(self, args: List[str]) -> None:
        """Remove units from sale."""
        if len(args) < 3:
            print("Usage: remove <category> <id> <quantity>")
            print("Example: remove 1 5 2")
            return
        
        try:
            item_id = (int(args[0]), int(args[1]))
            quantity = int(args[2])
        except ValueError:
            print("Invalid arguments. All values must be integers.")
            return
        
        if quantity < 1:
            print("Quantity must be at least 1.")
            return
        
        self._api.update_units_for_sale(item_id, quantity)
        print(f"✓ Removed {quantity} units of item {item_id} from sale\n")
    
    def _cmd_items(self, args: List[str]) -> None:
        """Display all items for sale."""
        items = self._api.display_items_for_sale()
        
        print("\n--- Your Items for Sale ---")
        
        if not items:
            print("You have no items listed for sale.")
        else:
            print(f"{'ID':<12} {'Name':<25} {'Price':>10} {'Qty':>6} {'Cond':<6} {'Rating':<12}")
            print("-" * 75)
            for item in items:
                item_id_str = f"({item.item_id[0]},{item.item_id[1]})"
                name = item.name[:23] + ".." if len(item.name) > 25 else item.name
                rating = f"👍{item.feedback[0]} 👎{item.feedback[1]}"
                print(f"{item_id_str:<12} {name:<25} ${item.sale_price:>8.2f} {item.quantity:>6} {item.condition:<6} {rating}")
        print()
    
    def _cmd_status(self, args: List[str]) -> None:
        """Show current status."""
        print("\n--- Status ---")
        print(f"Server: {self.host}:{self.port}")
        print(f"Connected: {self._client.is_connected()}")
        print(f"Logged in: {self._api.is_logged_in}")
        if self._api.is_logged_in:
            print(f"Seller ID: {self._api.seller_id}")
            print(f"Session ID: {self._api.session_id[:8]}...")
        print()
    
    def _cmd_quit(self, args: List[str]) -> None:
        """Exit the application."""
        if self._api and self._api.is_logged_in:
            print("Logging out...")
            self._api.logout()
        
        print("Goodbye!")
        self._running = False
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _reconnect(self) -> None:
        """Attempt to reconnect to the server."""
        try:
            if self._client:
                self._client.disconnect()
            self._client = SellerClient(self.host, self.port)
            self._client.connect()
            self._api = SellerAPI(self._client)
            print("Reconnected successfully.")
            print("Note: You will need to log in again.\n")
        except ConnectionError as e:
            print(f"Reconnection failed: {e}")
            self._running = False


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Online Marketplace Seller CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Connect to localhost:5002
  %(prog)s --host 192.168.1.10      # Connect to specific host
  %(prog)s --port 8080              # Connect to specific port

Typical workflow:
  1. register  - Create a new seller account
  2. login     - Log in to your account
  3. sell      - Register items for sale
  4. items     - View your listed items
  5. price     - Update item prices
  6. rating    - Check your seller rating
  7. logout    - End your session
        """
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server hostname (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5002,
        help="Server port (default: 5002)"
    )
    
    args = parser.parse_args()
    
    cli = SellerCLI(args.host, args.port)
    cli.start()


if __name__ == "__main__":
    main()