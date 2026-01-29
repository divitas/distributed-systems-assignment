"""
product_database_sqlite.py - Product Database with SQLite Backend

Handles:
- Item registration
- Item search by category and keywords
- Item information retrieval
- Inventory management
- Seller item listings

Uses SQLite with proper connection pooling and thread-safety.
"""

import sqlite3
import threading
from typing import Optional, Dict, List
from contextlib import contextmanager
import json


class ProductDatabase:
    """
    Thread-safe product database using SQLite.
    """
    
    def __init__(self, db_path: str = "products.db"):
        """
        Initialize the database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.local = threading.local()
        
        # Initialize database schema
        self._init_schema()
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a thread-local database connection.
        Each thread gets its own connection for thread-safety.
        """
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0  # Wait up to 30 seconds for locks
            )
            # Enable foreign keys
            self.local.connection.execute("PRAGMA foreign_keys = ON")
            # Use WAL mode for better concurrency
            self.local.connection.execute("PRAGMA journal_mode = WAL")
            # Row factory for dict-like access
            self.local.connection.row_factory = sqlite3.Row
        
        return self.local.connection
    
    @contextmanager
    def _get_cursor(self):
        """Context manager for database cursor with automatic commit/rollback."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
    
    def _init_schema(self):
        """Initialize database schema."""
        with self._get_cursor() as cursor:
            # Items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category INTEGER NOT NULL,
                    condition TEXT NOT NULL CHECK(condition IN ('New', 'Used')),
                    sale_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    created_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            # Keywords table (for item search)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_keywords (
                    item_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    PRIMARY KEY (item_id, keyword),
                    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_seller 
                ON items(seller_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_category 
                ON items(category)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_keywords_keyword 
                ON item_keywords(keyword)
            """)
    
    # =========================================================================
    # Item Registration
    # =========================================================================
    
    def register_item(self, seller_id: int, name: str, category: int, 
                     keywords: List[str], condition: str, 
                     sale_price: float, quantity: int) -> Dict:
        """
        Register a new item for sale.
        
        Returns:
            {'status': 'success', 'data': {'item_id': int}}
            or {'status': 'error', 'error_message': str}
        """
        try:
            with self._get_cursor() as cursor:
                # Insert item
                cursor.execute("""
                    INSERT INTO items (seller_id, name, category, condition, sale_price, quantity)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (seller_id, name, category, condition, sale_price, quantity))
                
                item_id = cursor.lastrowid
                
                # Insert keywords
                for keyword in keywords:
                    cursor.execute("""
                        INSERT INTO item_keywords (item_id, keyword)
                        VALUES (?, ?)
                    """, (item_id, keyword.lower()))
                
                return {
                    'status': 'success',
                    'data': {'item_id': item_id}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    # =========================================================================
    # Item Search and Retrieval
    # =========================================================================
    
    def search_items(self, category: Optional[int] = None, 
                    keywords: Optional[List[str]] = None) -> Dict:
        """
        Search for items by category and/or keywords.
        
        Returns:
            {'status': 'success', 'data': {'items': [...]}}
        """
        try:
            with self._get_cursor() as cursor:
                # Build query
                if category is not None and keywords:
                    # Search by category AND keywords
                    placeholders = ','.join('?' * len(keywords))
                    query = f"""
                        SELECT DISTINCT i.item_id, i.seller_id, i.name, i.category, 
                               i.condition, i.sale_price, i.quantity
                        FROM items i
                        INNER JOIN item_keywords k ON i.item_id = k.item_id
                        WHERE i.category = ? AND k.keyword IN ({placeholders})
                        AND i.quantity > 0
                    """
                    params = [category] + [kw.lower() for kw in keywords]
                    cursor.execute(query, params)
                
                elif category is not None:
                    # Search by category only
                    cursor.execute("""
                        SELECT item_id, seller_id, name, category, condition, sale_price, quantity
                        FROM items
                        WHERE category = ? AND quantity > 0
                    """, (category,))
                
                elif keywords:
                    # Search by keywords only
                    placeholders = ','.join('?' * len(keywords))
                    query = f"""
                        SELECT DISTINCT i.item_id, i.seller_id, i.name, i.category,
                               i.condition, i.sale_price, i.quantity
                        FROM items i
                        INNER JOIN item_keywords k ON i.item_id = k.item_id
                        WHERE k.keyword IN ({placeholders})
                        AND i.quantity > 0
                    """
                    params = [kw.lower() for kw in keywords]
                    cursor.execute(query, params)
                
                else:
                    # Return all items
                    cursor.execute("""
                        SELECT item_id, seller_id, name, category, condition, sale_price, quantity
                        FROM items
                        WHERE quantity > 0
                    """)
                
                items = []
                for row in cursor.fetchall():
                    # Get keywords for this item
                    cursor.execute("""
                        SELECT keyword FROM item_keywords WHERE item_id = ?
                    """, (row[0],))
                    item_keywords = [kw[0] for kw in cursor.fetchall()]
                    
                    items.append({
                        'item_id': row[0],
                        'seller_id': row[1],
                        'name': row[2],
                        'category': row[3],
                        'condition': row[4],
                        'sale_price': row[5],
                        'quantity': row[6],
                        'keywords': item_keywords
                    })
                
                return {
                    'status': 'success',
                    'data': {'items': items}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def get_item(self, item_id: int) -> Dict:
        """Get detailed information about a specific item."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    SELECT item_id, seller_id, name, category, condition, sale_price, quantity
                    FROM items
                    WHERE item_id = ?
                """, (item_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    return {
                        'status': 'error',
                        'error_message': 'Item not found'
                    }
                
                # Get keywords
                cursor.execute("""
                    SELECT keyword FROM item_keywords WHERE item_id = ?
                """, (item_id,))
                keywords = [kw[0] for kw in cursor.fetchall()]
                
                item = {
                    'item_id': row[0],
                    'seller_id': row[1],
                    'name': row[2],
                    'category': row[3],
                    'condition': row[4],
                    'sale_price': row[5],
                    'quantity': row[6],
                    'keywords': keywords
                }
                
                return {
                    'status': 'success',
                    'data': {'item': item}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def get_seller_items(self, seller_id: int) -> Dict:
        """Get all items for a specific seller."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    SELECT item_id, seller_id, name, category, condition, sale_price, quantity
                    FROM items
                    WHERE seller_id = ?
                """, (seller_id,))
                
                items = []
                for row in cursor.fetchall():
                    # Get keywords
                    cursor.execute("""
                        SELECT keyword FROM item_keywords WHERE item_id = ?
                    """, (row[0],))
                    keywords = [kw[0] for kw in cursor.fetchall()]
                    
                    items.append({
                        'item_id': row[0],
                        'seller_id': row[1],
                        'name': row[2],
                        'category': row[3],
                        'condition': row[4],
                        'sale_price': row[5],
                        'quantity': row[6],
                        'keywords': keywords
                    })
                
                return {
                    'status': 'success',
                    'data': {'items': items}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    # =========================================================================
    # Item Updates
    # =========================================================================
    
    def update_item_price(self, item_id: int, new_price: float) -> Dict:
        """Update item price."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    UPDATE items SET sale_price = ?
                    WHERE item_id = ?
                """, (new_price, item_id))
                
                if cursor.rowcount == 0:
                    return {
                        'status': 'error',
                        'error_message': 'Item not found'
                    }
                
                return {'status': 'success', 'data': {}}
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def update_item_quantity(self, item_id: int, quantity_change: int) -> Dict:
        """
        Update item quantity (can be positive or negative).
        
        Args:
            item_id: Item to update
            quantity_change: Amount to change (negative to decrease)
        """
        try:
            with self._get_cursor() as cursor:
                # Get current quantity
                cursor.execute("""
                    SELECT quantity FROM items WHERE item_id = ?
                """, (item_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    return {
                        'status': 'error',
                        'error_message': 'Item not found'
                    }
                
                current_qty = row[0]
                new_qty = current_qty + quantity_change
                
                if new_qty < 0:
                    return {
                        'status': 'error',
                        'error_message': f'Insufficient quantity. Only {current_qty} available.'
                    }
                
                # Update quantity
                cursor.execute("""
                    UPDATE items SET quantity = ?
                    WHERE item_id = ?
                """, (new_qty, item_id))
                
                return {
                    'status': 'success',
                    'data': {'new_quantity': new_qty}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def close(self):
        """Close database connections."""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()


if __name__ == "__main__":
    # Test the database
    db = ProductDatabase("test_products.db")
    
    # Test item registration
    result = db.register_item(
        seller_id=1,
        name="Test Product",
        category=5,
        keywords=["test", "product"],
        condition="New",
        sale_price=99.99,
        quantity=10
    )
    print(f"Register item: {result}")
    
    if result['status'] == 'success':
        item_id = result['data']['item_id']
        
        # Test get item
        result = db.get_item(item_id)
        print(f"Get item: {result}")
        
        # Test search
        result = db.search_items(category=5, keywords=["test"])
        print(f"Search items: {result}")
        
        # Test update price
        result = db.update_item_price(item_id, 79.99)
        print(f"Update price: {result}")
        
        # Test update quantity
        result = db.update_item_quantity(item_id, -2)
        print(f"Update quantity: {result}")
        
        # Test get seller items
        result = db.get_seller_items(1)
        print(f"Get seller items: {result}")
    
    db.close()
    print("\nTest completed!")