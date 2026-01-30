"""
Product Database Server
Handles all product-related data: items, inventory, search, feedback
Runs as a separate process and communicates via TCP sockets
"""

import socket
import threading
import sqlite3
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.protocol import Protocol
from shared.constants import *
from shared.utils import generate_item_id, calculate_search_score


class ProductDatabase:
    """Product Database Server"""
    
    def __init__(self, db_path, host, port):
        self.db_path = db_path
        self.host = host
        self.port = port
        self.running = False
        
        # Thread-safe database connection handling
        self.conn_lock = threading.Lock()
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema if not exists"""
        from database.init_db import init_product_database
        init_product_database(self.db_path)
    
    def _get_connection(self):
        """Get a thread-safe database connection"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def handle_request(self, request):
        """
        Handle incoming request and return response
        
        Args:
            request: Request dictionary
            
        Returns:
            Response dictionary
        """
        operation = request.get('operation')
        data = request.get('data', {})
        
        try:
            if operation == OP_REGISTER_ITEM:
                return self._register_item(data)
            elif operation == OP_GET_ITEM:
                return self._get_item(data)
            elif operation == OP_UPDATE_ITEM_PRICE:
                return self._update_item_price(data)
            elif operation == OP_UPDATE_ITEM_QUANTITY:
                return self._update_item_quantity(data)
            elif operation == OP_SEARCH_ITEMS:
                return self._search_items(data)
            elif operation == OP_GET_SELLER_ITEMS:
                return self._get_seller_items(data)
            elif operation == OP_PROVIDE_ITEM_FEEDBACK:
                return self._provide_item_feedback(data)
            elif operation == OP_GET_ITEM_FEEDBACK:
                return self._get_item_feedback(data)
            elif operation == OP_CHECK_ITEM_AVAILABILITY:
                return self._check_item_availability(data)
            elif operation == OP_DECREASE_ITEM_QUANTITY:
                return self._decrease_item_quantity(data)
            else:
                return Protocol.create_response(STATUS_ERROR, message=f"Unknown operation: {operation}")
        except Exception as e:
            return Protocol.create_response(STATUS_ERROR, message=str(e))
    
    # ========== Item Operations ==========
    
    def _register_item(self, data):
        """Register a new item for sale"""
        seller_id = data.get('seller_id')
        name = data.get('name')
        category = data.get('category')
        keywords = data.get('keywords', [])
        condition = data.get('condition')
        price = data.get('price')
        quantity = data.get('quantity')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get and increment category counter
            cursor.execute('''
                UPDATE category_counters SET last_id = last_id + 1
                WHERE category = ?
            ''', (category,))
            
            cursor.execute('''
                SELECT last_id FROM category_counters
                WHERE category = ?
            ''', (category,))
            
            sequence = cursor.fetchone()[0]
            item_id = generate_item_id(category, sequence)
            
            # Store keywords as JSON
            keywords_json = json.dumps(keywords)
            
            # Insert item
            cursor.execute('''
                INSERT INTO items (item_id, seller_id, name, category, keywords, 
                                   condition, price, quantity, thumbs_up, thumbs_down)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (item_id, seller_id, name, category, keywords_json, condition, price, quantity))
            
            conn.commit()
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={'item_id': item_id},
                message="Item registered successfully"
            )
        finally:
            conn.close()
    
    def _get_item(self, data):
        """Get item details by item ID"""
        item_id = data.get('item_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT item_id, seller_id, name, category, keywords, condition, 
                       price, quantity, thumbs_up, thumbs_down
                FROM items
                WHERE item_id = ?
            ''', (item_id,))
            
            result = cursor.fetchone()
            
            if result:
                item = {
                    'item_id': result[0],
                    'seller_id': result[1],
                    'name': result[2],
                    'category': result[3],
                    'keywords': json.loads(result[4]) if result[4] else [],
                    'condition': result[5],
                    'price': result[6],
                    'quantity': result[7],
                    'thumbs_up': result[8],
                    'thumbs_down': result[9]
                }
                return Protocol.create_response(STATUS_SUCCESS, data={'item': item})
            else:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
        finally:
            conn.close()
    
    def _update_item_price(self, data):
        """Update item price"""
        item_id = data.get('item_id')
        seller_id = data.get('seller_id')
        new_price = data.get('new_price')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Verify seller owns this item
            cursor.execute('''
                SELECT seller_id FROM items WHERE item_id = ?
            ''', (item_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
            
            if result[0] != seller_id:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="You don't own this item"
                )
            
            # Update price
            cursor.execute('''
                UPDATE items SET price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
            ''', (new_price, item_id))
            
            conn.commit()
            
            return Protocol.create_response(STATUS_SUCCESS, message="Price updated successfully")
        finally:
            conn.close()
    
    def _update_item_quantity(self, data):
        """Update item quantity (remove units)"""
        item_id = data.get('item_id')
        seller_id = data.get('seller_id')
        quantity_to_remove = data.get('quantity_to_remove')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Verify seller owns this item
            cursor.execute('''
                SELECT seller_id, quantity FROM items WHERE item_id = ?
            ''', (item_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
            
            if result[0] != seller_id:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="You don't own this item"
                )
            
            current_quantity = result[1]
            new_quantity = current_quantity - quantity_to_remove
            
            if new_quantity < 0:
                return Protocol.create_response(
                    STATUS_ERROR,
                    message=f"Cannot remove {quantity_to_remove} units. Only {current_quantity} available."
                )
            
            # Update quantity
            cursor.execute('''
                UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
            ''', (new_quantity, item_id))
            
            conn.commit()
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                message=f"Quantity updated. {new_quantity} units remaining."
            )
        finally:
            conn.close()
    
    def _search_items(self, data):
        """
        Search items by category and keywords
        
        Search semantics:
        1. Category must match exactly
        2. Items are scored based on keyword matching:
           - Exact match of keyword with item name: 10 points
           - Partial match of keyword in item name: 5 points
           - Keyword appears in item's keyword list: 3 points
        3. Results sorted by score (highest first)
        4. Only items with quantity > 0 are returned
        """
        category = data.get('category')
        keywords = data.get('keywords', [])
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get all items in category with available quantity
            cursor.execute('''
                SELECT item_id, seller_id, name, category, keywords, condition, 
                       price, quantity, thumbs_up, thumbs_down
                FROM items
                WHERE category = ? AND quantity > 0
            ''', (category,))
            
            results = cursor.fetchall()
            
            # Convert to item dictionaries and calculate scores
            scored_items = []
            for row in results:
                item = {
                    'item_id': row[0],
                    'seller_id': row[1],
                    'name': row[2],
                    'category': row[3],
                    'keywords': json.loads(row[4]) if row[4] else [],
                    'condition': row[5],
                    'price': row[6],
                    'quantity': row[7],
                    'thumbs_up': row[8],
                    'thumbs_down': row[9]
                }
                
                # Calculate relevance score
                score = calculate_search_score(item, category, keywords)
                
                # Only include items with score > 0 if keywords provided
                if not keywords or score > 0:
                    scored_items.append((score, item))
            
            # Sort by score (descending)
            scored_items.sort(key=lambda x: x[0], reverse=True)
            
            # Extract items (remove scores) and limit results
            items = [item for score, item in scored_items[:config.MAX_SEARCH_RESULTS]]
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={'items': items},
                message=f"Found {len(items)} items"
            )
        finally:
            conn.close()
    
    def _get_seller_items(self, data):
        """Get all items for a specific seller"""
        seller_id = data.get('seller_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT item_id, seller_id, name, category, keywords, condition, 
                       price, quantity, thumbs_up, thumbs_down
                FROM items
                WHERE seller_id = ?
                ORDER BY created_at DESC
            ''', (seller_id,))
            
            results = cursor.fetchall()
            
            items = []
            for row in results:
                item = {
                    'item_id': row[0],
                    'seller_id': row[1],
                    'name': row[2],
                    'category': row[3],
                    'keywords': json.loads(row[4]) if row[4] else [],
                    'condition': row[5],
                    'price': row[6],
                    'quantity': row[7],
                    'thumbs_up': row[8],
                    'thumbs_down': row[9]
                }
                items.append(item)
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={'items': items},
                message=f"Found {len(items)} items"
            )
        finally:
            conn.close()
    
    def _provide_item_feedback(self, data):
        """Provide feedback (thumbs up/down) for an item"""
        item_id = data.get('item_id')
        feedback_type = data.get('feedback_type')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if feedback_type == FEEDBACK_THUMBS_UP:
                cursor.execute('''
                    UPDATE items SET thumbs_up = thumbs_up + 1
                    WHERE item_id = ?
                ''', (item_id,))
            else:
                cursor.execute('''
                    UPDATE items SET thumbs_down = thumbs_down + 1
                    WHERE item_id = ?
                ''', (item_id,))
            
            if cursor.rowcount == 0:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS, message="Feedback recorded")
        finally:
            conn.close()
    
    def _get_item_feedback(self, data):
        """Get feedback for an item"""
        item_id = data.get('item_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT thumbs_up, thumbs_down FROM items
                WHERE item_id = ?
            ''', (item_id,))
            
            result = cursor.fetchone()
            
            if result:
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={'thumbs_up': result[0], 'thumbs_down': result[1]}
                )
            else:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
        finally:
            conn.close()
    
    def _check_item_availability(self, data):
        """Check if item has sufficient quantity available"""
        item_id = data.get('item_id')
        requested_quantity = data.get('quantity')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT quantity FROM items WHERE item_id = ?
            ''', (item_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
            
            available_quantity = result[0]
            
            if available_quantity >= requested_quantity:
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={'available': True, 'quantity': available_quantity}
                )
            else:
                return Protocol.create_response(
                    STATUS_INSUFFICIENT_QUANTITY,
                    data={'available': False, 'quantity': available_quantity},
                    message=f"Only {available_quantity} units available"
                )
        finally:
            conn.close()
    
    def _decrease_item_quantity(self, data):
        """Decrease item quantity (for purchases)"""
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT quantity, seller_id FROM items WHERE item_id = ?
            ''', (item_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not found")
            
            available_quantity, seller_id = result
            
            if available_quantity < quantity:
                return Protocol.create_response(
                    STATUS_INSUFFICIENT_QUANTITY,
                    message=f"Only {available_quantity} units available"
                )
            
            # Decrease quantity
            cursor.execute('''
                UPDATE items SET quantity = quantity - ?
                WHERE item_id = ?
            ''', (quantity, item_id))
            
            conn.commit()
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={'seller_id': seller_id},
                message="Quantity decreased"
            )
        finally:
            conn.close()
    
    # ========== Server Management ==========
    
    def handle_client(self, client_socket, client_address):
        """Handle individual client connection"""
        try:
            while True:
                # Receive request
                request = Protocol.receive_message(client_socket)
                
                # Process request
                response = self.handle_request(request)
                
                # Send response
                Protocol.send_message(client_socket, response)
                
        except Exception as e:
            print(f"Error handling client {client_address}: {e}")
        finally:
            client_socket.close()
    
    def start(self):
        """Start the database server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(config.BACKLOG)
        
        self.running = True
        
        print(f"Product Database Server started on {self.host}:{self.port}")
        print(f"Database: {self.db_path}")
        
        try:
            while self.running:
                client_socket, client_address = server_socket.accept()
                
                # Handle each client in a separate thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
        except KeyboardInterrupt:
            print("\nShutting down Product Database Server...")
        finally:
            server_socket.close()
            self.running = False


def main():
    """Main entry point"""
    db_server = ProductDatabase(
        db_path=config.PRODUCT_DB_FILE,
        host=config.PRODUCT_DB_HOST,
        port=config.PRODUCT_DB_PORT
    )
    db_server.start()


if __name__ == '__main__':
    main()
