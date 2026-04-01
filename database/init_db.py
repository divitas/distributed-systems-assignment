"""
Database initialization script
Creates SQLite databases with proper schemas
"""

import sqlite3
import os


def init_customer_database(db_path):
    """
    Initialize customer database schema
    
    Stores:
    - Sellers (accounts, ratings, items sold)
    - Buyers (accounts, purchases)
    - Sessions (login sessions with timeout tracking)
    - Shopping carts (per-session and saved carts)
    """
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    
    # Sellers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sellers (
            seller_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            seller_name TEXT NOT NULL,
            thumbs_up INTEGER DEFAULT 0,
            thumbs_down INTEGER DEFAULT 0,
            items_sold INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Buyers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyers (
            buyer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            buyer_name TEXT NOT NULL,
            items_purchased INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Seller sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_sessions (
            session_id TEXT PRIMARY KEY,
            seller_id INTEGER NOT NULL,
            last_activity REAL NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
        )
    ''')
    
    # Buyer sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyer_sessions (
            session_id TEXT PRIMARY KEY,
            buyer_id INTEGER NOT NULL,
            last_activity REAL NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id)
        )
    ''')
    
    # Shopping carts (session-specific, active cart)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shopping_carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            buyer_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id),
            UNIQUE(session_id, item_id)
        )
    ''')
    
    # Saved carts (user-specific, persists across sessions)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id),
            UNIQUE(buyer_id, item_id)
        )
    ''')
    
    # Purchase history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchase_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id)
        )
    ''')
    
    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_seller_sessions_seller ON seller_sessions(seller_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyer_sessions_buyer ON buyer_sessions(buyer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shopping_carts_session ON shopping_carts(session_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shopping_carts_buyer ON shopping_carts(buyer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_saved_carts_buyer ON saved_carts(buyer_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_purchase_history_buyer ON purchase_history(buyer_id)')
    
    conn.commit()
    conn.close()
    
    print(f"Customer database initialized at {db_path}")


def init_product_database(db_path):
    """
    Initialize product database schema
    
    Stores:
    - Items (product listings with all attributes)
    - Item feedback (thumbs up/down for items)
    - Category counters (for generating sequential item IDs per category)
    """
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    
    # Items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category INTEGER NOT NULL,
            keywords TEXT,
            condition TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            thumbs_up INTEGER DEFAULT 0,
            thumbs_down INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Category counters for generating sequential item IDs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS category_counters (
            category INTEGER PRIMARY KEY,
            last_id INTEGER DEFAULT 0
        )
    ''')
    
    # Create indexes for better search performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_seller ON items(seller_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)')
    
    # Initialize category counters
    for category in range(1, 9):
        cursor.execute('''
            INSERT OR IGNORE INTO category_counters (category, last_id)
            VALUES (?, 0)
        ''', (category,))
    
    conn.commit()
    conn.close()
    
    print(f"Product database initialized at {db_path}")


if __name__ == '__main__':
    # Initialize both databases
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    import config
    
    init_customer_database(config.CUSTOMER_DB_FILE)
    init_product_database(config.PRODUCT_DB_FILE)
    
    print("\nDatabase initialization complete!")
