"""
seller_api.py - High-Level Seller API Implementation

This module provides the business-logic layer for sellers:
- Defines all Seller API methods (Login, RegisterItem, ChangePrice, etc.)
- Constructs proper request messages
- Parses and validates responses
- Manages session state (session_id)

This layer uses SellerClient for communication but handles all the
application-specific logic.
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass

import sys
import os

# Add project root (parent folder) to Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from seller_client.seller_client import SellerClient, ConnectionError


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
class SellerInfo:
    """Represents seller account information."""
    seller_id: int
    name: str
    feedback: Tuple[int, int]  # (thumbs_up, thumbs_down)
    items_sold: int


class APIError(Exception):
    """Raised when an API call fails."""
    pass


class SellerAPI:
    """
    High-level API for seller operations.
    
    This class provides clean, typed methods for all seller operations.
    It handles session management and request/response formatting.
    """
    
    # Valid item conditions
    CONDITION_NEW = "New"
    CONDITION_USED = "Used"
    VALID_CONDITIONS = {CONDITION_NEW, CONDITION_USED}
    
    def __init__(self, client: SellerClient):
        """
        Initialize API with a connected client.
        
        Args:
            client: A SellerClient instance (should already be connected)
        """
        self._client = client
        self._session_id: Optional[str] = None
        self._seller_id: Optional[int] = None
    
    @property
    def is_logged_in(self) -> bool:
        """Check if there's an active session."""
        return self._session_id is not None
    
    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID."""
        return self._session_id
    
    @property
    def seller_id(self) -> Optional[int]:
        """Get current seller's ID (if logged in)."""
        return self._seller_id
    
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
        Create a new seller account.
        
        Args:
            username: Desired username (max 32 chars)
            password: Account password
            
        Returns:
            The assigned seller_id
            
        Raises:
            APIError: If account creation fails
        """
        if len(username) > 32:
            raise APIError("Username must be 32 characters or less")
        
        if not username.strip():
            raise APIError("Username cannot be empty")
        
        if not password:
            raise APIError("Password cannot be empty")
        
        data = self._make_request(
            "CREATE_ACCOUNT",
            {"username": username, "password": password},
            require_session=False
        )
        return data["seller_id"]
    
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
        self._seller_id = data.get("seller_id")
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
            self._seller_id = None
        
        return True
    
    # =========================================================================
    # Seller Rating API
    # =========================================================================
    
    def get_seller_rating(self) -> Tuple[int, int]:
        """
        Get the feedback rating for the current seller.
        
        Returns:
            Tuple of (thumbs_up, thumbs_down)
        """
        data = self._make_request("GET_SELLER_RATING", {})
        return (data["thumbs_up"], data["thumbs_down"])
    
    # =========================================================================
    # Item Management APIs
    # =========================================================================
    
    def register_item(
        self,
        name: str,
        category: int,
        keywords: List[str],
        condition: str,
        sale_price: float,
        quantity: int
    ) -> Tuple[int, int]:
        """
        Register a new item for sale.
        
        Args:
            name: Item name (max 32 chars)
            category: Item category (integer)
            keywords: List of keywords (max 5, each max 8 chars)
            condition: "New" or "Used"
            sale_price: Price per unit
            quantity: Number of units available
            
        Returns:
            The assigned item_id as tuple (category, unique_id)
            
        Raises:
            APIError: If validation fails or registration fails
        """
        # Validate inputs
        if len(name) > 32:
            raise APIError("Item name must be 32 characters or less")
        
        if not name.strip():
            raise APIError("Item name cannot be empty")
        
        if len(keywords) > 5:
            raise APIError("Maximum 5 keywords allowed")
        
        for kw in keywords:
            if len(kw) > 8:
                raise APIError(f"Keyword '{kw}' exceeds 8 character limit")
        
        if condition not in self.VALID_CONDITIONS:
            raise APIError(f"Condition must be '{self.CONDITION_NEW}' or '{self.CONDITION_USED}'")
        
        if sale_price < 0:
            raise APIError("Sale price cannot be negative")
        
        if quantity < 1:
            raise APIError("Quantity must be at least 1")
        
        data = self._make_request(
            "REGISTER_ITEM",
            {
                "name": name,
                "category": category,
                "keywords": keywords,
                "condition": condition,
                "sale_price": sale_price,
                "quantity": quantity
            }
        )
        
        return tuple(data["item_id"])
    
    def change_item_price(self, item_id: Tuple[int, int], new_price: float) -> bool:
        """
        Update the price of an item.
        
        Args:
            item_id: The item to update (category, unique_id)
            new_price: New sale price
            
        Returns:
            True if successful
            
        Raises:
            APIError: If item doesn't exist or seller doesn't own it
        """
        if new_price < 0:
            raise APIError("Price cannot be negative")
        
        self._make_request(
            "CHANGE_ITEM_PRICE",
            {"item_id": list(item_id), "new_price": new_price}
        )
        return True
    
    def update_units_for_sale(self, item_id: Tuple[int, int], quantity_to_remove: int) -> bool:
        """
        Remove a quantity of items from sale.
        
        Args:
            item_id: The item to update
            quantity_to_remove: Number of units to remove from availability
            
        Returns:
            True if successful
            
        Raises:
            APIError: If item doesn't exist or insufficient quantity
        """
        if quantity_to_remove < 1:
            raise APIError("Quantity to remove must be at least 1")
        
        self._make_request(
            "UPDATE_UNITS_FOR_SALE",
            {"item_id": list(item_id), "quantity_to_remove": quantity_to_remove}
        )
        return True
    
    def display_items_for_sale(self) -> List[Item]:
        """
        Get all items currently listed by this seller.
        
        Returns:
            List of items the seller has for sale
        """
        data = self._make_request("DISPLAY_ITEMS_FOR_SALE", {})
        
        return [self._parse_item(item_data) for item_data in data.get("items", [])]
    
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
    from seller_client import SellerClient
    
    # Create client and API
    client = SellerClient("localhost", 5002)
    
    try:
        client.connect()
        api = SellerAPI(client)
        
        # Create account
        seller_id = api.create_account("bob_shop", "securepass")
        print(f"Created seller account with ID: {seller_id}")
        
        # Login
        session = api.login("bob_shop", "securepass")
        print(f"Logged in, session: {session}")
        
        # Register an item
        item_id = api.register_item(
            name="Gaming Laptop XR500",
            category=1,
            keywords=["laptop", "gaming", "fast"],
            condition="New",
            sale_price=1299.99,
            quantity=5
        )
        print(f"Registered item with ID: {item_id}")
        
        # Check seller rating
        thumbs_up, thumbs_down = api.get_seller_rating()
        print(f"Seller rating: {thumbs_up} up, {thumbs_down} down")
        
        # View items
        items = api.display_items_for_sale()
        for item in items:
            print(f"  - {item.name}: ${item.sale_price} ({item.quantity} available)")
        
        # Change price
        api.change_item_price(item_id, 1199.99)
        print(f"Updated price for item {item_id}")
        
        # Logout
        api.logout()
        print("Logged out")
        
    finally:
        client.disconnect()