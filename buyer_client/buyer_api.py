"""
buyer_api.py - High-Level Buyer API Implementation

This module provides the business-logic layer:
- Defines all Buyer API methods (Login, SearchItems, AddToCart, etc.)
- Constructs proper request messages
- Parses and validates responses
- Manages session state (session_id)

This layer uses BuyerClient for communication but handles all the
application-specific logic.
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass
from buyer_client import BuyerClient, ConnectionError


@dataclass
class Item:
    """Represents an item for sale."""
    item_id: Tuple[int, int]  # (category, unique_id)
    name: str
    category: int
    keywords: List[str]
    condition: str
    sale_price: float
    quantity: int
    seller_id: int
    feedback: Tuple[int, int]  # (thumbs_up, thumbs_down)


@dataclass
class CartItem:
    """Represents an item in the shopping cart."""
    item_id: Tuple[int, int]
    quantity: int


class APIError(Exception):
    """Raised when an API call fails."""
    pass


class BuyerAPI:
    """
    High-level API for buyer operations.
    
    This class provides clean, typed methods for all buyer operations.
    It handles session management and request/response formatting.
    """
    
    def __init__(self, client: BuyerClient):
        """
        Initialize API with a connected client.
        
        Args:
            client: A BuyerClient instance (should already be connected)
        """
        self._client = client
        self._session_id: Optional[str] = None
    
    @property
    def is_logged_in(self) -> bool:
        """Check if there's an active session."""
        return self._session_id is not None
    
    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID."""
        return self._session_id
    
    def _make_request(self, request_type: str, data: dict, require_session: bool = True) -> dict:
        """
        Helper to make API requests with common error handling.
        
        Args:
            request_type: The API operation name
            data: Request payload
            require_session: Whether this operation requires an active session
            
        Returns:
            Response data dictionary
            
        Raises:
            APIError: If the request fails or session is required but missing
        """
        if require_session and not self._session_id:
            raise APIError("Must be logged in to perform this operation")
        
        request = {
            "type": request_type,
            "data": data
        }
        
        # Add session_id if we have one
        if self._session_id:
            request["session_id"] = self._session_id
        
        response = self._client.send_request(request)
        
        if response.get("status") == "error":
            raise APIError(response.get("error_message", "Unknown error"))
        
        return response.get("data", {})
    
    # =========================================================================
    # Account Management APIs
    # =========================================================================
    
    def create_account(self, username: str, password: str) -> int:
        """
        Create a new buyer account.
        
        Args:
            username: Desired username (max 32 chars)
            password: Account password
            
        Returns:
            The assigned buyer_id
            
        Raises:
            APIError: If account creation fails
        """
        if len(username) > 32:
            raise APIError("Username must be 32 characters or less")
        
        data = self._make_request(
            "CREATE_ACCOUNT",
            {"username": username, "password": password},
            require_session=False
        )
        return data["buyer_id"]
    
    def login(self, username: str, password: str) -> str:
        """
        Log in to an existing account.
        
        Args:
            username: Account username
            password: Account password
            
        Returns:
            Session ID for the active session
            
        Raises:
            APIError: If login fails (wrong credentials, etc.)
        """
        data = self._make_request(
            "LOGIN",
            {"username": username, "password": password},
            require_session=False
        )
        
        self._session_id = data["session_id"]
        return self._session_id
    
    def logout(self) -> bool:
        """
        End the current session.
        
        Returns:
            True if logout was successful
        """
        if not self._session_id:
            return True  # Already logged out
        
        try:
            self._make_request("LOGOUT", {})
        finally:
            self._session_id = None
        
        return True
    
    # =========================================================================
    # Item Search APIs
    # =========================================================================
    
    def search_items(self, category: int, keywords: List[str] = None) -> List[Item]:
        """
        Search for items by category and keywords.
        
        Args:
            category: Item category to search in
            keywords: Optional list of keywords (max 5, each max 8 chars)
            
        Returns:
            List of matching items, sorted by relevance
        """
        keywords = keywords or []
        
        if len(keywords) > 5:
            raise APIError("Maximum 5 keywords allowed")
        
        for kw in keywords:
            if len(kw) > 8:
                raise APIError(f"Keyword '{kw}' exceeds 8 character limit")
        
        data = self._make_request(
            "SEARCH_ITEMS",
            {"category": category, "keywords": keywords}
        )
        
        return [self._parse_item(item_data) for item_data in data.get("items", [])]
    
    def get_item(self, item_id: Tuple[int, int]) -> Item:
        """
        Get details for a specific item.
        
        Args:
            item_id: Tuple of (category, unique_id)
            
        Returns:
            Item details
        """
        data = self._make_request(
            "GET_ITEM",
            {"item_id": list(item_id)}
        )
        return self._parse_item(data["item"])
    
    # =========================================================================
    # Shopping Cart APIs
    # =========================================================================
    
    def add_to_cart(self, item_id: Tuple[int, int], quantity: int) -> bool:
        """
        Add items to the shopping cart.
        
        Args:
            item_id: The item to add
            quantity: Number of units to add
            
        Returns:
            True if successful
        """
        if quantity <= 0:
            raise APIError("Quantity must be positive")
        
        self._make_request(
            "ADD_TO_CART",
            {"item_id": list(item_id), "quantity": quantity}
        )
        return True
    
    def remove_from_cart(self, item_id: Tuple[int, int], quantity: int) -> bool:
        """
        Remove items from the shopping cart.
        
        Args:
            item_id: The item to remove
            quantity: Number of units to remove
            
        Returns:
            True if successful
        """
        if quantity <= 0:
            raise APIError("Quantity must be positive")
        
        self._make_request(
            "REMOVE_FROM_CART",
            {"item_id": list(item_id), "quantity": quantity}
        )
        return True
    
    def display_cart(self) -> List[CartItem]:
        """
        Get contents of the shopping cart.
        
        Returns:
            List of items in cart with quantities
        """
        data = self._make_request("DISPLAY_CART", {})
        
        return [
            CartItem(
                item_id=tuple(item["item_id"]),
                quantity=item["quantity"]
            )
            for item in data.get("cart_items", [])
        ]
    
    def save_cart(self) -> bool:
        """
        Save cart to persist across sessions.
        
        Returns:
            True if successful
        """
        self._make_request("SAVE_CART", {})
        return True
    
    def clear_cart(self) -> bool:
        """
        Clear all items from the cart.
        
        Returns:
            True if successful
        """
        self._make_request("CLEAR_CART", {})
        return True
    
    # =========================================================================
    # Feedback APIs
    # =========================================================================
    
    def provide_feedback(self, item_id: Tuple[int, int], thumbs_up: bool) -> bool:
        """
        Provide feedback for an item.
        
        Args:
            item_id: The item to rate
            thumbs_up: True for thumbs up, False for thumbs down
            
        Returns:
            True if successful
        """
        self._make_request(
            "PROVIDE_FEEDBACK",
            {"item_id": list(item_id), "thumbs_up": thumbs_up}
        )
        return True
    
    def get_seller_rating(self, seller_id: int) -> Tuple[int, int]:
        """
        Get feedback ratings for a seller.
        
        Args:
            seller_id: The seller's ID
            
        Returns:
            Tuple of (thumbs_up, thumbs_down)
        """
        data = self._make_request(
            "GET_SELLER_RATING",
            {"seller_id": seller_id}
        )
        return (data["thumbs_up"], data["thumbs_down"])
    
    # =========================================================================
    # Purchase History APIs
    # =========================================================================
    
    def get_purchase_history(self) -> List[Tuple[int, int]]:
        """
        Get history of purchased items.
        
        Returns:
            List of item_ids that were purchased
        """
        data = self._make_request("GET_BUYER_PURCHASES", {})
        return [tuple(item_id) for item_id in data.get("purchases", [])]
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _parse_item(self, item_data: dict) -> Item:
        """Parse raw item data into an Item object."""
        return Item(
            item_id=tuple(item_data["item_id"]),
            name=item_data["name"],
            category=item_data["category"],
            keywords=item_data.get("keywords", []),
            condition=item_data["condition"],
            sale_price=item_data["sale_price"],
            quantity=item_data["quantity"],
            seller_id=item_data["seller_id"],
            feedback=tuple(item_data.get("feedback", [0, 0]))
        )


# Example usage
if __name__ == "__main__":
    from buyer_client import BuyerClient
    
    # Create client and API
    client = BuyerClient("localhost", 5001)
    
    try:
        client.connect()
        api = BuyerAPI(client)
        
        # Create account
        buyer_id = api.create_account("alice", "password123")
        print(f"Created account with ID: {buyer_id}")
        
        # Login
        session = api.login("alice", "password123")
        print(f"Logged in, session: {session}")
        
        # Search for items
        items = api.search_items(category=1, keywords=["laptop", "gaming"])
        for item in items:
            print(f"Found: {item.name} - ${item.sale_price}")
        
        # Add to cart
        if items:
            api.add_to_cart(items[0].item_id, quantity=1)
            print("Added item to cart")
        
        # View cart
        cart = api.display_cart()
        print(f"Cart has {len(cart)} items")
        
        # Logout
        api.logout()
        print("Logged out")
        
    finally:
        client.disconnect()