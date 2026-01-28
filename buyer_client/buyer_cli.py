"""
buyer_cli.py - Command Line Interface for Buyers

This module provides the user-facing interface:
- Parses user commands from stdin
- Displays formatted output
- Handles user interaction flow
- Provides help and error messages

This layer uses BuyerAPI for operations but handles all user interaction.
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

from buyer_client.buyer_client import BuyerClient, ConnectionError
from buyer_client.buyer_api import BuyerAPI, APIError, Item, CartItem


class BuyerCLI:
    """
    Interactive command-line interface for buyers.
    
    Provides a REPL (Read-Eval-Print Loop) for buyer operations.
    """
    
    COMMANDS = {
        "help": "Show available commands",
        "register": "Create a new buyer account",
        "login": "Log in to your account",
        "logout": "Log out of current session",
        "search": "Search for items (usage: search <category> [keyword1] [keyword2] ...)",
        "item": "Get item details (usage: item <category> <id>)",
        "cart": "Display shopping cart",
        "add": "Add item to cart (usage: add <category> <id> <quantity>)",
        "remove": "Remove item from cart (usage: remove <category> <id> <quantity>)",
        "save": "Save cart for next session",
        "clear": "Clear shopping cart",
        "feedback": "Rate an item (usage: feedback <category> <id> <up/down>)",
        "seller": "Get seller rating (usage: seller <seller_id>)",
        "history": "View purchase history",
        "status": "Show connection and session status",
        "quit": "Exit the application",
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
        self._client: Optional[BuyerClient] = None
        self._api: Optional[BuyerAPI] = None
        self._running = False
    
    def start(self) -> None:
        """Start the interactive CLI session."""
        print("=" * 60)
        print("  Online Marketplace - Buyer Interface")
        print("=" * 60)
        print(f"Connecting to server at {self.host}:{self.port}...")
        
        try:
            self._client = BuyerClient(self.host, self.port)
            self._client.connect()
            self._api = BuyerAPI(self._client)
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
            return "buyer (logged in) > "
        return "buyer > "
    
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
            "search": self._cmd_search,
            "item": self._cmd_item,
            "cart": self._cmd_cart,
            "add": self._cmd_add,
            "remove": self._cmd_remove,
            "save": self._cmd_save,
            "clear": self._cmd_clear,
            "feedback": self._cmd_feedback,
            "seller": self._cmd_seller,
            "history": self._cmd_history,
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
        print("\n--- Create New Account ---")
        username = input("Username: ").strip()
        if not username:
            print("Username cannot be empty.")
            return
        
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("Passwords do not match.")
            return
        
        buyer_id = self._api.create_account(username, password)
        print(f"\nAccount created successfully!")
        print(f"Your Buyer ID: {buyer_id}")
        print("You can now log in with your credentials.\n")
    
    def _cmd_login(self, args: List[str]) -> None:
        """Handle user login."""
        if self._api.is_logged_in:
            print("Already logged in. Use 'logout' first.")
            return
        
        print("\n--- Login ---")
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        
        session_id = self._api.login(username, password)
        print(f"Login successful!")
        print(f"Session ID: {session_id[:8]}...\n")
    
    def _cmd_logout(self, args: List[str]) -> None:
        """Handle user logout."""
        if not self._api.is_logged_in:
            print("Not logged in.")
            return
        
        self._api.logout()
        print("Logged out successfully.\n")
    
    def _cmd_search(self, args: List[str]) -> None:
        """Search for items."""
        if len(args) < 1:
            print("Usage: search <category> [keyword1] [keyword2] ...")
            return
        
        try:
            category = int(args[0])
        except ValueError:
            print("Category must be an integer.")
            return
        
        keywords = args[1:6]  # Max 5 keywords
        
        print(f"\nSearching category {category} with keywords: {keywords or '(none)'}")
        print("-" * 70)
        
        items = self._api.search_items(category, keywords)
        
        if not items:
            print("No items found.")
        else:
            self._display_items(items)
        print()
    
    def _cmd_item(self, args: List[str]) -> None:
        """Get item details."""
        if len(args) < 2:
            print("Usage: item <category> <id>")
            return
        
        try:
            item_id = (int(args[0]), int(args[1]))
        except ValueError:
            print("Item ID must be two integers: <category> <id>")
            return
        
        item = self._api.get_item(item_id)
        self._display_item_details(item)
    
    def _cmd_cart(self, args: List[str]) -> None:
        """Display shopping cart."""
        cart_items = self._api.display_cart()
        
        print("\n--- Shopping Cart ---")
        if not cart_items:
            print("Your cart is empty.")
        else:
            print(f"{'Item ID':<15} {'Quantity':>10}")
            print("-" * 30)
            for item in cart_items:
                item_id_str = f"({item.item_id[0]}, {item.item_id[1]})"
                print(f"{item_id_str:<15} {item.quantity:>10}")
        print()
    
    def _cmd_add(self, args: List[str]) -> None:
        """Add item to cart."""
        if len(args) < 3:
            print("Usage: add <category> <id> <quantity>")
            return
        
        try:
            item_id = (int(args[0]), int(args[1]))
            quantity = int(args[2])
        except ValueError:
            print("Arguments must be integers.")
            return
        
        self._api.add_to_cart(item_id, quantity)
        print(f"Added {quantity} of item {item_id} to cart.\n")
    
    def _cmd_remove(self, args: List[str]) -> None:
        """Remove item from cart."""
        if len(args) < 3:
            print("Usage: remove <category> <id> <quantity>")
            return
        
        try:
            item_id = (int(args[0]), int(args[1]))
            quantity = int(args[2])
        except ValueError:
            print("Arguments must be integers.")
            return
        
        self._api.remove_from_cart(item_id, quantity)
        print(f"Removed {quantity} of item {item_id} from cart.\n")
    
    def _cmd_save(self, args: List[str]) -> None:
        """Save cart."""
        self._api.save_cart()
        print("Cart saved. It will persist across sessions.\n")
    
    def _cmd_clear(self, args: List[str]) -> None:
        """Clear cart."""
        confirm = input("Are you sure you want to clear your cart? (y/n): ")
        if confirm.lower() == 'y':
            self._api.clear_cart()
            print("Cart cleared.\n")
        else:
            print("Cancelled.\n")
    
    def _cmd_feedback(self, args: List[str]) -> None:
        """Provide item feedback."""
        if len(args) < 3:
            print("Usage: feedback <category> <id> <up/down>")
            return
        
        try:
            item_id = (int(args[0]), int(args[1]))
        except ValueError:
            print("Item ID must be two integers.")
            return
        
        vote = args[2].lower()
        if vote not in ('up', 'down'):
            print("Vote must be 'up' or 'down'.")
            return
        
        thumbs_up = (vote == 'up')
        self._api.provide_feedback(item_id, thumbs_up)
        print(f"Feedback recorded: thumbs {'up' if thumbs_up else 'down'}\n")
    
    def _cmd_seller(self, args: List[str]) -> None:
        """Get seller rating."""
        if len(args) < 1:
            print("Usage: seller <seller_id>")
            return
        
        try:
            seller_id = int(args[0])
        except ValueError:
            print("Seller ID must be an integer.")
            return
        
        thumbs_up, thumbs_down = self._api.get_seller_rating(seller_id)
        print(f"\nSeller {seller_id} Rating:")
        print(f"  👍 Thumbs Up:   {thumbs_up}")
        print(f"  👎 Thumbs Down: {thumbs_down}")
        if thumbs_up + thumbs_down > 0:
            ratio = thumbs_up / (thumbs_up + thumbs_down) * 100
            print(f"  📊 Positive:    {ratio:.1f}%")
        print()
    
    def _cmd_history(self, args: List[str]) -> None:
        """View purchase history."""
        purchases = self._api.get_purchase_history()
        
        print("\n--- Purchase History ---")
        if not purchases:
            print("No purchases yet.")
        else:
            for i, item_id in enumerate(purchases, 1):
                print(f"  {i}. Item ({item_id[0]}, {item_id[1]})")
        print()
    
    def _cmd_status(self, args: List[str]) -> None:
        """Show current status."""
        print("\n--- Status ---")
        print(f"Server: {self.host}:{self.port}")
        print(f"Connected: {self._client.is_connected()}")
        print(f"Logged in: {self._api.is_logged_in}")
        if self._api.is_logged_in:
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
    # Display Helpers
    # =========================================================================
    
    def _display_items(self, items: List[Item]) -> None:
        """Display a list of items in table format."""
        print(f"{'ID':<12} {'Name':<25} {'Price':>10} {'Qty':>6} {'Condition':<8}")
        print("-" * 70)
        for item in items:
            item_id_str = f"({item.item_id[0]},{item.item_id[1]})"
            name = item.name[:23] + ".." if len(item.name) > 25 else item.name
            print(f"{item_id_str:<12} {name:<25} ${item.sale_price:>8.2f} {item.quantity:>6} {item.condition:<8}")
    
    def _display_item_details(self, item: Item) -> None:
        """Display detailed information for a single item."""
        print(f"\n{'=' * 50}")
        print(f"Item: {item.name}")
        print(f"{'=' * 50}")
        print(f"  ID:         ({item.item_id[0]}, {item.item_id[1]})")
        print(f"  Category:   {item.category}")
        print(f"  Condition:  {item.condition}")
        print(f"  Price:      ${item.sale_price:.2f}")
        print(f"  Quantity:   {item.quantity} available")
        print(f"  Keywords:   {', '.join(item.keywords) or 'None'}")
        print(f"  Seller ID:  {item.seller_id}")
        print(f"  Feedback:   👍 {item.feedback[0]} / 👎 {item.feedback[1]}")
        print()
    
    def _reconnect(self) -> None:
        """Attempt to reconnect to the server."""
        try:
            if self._client:
                self._client.disconnect()
            self._client = BuyerClient(self.host, self.port)
            self._client.connect()
            self._api = BuyerAPI(self._client)
            print("Reconnected successfully.")
            print("Note: You will need to log in again.\n")
        except ConnectionError as e:
            print(f"Reconnection failed: {e}")
            self._running = False


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Online Marketplace Buyer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Connect to localhost:5001
  %(prog)s --host 192.168.1.10      # Connect to specific host
  %(prog)s --port 8080              # Connect to specific port
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
        default=5001,
        help="Server port (default: 5001)"
    )
    
    args = parser.parse_args()
    
    cli = BuyerCLI(args.host, args.port)
    cli.start()


if __name__ == "__main__":
    main()