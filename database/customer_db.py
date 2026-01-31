"""
Customer Database Server
Handles all customer-related data: sellers, buyers, sessions, shopping carts
Runs as a separate process and communicates via TCP sockets
"""

import socket
import threading
import sqlite3
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.protocol import Protocol
from shared.constants import *
from shared.utils import generate_session_id, get_current_timestamp, is_session_expired


class CustomerDatabase:
    """Customer Database Server"""
    
    def __init__(self, db_path, host, port):
        self.db_path = db_path
        self.host = host
        self.port = port
        self.running = False
        
        # Thread-safe database connection handling
        self.conn_lock = threading.Lock()
        
        # Initialize database
        self._init_database()
        
        # Start session cleanup thread
        self.cleanup_thread = threading.Thread(target=self._session_cleanup_worker, daemon=True)
        self.cleanup_thread.start()
    
    def _init_database(self):
        """Initialize database schema if not exists"""
        from database.init_db import init_customer_database
        init_customer_database(self.db_path)
    
    def _get_connection(self):
        """Get a thread-safe database connection"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def _session_cleanup_worker(self):
        """Background thread to cleanup expired sessions"""
        while True:
            time.sleep(config.SESSION_CHECK_INTERVAL)
            try:
                self._cleanup_expired_sessions()
            except Exception as e:
                print(f"Error in session cleanup: {e}")
    
    def _cleanup_expired_sessions(self):
        """Remove expired sessions from database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        current_time = get_current_timestamp()
        timeout = config.SESSION_TIMEOUT
        cutoff_time = current_time - timeout
        
        try:
            # Clean seller sessions
            cursor.execute('''
                DELETE FROM seller_sessions 
                WHERE last_activity < ?
            ''', (cutoff_time,))
            
            # Clean buyer sessions
            cursor.execute('''
                DELETE FROM buyer_sessions 
                WHERE last_activity < ?
            ''', (cutoff_time,))
            
            # Clean associated shopping carts for expired buyer sessions
            cursor.execute('''
                DELETE FROM shopping_carts 
                WHERE session_id NOT IN (SELECT session_id FROM buyer_sessions)
            ''')
            
            conn.commit()
        finally:
            conn.close()
    
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
            if operation == OP_CREATE_SELLER:
                return self._create_seller(data)
            elif operation == OP_CREATE_BUYER:
                return self._create_buyer(data)
            elif operation == OP_LOGIN_SELLER:
                return self._login_seller(data)
            elif operation == OP_LOGIN_BUYER:
                return self._login_buyer(data)
            elif operation == OP_LOGOUT_SELLER:
                return self._logout_seller(data)
            elif operation == OP_LOGOUT_BUYER:
                return self._logout_buyer(data)
            elif operation == OP_VALIDATE_SESSION_SELLER:
                return self._validate_seller_session(data)
            elif operation == OP_VALIDATE_SESSION_BUYER:
                return self._validate_buyer_session(data)
            elif operation == OP_GET_SELLER_INFO:
                return self._get_seller_info(data)
            elif operation == OP_GET_BUYER_INFO:
                return self._get_buyer_info(data)
            elif operation == OP_GET_SELLER_RATING:
                return self._get_seller_rating(data)
            elif operation == OP_UPDATE_SELLER_FEEDBACK:
                return self._update_seller_feedback(data)
            elif operation == OP_UPDATE_SELLER_ITEMS_SOLD:
                return self._update_seller_items_sold(data)
            elif operation == OP_UPDATE_BUYER_ITEMS_PURCHASED:
                return self._update_buyer_items_purchased(data)
            elif operation == OP_GET_BUYER_PURCHASES:
                return self._get_buyer_purchases(data)
            elif operation == OP_ADD_BUYER_PURCHASE:
                return self._add_buyer_purchase(data)
            elif operation == OP_GET_CART:
                return self._get_cart(data)
            elif operation == OP_ADD_TO_CART:
                return self._add_to_cart(data)
            elif operation == OP_REMOVE_FROM_CART:
                return self._remove_from_cart(data)
            elif operation == OP_CLEAR_CART:
                return self._clear_cart(data)
            elif operation == OP_SAVE_CART:
                return self._save_cart(data)
            elif operation == OP_UPDATE_SESSION_ACTIVITY:
                return self._update_session_activity(data)
            elif operation == OP_RESTORE_SESSION_BUYER: #JN added
                return self._restore_session_buyer(data)
            elif operation == OP_RESTORE_SESSION_SELLER: #JN added
                return self._restore_session_seller(data)
            else:
                return Protocol.create_response(STATUS_ERROR, message=f"Unknown operation: {operation}")
        except Exception as e:
            return Protocol.create_response(STATUS_ERROR, message=str(e))
    
    # ========== Seller Operations ==========
    
    def _create_seller(self, data):
        """Create a new seller account"""
        username = data.get('username')
        password = data.get('password')
        seller_name = data.get('seller_name')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO sellers (username, password, seller_name)
                VALUES (?, ?, ?)
            ''', (username, password, seller_name))
            
            seller_id = cursor.lastrowid
            conn.commit()
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={'seller_id': seller_id},
                message="Seller account created successfully"
            )
        except sqlite3.IntegrityError:
            return Protocol.create_response(
                STATUS_DUPLICATE,
                message="Username already exists"
            )
        finally:
            conn.close()
    
    def _login_seller(self, data):
        """Login seller and create session"""
        username = data.get('username')
        password = data.get('password')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT seller_id, seller_name FROM sellers
                WHERE username = ? AND password = ?
            ''', (username, password))
            
            result = cursor.fetchone()
            
            if result:
                seller_id, seller_name = result
                session_id = generate_session_id()
                current_time = get_current_timestamp()
                
                # Create session
                cursor.execute('''
                    INSERT INTO seller_sessions (session_id, seller_id, last_activity, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, seller_id, current_time, current_time))
                
                conn.commit()
                
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={
                        'session_id': session_id,
                        'seller_id': seller_id,
                        'seller_name': seller_name
                    },
                    message="Login successful"
                )
            else:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="Invalid username or password"
                )
        finally:
            conn.close()
    
    def _logout_seller(self, data):
        """Logout seller and remove session"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (session_id,))
            conn.commit()
            
            return Protocol.create_response(STATUS_SUCCESS, message="Logout successful")
        finally:
            conn.close()
    
    def _validate_seller_session(self, data):
        """Validate seller session and update activity"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT seller_id, last_activity FROM seller_sessions
                WHERE session_id = ?
            ''', (session_id,))
            
            result = cursor.fetchone()
            
            if result:
                seller_id, last_activity = result
                
                # Check if session expired
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (session_id,))
                    conn.commit()
                    return Protocol.create_response(
                        STATUS_UNAUTHORIZED,
                        message="Session expired. Please login again."
                    )
                
                # Update last activity
                current_time = get_current_timestamp()
                cursor.execute('''
                    UPDATE seller_sessions SET last_activity = ?
                    WHERE session_id = ?
                ''', (current_time, session_id))
                conn.commit()
                
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={'seller_id': seller_id}
                )
            else:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="Invalid session. Please login."
                )
        finally:
            conn.close()

    def _restore_buyer_session(self, data): #JN added
        """Restore buyer session if still valid"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT bs.buyer_id, bs.last_activity, b.buyer_name
                FROM buyer_sessions bs
                JOIN buyers b ON bs.buyer_id = b.buyer_id
                WHERE bs.session_id = ?
            ''', (session_id,))
            
            result = cursor.fetchone()
            
            if result:
                buyer_id, last_activity, buyer_name = result
                
                # Check if session expired
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (session_id,))
                    cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (session_id,))
                    conn.commit()
                    return Protocol.create_response(
                        STATUS_UNAUTHORIZED,
                        message="Session expired. Please login again."
                    )
                
                # Update last activity (refresh session)
                current_time = get_current_timestamp()
                cursor.execute('''
                    UPDATE buyer_sessions SET last_activity = ?
                    WHERE session_id = ?
                ''', (current_time, session_id))
                conn.commit()
                
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={
                        'session_id': session_id,
                        'buyer_id': buyer_id,
                        'buyer_name': buyer_name
                    },
                    message="Session restored successfully"
                )
            else:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="Invalid session. Please login."
                )
        finally:
            conn.close()

    def _restore_seller_session(self, data): #JN added
        """Restore seller session if still valid"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT ss.seller_id, ss.last_activity, s.seller_name
                FROM seller_sessions ss
                JOIN sellers s ON ss.seller_id = s.seller_id
                WHERE ss.session_id = ?
            ''', (session_id,))
            
            result = cursor.fetchone()
            
            if result:
                seller_id, last_activity, seller_name = result
                
                # Check if session expired
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    cursor.execute('DELETE FROM seller_sessions WHERE session_id = ?', (session_id,))
                    conn.commit()
                    return Protocol.create_response(
                        STATUS_UNAUTHORIZED,
                        message="Session expired. Please login again."
                    )
                
                # Update last activity (refresh session)
                current_time = get_current_timestamp()
                cursor.execute('''
                    UPDATE seller_sessions SET last_activity = ?
                    WHERE session_id = ?
                ''', (current_time, session_id))
                conn.commit()
                
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={
                        'session_id': session_id,
                        'seller_id': seller_id,
                        'seller_name': seller_name
                    },
                    message="Session restored successfully"
                )
            else:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="Invalid session. Please login."
                )
        finally:
            conn.close()
    
    def _get_seller_info(self, data):
        """Get seller information"""
        seller_id = data.get('seller_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT seller_name, thumbs_up, thumbs_down, items_sold
                FROM sellers WHERE seller_id = ?
            ''', (seller_id,))
            
            result = cursor.fetchone()
            
            if result:
                seller_name, thumbs_up, thumbs_down, items_sold = result
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={
                        'seller_name': seller_name,
                        'thumbs_up': thumbs_up,
                        'thumbs_down': thumbs_down,
                        'items_sold': items_sold
                    }
                )
            else:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Seller not found")
        finally:
            conn.close()
    
    def _get_seller_rating(self, data):
        """Get seller rating/feedback"""
        seller_id = data.get('seller_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT thumbs_up, thumbs_down FROM sellers
                WHERE seller_id = ?
            ''', (seller_id,))
            
            result = cursor.fetchone()
            
            if result:
                thumbs_up, thumbs_down = result
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={'thumbs_up': thumbs_up, 'thumbs_down': thumbs_down}
                )
            else:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Seller not found")
        finally:
            conn.close()
    
    def _update_seller_feedback(self, data):
        """Update seller feedback"""
        seller_id = data.get('seller_id')
        feedback_type = data.get('feedback_type')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if feedback_type == FEEDBACK_THUMBS_UP:
                cursor.execute('''
                    UPDATE sellers SET thumbs_up = thumbs_up + 1
                    WHERE seller_id = ?
                ''', (seller_id,))
            else:
                cursor.execute('''
                    UPDATE sellers SET thumbs_down = thumbs_down + 1
                    WHERE seller_id = ?
                ''', (seller_id,))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS, message="Feedback updated")
        finally:
            conn.close()
    
    def _update_seller_items_sold(self, data):
        """Update seller items sold count"""
        seller_id = data.get('seller_id')
        quantity = data.get('quantity', 1)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE sellers SET items_sold = items_sold + ?
                WHERE seller_id = ?
            ''', (quantity, seller_id))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS)
        finally:
            conn.close()
    
    # ========== Buyer Operations ==========
    
    def _create_buyer(self, data):
        """Create a new buyer account"""
        username = data.get('username')
        password = data.get('password')
        buyer_name = data.get('buyer_name')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO buyers (username, password, buyer_name)
                VALUES (?, ?, ?)
            ''', (username, password, buyer_name))
            
            buyer_id = cursor.lastrowid
            conn.commit()
            
            return Protocol.create_response(
                STATUS_SUCCESS,
                data={'buyer_id': buyer_id},
                message="Buyer account created successfully"
            )
        except sqlite3.IntegrityError:
            return Protocol.create_response(
                STATUS_DUPLICATE,
                message="Username already exists"
            )
        finally:
            conn.close()
    
    def _login_buyer(self, data):
        """Login buyer and create session"""
        username = data.get('username')
        password = data.get('password')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT buyer_id, buyer_name FROM buyers
                WHERE username = ? AND password = ?
            ''', (username, password))
            
            result = cursor.fetchone()
            
            if result:
                buyer_id, buyer_name = result
                session_id = generate_session_id()
                current_time = get_current_timestamp()
                
                # Create session
                cursor.execute('''
                    INSERT INTO buyer_sessions (session_id, buyer_id, last_activity, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, buyer_id, current_time, current_time))
                
                # Load saved cart into this session's active cart
                cursor.execute('''
                    SELECT item_id, quantity FROM saved_carts
                    WHERE buyer_id = ?
                ''', (buyer_id,))
                
                saved_items = cursor.fetchall()
                for item_id, quantity in saved_items:
                    cursor.execute('''
                        INSERT OR REPLACE INTO shopping_carts (session_id, buyer_id, item_id, quantity)
                        VALUES (?, ?, ?, ?)
                    ''', (session_id, buyer_id, item_id, quantity))
                
                conn.commit()
                
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={
                        'session_id': session_id,
                        'buyer_id': buyer_id,
                        'buyer_name': buyer_name
                    },
                    message="Login successful"
                )
            else:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="Invalid username or password"
                )
        finally:
            conn.close()
    
    def _logout_buyer(self, data):
        """Logout buyer and clear session cart (if not saved)"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Delete session-specific cart items (not saved)
            cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (session_id,))
            
            # Delete session
            cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (session_id,))
            
            conn.commit()
            
            return Protocol.create_response(STATUS_SUCCESS, message="Logout successful")
        finally:
            conn.close()
    
    def _validate_buyer_session(self, data):
        """Validate buyer session and update activity"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT buyer_id, last_activity FROM buyer_sessions
                WHERE session_id = ?
            ''', (session_id,))
            
            result = cursor.fetchone()
            
            if result:
                buyer_id, last_activity = result
                
                # Check if session expired
                if is_session_expired(last_activity, config.SESSION_TIMEOUT):
                    # Clean up expired session
                    cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (session_id,))
                    cursor.execute('DELETE FROM buyer_sessions WHERE session_id = ?', (session_id,))
                    conn.commit()
                    return Protocol.create_response(
                        STATUS_UNAUTHORIZED,
                        message="Session expired. Please login again."
                    )
                
                # Update last activity
                current_time = get_current_timestamp()
                cursor.execute('''
                    UPDATE buyer_sessions SET last_activity = ?
                    WHERE session_id = ?
                ''', (current_time, session_id))
                conn.commit()
                
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={'buyer_id': buyer_id}
                )
            else:
                return Protocol.create_response(
                    STATUS_UNAUTHORIZED,
                    message="Invalid session. Please login."
                )
        finally:
            conn.close()
    
    def _get_buyer_info(self, data):
        """Get buyer information"""
        buyer_id = data.get('buyer_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT buyer_name, items_purchased FROM buyers
                WHERE buyer_id = ?
            ''', (buyer_id,))
            
            result = cursor.fetchone()
            
            if result:
                buyer_name, items_purchased = result
                return Protocol.create_response(
                    STATUS_SUCCESS,
                    data={
                        'buyer_name': buyer_name,
                        'items_purchased': items_purchased
                    }
                )
            else:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Buyer not found")
        finally:
            conn.close()
    
    def _update_buyer_items_purchased(self, data):
        """Update buyer items purchased count"""
        buyer_id = data.get('buyer_id')
        quantity = data.get('quantity', 1)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE buyers SET items_purchased = items_purchased + ?
                WHERE buyer_id = ?
            ''', (quantity, buyer_id))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS)
        finally:
            conn.close()
    
    def _get_buyer_purchases(self, data):
        """Get buyer purchase history"""
        buyer_id = data.get('buyer_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT item_id, quantity, purchase_date FROM purchase_history
                WHERE buyer_id = ?
                ORDER BY purchase_date DESC
            ''', (buyer_id,))
            
            purchases = []
            for row in cursor.fetchall():
                purchases.append({
                    'item_id': row[0],
                    'quantity': row[1],
                    'purchase_date': row[2]
                })
            
            return Protocol.create_response(STATUS_SUCCESS, data={'purchases': purchases})
        finally:
            conn.close()
    
    def _add_buyer_purchase(self, data):
        """Add a purchase to buyer's history"""
        buyer_id = data.get('buyer_id')
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO purchase_history (buyer_id, item_id, quantity)
                VALUES (?, ?, ?)
            ''', (buyer_id, item_id, quantity))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS)
        finally:
            conn.close()
    
    # ========== Shopping Cart Operations ==========
    
    def _get_cart(self, data):
        """Get shopping cart for session"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT item_id, quantity FROM shopping_carts
                WHERE session_id = ?
            ''', (session_id,))
            
            cart_items = []
            for row in cursor.fetchall():
                cart_items.append({
                    'item_id': row[0],
                    'quantity': row[1]
                })
            
            return Protocol.create_response(STATUS_SUCCESS, data={'cart': cart_items})
        finally:
            conn.close()
    
    def _add_to_cart(self, data):
        """Add item to shopping cart"""
        session_id = data.get('session_id')
        buyer_id = data.get('buyer_id')
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if item already in cart
            cursor.execute('''
                SELECT quantity FROM shopping_carts
                WHERE session_id = ? AND item_id = ?
            ''', (session_id, item_id))
            
            result = cursor.fetchone()
            
            if result:
                # Update quantity
                new_quantity = result[0] + quantity
                cursor.execute('''
                    UPDATE shopping_carts SET quantity = ?
                    WHERE session_id = ? AND item_id = ?
                ''', (new_quantity, session_id, item_id))
            else:
                # Insert new cart item
                cursor.execute('''
                    INSERT INTO shopping_carts (session_id, buyer_id, item_id, quantity)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, buyer_id, item_id, quantity))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS, message="Item added to cart")
        finally:
            conn.close()
    
    def _remove_from_cart(self, data):
        """Remove item from shopping cart"""
        session_id = data.get('session_id')
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT quantity FROM shopping_carts
                WHERE session_id = ? AND item_id = ?
            ''', (session_id, item_id))
            
            result = cursor.fetchone()
            
            if result:
                current_quantity = result[0]
                new_quantity = current_quantity - quantity
                
                if new_quantity <= 0:
                    # Remove item completely
                    cursor.execute('''
                        DELETE FROM shopping_carts
                        WHERE session_id = ? AND item_id = ?
                    ''', (session_id, item_id))
                else:
                    # Update quantity
                    cursor.execute('''
                        UPDATE shopping_carts SET quantity = ?
                        WHERE session_id = ? AND item_id = ?
                    ''', (new_quantity, session_id, item_id))
                
                conn.commit()
                return Protocol.create_response(STATUS_SUCCESS, message="Item removed from cart")
            else:
                return Protocol.create_response(STATUS_NOT_FOUND, message="Item not in cart")
        finally:
            conn.close()
    
    def _clear_cart(self, data):
        """Clear all items from shopping cart"""
        session_id = data.get('session_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (session_id,))
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS, message="Cart cleared")
        finally:
            conn.close()
    
    def _save_cart(self, data):
        """Save current cart to persist across sessions"""
        session_id = data.get('session_id')
        buyer_id = data.get('buyer_id')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current cart items
            cursor.execute('''
                SELECT item_id, quantity FROM shopping_carts
                WHERE session_id = ?
            ''', (session_id,))
            
            cart_items = cursor.fetchall()
            
            # Clear existing saved cart
            cursor.execute('DELETE FROM saved_carts WHERE buyer_id = ?', (buyer_id,))
            
            # Save current cart items
            for item_id, quantity in cart_items:
                cursor.execute('''
                    INSERT INTO saved_carts (buyer_id, item_id, quantity)
                    VALUES (?, ?, ?)
                ''', (buyer_id, item_id, quantity))
            
            # Update all other sessions for this buyer to reflect saved cart
            cursor.execute('''
                SELECT session_id FROM buyer_sessions
                WHERE buyer_id = ? AND session_id != ?
            ''', (buyer_id, session_id))
            
            other_sessions = [row[0] for row in cursor.fetchall()]
            
            for other_session_id in other_sessions:
                # Clear other session's cart
                cursor.execute('DELETE FROM shopping_carts WHERE session_id = ?', (other_session_id,))
                
                # Add saved items to other sessions
                for item_id, quantity in cart_items:
                    cursor.execute('''
                        INSERT INTO shopping_carts (session_id, buyer_id, item_id, quantity)
                        VALUES (?, ?, ?, ?)
                    ''', (other_session_id, buyer_id, item_id, quantity))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS, message="Cart saved successfully")
        finally:
            conn.close()
    
    def _update_session_activity(self, data):
        """Update session last activity timestamp"""
        session_id = data.get('session_id')
        user_type = data.get('user_type', 'buyer')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            current_time = get_current_timestamp()
            
            if user_type == 'seller':
                cursor.execute('''
                    UPDATE seller_sessions SET last_activity = ?
                    WHERE session_id = ?
                ''', (current_time, session_id))
            else:
                cursor.execute('''
                    UPDATE buyer_sessions SET last_activity = ?
                    WHERE session_id = ?
                ''', (current_time, session_id))
            
            conn.commit()
            return Protocol.create_response(STATUS_SUCCESS)
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
        
        print(f"Customer Database Server started on {self.host}:{self.port}")
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
            print("\nShutting down Customer Database Server...")
        finally:
            server_socket.close()
            self.running = False


def main():
    """Main entry point"""
    db_server = CustomerDatabase(
        db_path=config.CUSTOMER_DB_FILE,
        host=config.CUSTOMER_DB_HOST,
        port=config.CUSTOMER_DB_PORT
    )
    db_server.start()


if __name__ == '__main__':
    main()
