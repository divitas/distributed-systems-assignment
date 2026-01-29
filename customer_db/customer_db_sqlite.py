"""
customer_database_sqlite.py - Customer Database with SQLite Backend

Handles:
- Seller accounts and authentication
- Buyer accounts and authentication  
- Session management
- Shopping carts
- Seller ratings/feedback

Uses SQLite with proper connection pooling and thread-safety.
"""

import sqlite3
import hashlib
import secrets
import time
import threading
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager
import json


class CustomerDatabase:
    """
    Thread-safe customer database using SQLite.
    """
    
    def __init__(self, db_path: str = "customer.db"):
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
            # Sellers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sellers (
                    seller_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    thumbs_up INTEGER DEFAULT 0,
                    thumbs_down INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            # Buyers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS buyers (
                    buyer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    user_type TEXT NOT NULL CHECK(user_type IN ('seller', 'buyer')),
                    created_at REAL NOT NULL,
                    last_activity REAL NOT NULL
                )
            """)
            
            # Shopping carts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cart_items (
                    buyer_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    added_at REAL DEFAULT (julianday('now')),
                    PRIMARY KEY (buyer_id, item_id),
                    FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id) ON DELETE CASCADE
                )
            """)
            
            # Saved carts (for persistence across sessions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_carts (
                    buyer_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    saved_at REAL DEFAULT (julianday('now')),
                    PRIMARY KEY (buyer_id, item_id),
                    FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user 
                ON sessions(user_id, user_type)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_activity 
                ON sessions(last_activity)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cart_buyer 
                ON cart_items(buyer_id)
            """)
    
    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return secrets.token_urlsafe(32)
    
    # =========================================================================
    # Seller Operations
    # =========================================================================
    
    def create_seller(self, username: str, password: str) -> Dict:
        """
        Create a new seller account.
        
        Returns:
            {'status': 'success', 'data': {'seller_id': int}}
            or {'status': 'error', 'error_message': str}
        """
        try:
            with self._get_cursor() as cursor:
                password_hash = self._hash_password(password)
                
                cursor.execute("""
                    INSERT INTO sellers (username, password_hash)
                    VALUES (?, ?)
                """, (username, password_hash))
                
                seller_id = cursor.lastrowid
                
                return {
                    'status': 'success',
                    'data': {'seller_id': seller_id}
                }
        
        except sqlite3.IntegrityError:
            return {
                'status': 'error',
                'error_message': 'Username already exists'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def login_seller(self, username: str, password: str) -> Dict:
        """
        Authenticate seller and create session.
        
        Returns:
            {'status': 'success', 'data': {'session_id': str, 'seller_id': int}}
            or {'status': 'error', 'error_message': str}
        """
        try:
            with self._get_cursor() as cursor:
                password_hash = self._hash_password(password)
                
                cursor.execute("""
                    SELECT seller_id FROM sellers
                    WHERE username = ? AND password_hash = ?
                """, (username, password_hash))
                
                row = cursor.fetchone()
                
                if not row:
                    return {
                        'status': 'error',
                        'error_message': 'Invalid username or password'
                    }
                
                seller_id = row[0]
                session_id = self._generate_session_id()
                now = time.time()
                
                # Create session
                cursor.execute("""
                    INSERT INTO sessions (session_id, user_id, user_type, created_at, last_activity)
                    VALUES (?, ?, 'seller', ?, ?)
                """, (session_id, seller_id, now, now))
                
                return {
                    'status': 'success',
                    'data': {
                        'session_id': session_id,
                        'seller_id': seller_id
                    }
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def get_seller_rating(self, seller_id: int) -> Dict:
        """Get seller's feedback ratings."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    SELECT thumbs_up, thumbs_down FROM sellers
                    WHERE seller_id = ?
                """, (seller_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    return {
                        'status': 'error',
                        'error_message': 'Seller not found'
                    }
                
                return {
                    'status': 'success',
                    'data': {
                        'thumbs_up': row[0],
                        'thumbs_down': row[1]
                    }
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def update_seller_feedback(self, seller_id: int, thumbs_up: bool) -> Dict:
        """Update seller feedback."""
        try:
            with self._get_cursor() as cursor:
                if thumbs_up:
                    cursor.execute("""
                        UPDATE sellers SET thumbs_up = thumbs_up + 1
                        WHERE seller_id = ?
                    """, (seller_id,))
                else:
                    cursor.execute("""
                        UPDATE sellers SET thumbs_down = thumbs_down + 1
                        WHERE seller_id = ?
                    """, (seller_id,))
                
                return {'status': 'success', 'data': {}}
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    # =========================================================================
    # Buyer Operations
    # =========================================================================
    
    def create_buyer(self, username: str, password: str) -> Dict:
        """Create a new buyer account."""
        try:
            with self._get_cursor() as cursor:
                password_hash = self._hash_password(password)
                
                cursor.execute("""
                    INSERT INTO buyers (username, password_hash)
                    VALUES (?, ?)
                """, (username, password_hash))
                
                buyer_id = cursor.lastrowid
                
                return {
                    'status': 'success',
                    'data': {'buyer_id': buyer_id}
                }
        
        except sqlite3.IntegrityError:
            return {
                'status': 'error',
                'error_message': 'Username already exists'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def login_buyer(self, username: str, password: str) -> Dict:
        """Authenticate buyer and create session."""
        try:
            with self._get_cursor() as cursor:
                password_hash = self._hash_password(password)
                
                cursor.execute("""
                    SELECT buyer_id FROM buyers
                    WHERE username = ? AND password_hash = ?
                """, (username, password_hash))
                
                row = cursor.fetchone()
                
                if not row:
                    return {
                        'status': 'error',
                        'error_message': 'Invalid username or password'
                    }
                
                buyer_id = row[0]
                session_id = self._generate_session_id()
                now = time.time()
                
                # Create session
                cursor.execute("""
                    INSERT INTO sessions (session_id, user_id, user_type, created_at, last_activity)
                    VALUES (?, ?, 'buyer', ?, ?)
                """, (session_id, buyer_id, now, now))
                
                # Load saved cart if exists
                cursor.execute("""
                    INSERT OR REPLACE INTO cart_items (buyer_id, session_id, item_id, quantity)
                    SELECT buyer_id, ?, item_id, quantity
                    FROM saved_carts
                    WHERE buyer_id = ?
                """, (session_id, buyer_id))
                
                return {
                    'status': 'success',
                    'data': {
                        'session_id': session_id,
                        'buyer_id': buyer_id
                    }
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def validate_session(self, session_id: str, update_activity: bool = True) -> Dict:
        """
        Validate a session and optionally update last activity time.
        
        Returns:
            {'status': 'success', 'data': {'valid': bool, 'user_id': int, 'user_type': str}}
        """
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, user_type, last_activity FROM sessions
                    WHERE session_id = ?
                """, (session_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    return {
                        'status': 'success',
                        'data': {'valid': False}
                    }
                
                user_id, user_type, last_activity = row
                
                # Update activity if requested
                if update_activity:
                    cursor.execute("""
                        UPDATE sessions SET last_activity = ?
                        WHERE session_id = ?
                    """, (time.time(), session_id))
                
                return {
                    'status': 'success',
                    'data': {
                        'valid': True,
                        'user_id': user_id,
                        'user_type': user_type
                    }
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def logout(self, session_id: str) -> Dict:
        """Delete a session (logout)."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM sessions WHERE session_id = ?
                """, (session_id,))
                
                return {'status': 'success', 'data': {}}
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def cleanup_expired_sessions(self, timeout_seconds: int) -> Dict:
        """Remove sessions that haven't been active within timeout period."""
        try:
            with self._get_cursor() as cursor:
                cutoff_time = time.time() - timeout_seconds
                
                cursor.execute("""
                    DELETE FROM sessions WHERE last_activity < ?
                """, (cutoff_time,))
                
                deleted_count = cursor.rowcount
                
                return {
                    'status': 'success',
                    'data': {'deleted_sessions': deleted_count}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    # =========================================================================
    # Shopping Cart Operations
    # =========================================================================
    
    def add_to_cart(self, buyer_id: int, session_id: str, item_id: int, quantity: int) -> Dict:
        """Add item to shopping cart."""
        try:
            with self._get_cursor() as cursor:
                # Check if item already in cart
                cursor.execute("""
                    SELECT quantity FROM cart_items
                    WHERE buyer_id = ? AND item_id = ?
                """, (buyer_id, item_id))
                
                row = cursor.fetchone()
                
                if row:
                    # Update quantity
                    new_quantity = row[0] + quantity
                    cursor.execute("""
                        UPDATE cart_items SET quantity = ?, session_id = ?
                        WHERE buyer_id = ? AND item_id = ?
                    """, (new_quantity, session_id, buyer_id, item_id))
                else:
                    # Insert new
                    cursor.execute("""
                        INSERT INTO cart_items (buyer_id, session_id, item_id, quantity)
                        VALUES (?, ?, ?, ?)
                    """, (buyer_id, session_id, item_id, quantity))
                
                return {'status': 'success', 'data': {}}
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def remove_from_cart(self, buyer_id: int, item_id: int, quantity: int) -> Dict:
        """Remove item from shopping cart."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    SELECT quantity FROM cart_items
                    WHERE buyer_id = ? AND item_id = ?
                """, (buyer_id, item_id))
                
                row = cursor.fetchone()
                
                if not row:
                    return {'status': 'success', 'data': {}}
                
                current_qty = row[0]
                new_qty = current_qty - quantity
                
                if new_qty <= 0:
                    # Remove completely
                    cursor.execute("""
                        DELETE FROM cart_items
                        WHERE buyer_id = ? AND item_id = ?
                    """, (buyer_id, item_id))
                else:
                    # Update quantity
                    cursor.execute("""
                        UPDATE cart_items SET quantity = ?
                        WHERE buyer_id = ? AND item_id = ?
                    """, (new_qty, buyer_id, item_id))
                
                return {'status': 'success', 'data': {}}
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def get_cart(self, buyer_id: int) -> Dict:
        """Get shopping cart contents."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    SELECT item_id, quantity FROM cart_items
                    WHERE buyer_id = ?
                """, (buyer_id,))
                
                items = [
                    {'item_id': row[0], 'quantity': row[1]}
                    for row in cursor.fetchall()
                ]
                
                return {
                    'status': 'success',
                    'data': {'cart_items': items}
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def save_cart(self, buyer_id: int) -> Dict:
        """Save current cart for persistence across sessions."""
        try:
            with self._get_cursor() as cursor:
                # Clear existing saved cart
                cursor.execute("""
                    DELETE FROM saved_carts WHERE buyer_id = ?
                """, (buyer_id,))
                
                # Copy current cart to saved
                cursor.execute("""
                    INSERT INTO saved_carts (buyer_id, item_id, quantity)
                    SELECT buyer_id, item_id, quantity
                    FROM cart_items
                    WHERE buyer_id = ?
                """, (buyer_id,))
                
                return {'status': 'success', 'data': {}}
        
        except Exception as e:
            return {
                'status': 'error',
                'error_message': str(e)
            }
    
    def clear_cart(self, buyer_id: int) -> Dict:
        """Clear shopping cart."""
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM cart_items WHERE buyer_id = ?
                """, (buyer_id,))
                
                return {'status': 'success', 'data': {}}
        
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
    db = CustomerDatabase("test_customer.db")
    
    # Test seller creation
    result = db.create_seller("test_seller", "password123")
    print(f"Create seller: {result}")
    
    # Test seller login
    result = db.login_seller("test_seller", "password123")
    print(f"Login seller: {result}")
    
    if result['status'] == 'success':
        session_id = result['data']['session_id']
        seller_id = result['data']['seller_id']
        
        # Test session validation
        result = db.validate_session(session_id)
        print(f"Validate session: {result}")
        
        # Test seller rating
        result = db.get_seller_rating(seller_id)
        print(f"Get rating: {result}")
        
        # Test logout
        result = db.logout(session_id)
        print(f"Logout: {result}")
    
    db.close()
    print("\nTest completed!")