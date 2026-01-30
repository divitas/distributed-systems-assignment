"""
Shared utility functions used across the system
"""

import time
import uuid
import hashlib
import threading
from datetime import datetime, timedelta


def generate_session_id():
    """
    Generate a unique session ID
    
    Returns:
        str: Unique session identifier
    """
    return str(uuid.uuid4())


def generate_item_id(category, sequence):
    """
    Generate a unique item ID based on category and sequence
    
    Args:
        category: Item category (integer)
        sequence: Sequence number (integer)
        
    Returns:
        str: Item ID in format "category-sequence"
    """
    return f"{category}-{sequence}"


def parse_item_id(item_id):
    """
    Parse item ID to extract category and sequence
    
    Args:
        item_id: Item ID string
        
    Returns:
        tuple: (category, sequence) or (None, None) if invalid
    """
    try:
        parts = item_id.split('-')
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except:
        pass
    return None, None


def get_current_timestamp():
    """
    Get current timestamp in seconds since epoch
    
    Returns:
        float: Current timestamp
    """
    return time.time()


def is_session_expired(last_activity, timeout_seconds):
    """
    Check if a session has expired based on last activity
    
    Args:
        last_activity: Timestamp of last activity
        timeout_seconds: Session timeout in seconds
        
    Returns:
        bool: True if session expired
    """
    current_time = get_current_timestamp()
    return (current_time - last_activity) > timeout_seconds


def validate_item_name(name):
    """
    Validate item name
    
    Args:
        name: Item name string
        
    Returns:
        bool: True if valid
    """
    return isinstance(name, str) and 0 < len(name) <= 32


def validate_keywords(keywords):
    """
    Validate keywords list
    
    Args:
        keywords: List of keyword strings
        
    Returns:
        bool: True if valid
    """
    if not isinstance(keywords, list):
        return False
    if len(keywords) > 5:
        return False
    for keyword in keywords:
        if not isinstance(keyword, str) or len(keyword) > 8:
            return False
    return True


def validate_condition(condition):
    """
    Validate item condition
    
    Args:
        condition: Condition string
        
    Returns:
        bool: True if valid
    """
    return condition in ["New", "Used"]


def validate_price(price):
    """
    Validate price
    
    Args:
        price: Price value
        
    Returns:
        bool: True if valid
    """
    try:
        price_float = float(price)
        return price_float >= 0
    except:
        return False


def validate_quantity(quantity):
    """
    Validate quantity
    
    Args:
        quantity: Quantity value
        
    Returns:
        bool: True if valid
    """
    try:
        quantity_int = int(quantity)
        return quantity_int >= 0
    except:
        return False


def calculate_search_score(item, category, keywords):
    """
    Calculate relevance score for search results
    Scoring:
    - Category match: mandatory
    - Exact keyword match in item name: 10 points
    - Partial keyword match in item name: 5 points
    - Keyword in item keywords: 3 points per keyword
    
    Args:
        item: Item dictionary
        category: Search category
        keywords: List of search keywords
        
    Returns:
        int: Relevance score (higher is better)
    """
    score = 0
    
    # Category must match
    if item.get('category') != category:
        return 0
    
    item_name = item.get('name', '').lower()
    item_keywords = [k.lower() for k in item.get('keywords', [])]
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        
        # Exact match in item name
        if keyword_lower == item_name:
            score += 10
        # Partial match in item name
        elif keyword_lower in item_name:
            score += 5
        
        # Match in item keywords
        if keyword_lower in item_keywords:
            score += 3
    
    return score


class ThreadSafeCounter:
    """Thread-safe counter for generating sequential IDs"""
    
    def __init__(self, initial_value=0):
        self.value = initial_value
        self.lock = threading.Lock()
    
    def increment(self):
        """Increment and return new value"""
        with self.lock:
            self.value += 1
            return self.value
    
    def get(self):
        """Get current value"""
        with self.lock:
            return self.value
    
    def set(self, value):
        """Set value"""
        with self.lock:
            self.value = value


class ConnectionPool:
    """
    Simple connection pool for managing database connections
    """
    
    def __init__(self, create_connection_func, pool_size=10, max_overflow=20):
        """
        Initialize connection pool
        
        Args:
            create_connection_func: Function that creates a new connection
            pool_size: Number of connections to maintain
            max_overflow: Additional connections allowed beyond pool size
        """
        self.create_connection = create_connection_func
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool = []
        self.in_use = set()
        self.lock = threading.Lock()
        
        # Pre-create pool connections
        for _ in range(pool_size):
            conn = self.create_connection()
            self.pool.append(conn)
    
    def get_connection(self):
        """
        Get a connection from the pool
        
        Returns:
            connection object
        """
        with self.lock:
            # Try to get from pool
            if self.pool:
                conn = self.pool.pop()
                self.in_use.add(id(conn))
                return conn
            
            # Create new if under max
            if len(self.in_use) < (self.pool_size + self.max_overflow):
                conn = self.create_connection()
                self.in_use.add(id(conn))
                return conn
            
        # Wait and retry if pool exhausted
        time.sleep(0.01)
        return self.get_connection()
    
    def return_connection(self, conn):
        """
        Return a connection to the pool
        
        Args:
            conn: Connection to return
        """
        with self.lock:
            conn_id = id(conn)
            if conn_id in self.in_use:
                self.in_use.remove(conn_id)
                if len(self.pool) < self.pool_size:
                    self.pool.append(conn)
                else:
                    # Close excess connections
                    try:
                        conn.close()
                    except:
                        pass
    
    def close_all(self):
        """Close all connections in the pool"""
        with self.lock:
            for conn in self.pool:
                try:
                    conn.close()
                except:
                    pass
            self.pool.clear()
            self.in_use.clear()


def format_feedback(thumbs_up, thumbs_down):
    """
    Format feedback for display
    
    Args:
        thumbs_up: Number of thumbs up
        thumbs_down: Number of thumbs down
        
    Returns:
        str: Formatted feedback string
    """
    total = thumbs_up + thumbs_down
    if total == 0:
        return f"No feedback yet (👍 0, 👎 0)"
    
    percentage = (thumbs_up / total) * 100
    return f"👍 {thumbs_up} | 👎 {thumbs_down} ({percentage:.1f}% positive)"


def format_item_display(item):
    """
    Format item for display
    
    Args:
        item: Item dictionary
        
    Returns:
        str: Formatted item string
    """
    lines = [
        f"Item ID: {item['item_id']}",
        f"Name: {item['name']}",
        f"Category: {item['category']}",
        f"Condition: {item['condition']}",
        f"Price: ${item['price']:.2f}",
        f"Available: {item['quantity']} units",
        f"Seller ID: {item['seller_id']}",
        f"Keywords: {', '.join(item.get('keywords', []))}",
        f"Feedback: {format_feedback(item['thumbs_up'], item['thumbs_down'])}"
    ]
    return '\n'.join(lines)
