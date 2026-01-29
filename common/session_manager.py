"""
Session Manager with 5-minute timeout
Handles buyer and seller sessions with automatic cleanup
"""

import threading
import time
import uuid
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionManager:
    """
    Thread-safe session manager with automatic timeout
    Sessions expire after 5 minutes of inactivity
    """
    
    def __init__(self, timeout=300, cleanup_interval=60):
        """
        Initialize session manager
        
        Args:
            timeout: Session timeout in seconds (default: 300 = 5 minutes)
            cleanup_interval: How often to run cleanup thread (seconds)
        """
        self.timeout = timeout
        self.cleanup_interval = cleanup_interval
        
        self.sessions = {}  # session_id -> session_data
        self.user_sessions = {}  # (user_type, user_id) -> set of session_ids
        
        self.lock = threading.RLock()
        
        # Start cleanup thread
        self.running = True
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="SessionCleanup"
        )
        self.cleanup_thread.start()
        
        logger.info(f"SessionManager initialized (timeout={timeout}s)")
    
    def create_session(self, user_id, user_type, initial_data=None):
        """
        Create a new session for a user
        
        Args:
            user_id: Unique user identifier (seller_id or buyer_id)
            user_type: 'buyer' or 'seller'
            initial_data: Optional dictionary of initial session data
            
        Returns:
            session_id (string)
        """
        session_id = str(uuid.uuid4())
        current_time = time.time()
        
        session_data = {
            'session_id': session_id,
            'user_id': user_id,
            'user_type': user_type,
            'created_at': current_time,
            'last_activity': current_time,
            'data': initial_data or {}
        }
        
        # Add shopping cart for buyers
        if user_type == 'buyer':
            session_data['data']['cart'] = []
        
        with self.lock:
            self.sessions[session_id] = session_data
            
            # Track all sessions for this user
            user_key = (user_type, user_id)
            if user_key not in self.user_sessions:
                self.user_sessions[user_key] = set()
            self.user_sessions[user_key].add(session_id)
        
        logger.info(f"Created session {session_id} for {user_type} {user_id}")
        return session_id
    
    def validate_session(self, session_id):
        """
        Check if session exists and is not expired
        Updates last_activity if valid
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if valid, False if invalid or expired
        """
        with self.lock:
            if session_id not in self.sessions:
                return False
            
            session = self.sessions[session_id]
            current_time = time.time()
            
            # Check if expired
            if current_time - session['last_activity'] > self.timeout:
                logger.info(f"Session {session_id} expired")
                self._delete_session_unlocked(session_id)
                return False
            
            # Update activity timestamp
            session['last_activity'] = current_time
            return True
    
    def get_session(self, session_id):
        """
        Get session data
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session data, or None if invalid
        """
        with self.lock:
            if not self.validate_session(session_id):
                return None
            
            # Return a deep copy to prevent external modifications
            return json.loads(json.dumps(self.sessions[session_id]))
    
    def update_session(self, session_id, updates):
        """
        Update session data
        
        Args:
            session_id: Session identifier
            updates: Dictionary of updates to merge into session['data']
            
        Returns:
            True if successful, False if session invalid
        """
        with self.lock:
            if not self.validate_session(session_id):
                return False
            
            session = self.sessions[session_id]
            session['data'].update(updates)
            session['last_activity'] = time.time()
            
            return True
    
    def get_session_data(self, session_id, key, default=None):
        """
        Get a specific value from session data
        
        Args:
            session_id: Session identifier
            key: Key to retrieve from session['data']
            default: Default value if key doesn't exist
            
        Returns:
            Value or default
        """
        session = self.get_session(session_id)
        if session:
            return session['data'].get(key, default)
        return default
    
    def set_session_data(self, session_id, key, value):
        """
        Set a specific value in session data
        
        Args:
            session_id: Session identifier
            key: Key to set in session['data']
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_session(session_id, {key: value})
    
    def delete_session(self, session_id):
        """
        Delete a session (logout)
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if deleted, False if doesn't exist
        """
        with self.lock:
            return self._delete_session_unlocked(session_id)
    
    def _delete_session_unlocked(self, session_id):
        """Internal method to delete session (must be called with lock held)"""
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        user_key = (session['user_type'], session['user_id'])
        
        # Remove from sessions
        del self.sessions[session_id]
        
        # Remove from user_sessions tracking
        if user_key in self.user_sessions:
            self.user_sessions[user_key].discard(session_id)
            if not self.user_sessions[user_key]:
                del self.user_sessions[user_key]
        
        logger.info(f"Deleted session {session_id}")
        return True
    
    def get_user_sessions(self, user_id, user_type):
        """
        Get all active sessions for a user
        
        Args:
            user_id: User identifier
            user_type: 'buyer' or 'seller'
            
        Returns:
            List of session_ids
        """
        user_key = (user_type, user_id)
        
        with self.lock:
            if user_key not in self.user_sessions:
                return []
            
            # Validate all sessions and remove expired ones
            valid_sessions = []
            for session_id in list(self.user_sessions[user_key]):
                if self.validate_session(session_id):
                    valid_sessions.append(session_id)
            
            return valid_sessions
    
    def delete_all_user_sessions(self, user_id, user_type):
        """
        Delete all sessions for a user
        
        Args:
            user_id: User identifier
            user_type: 'buyer' or 'seller'
            
        Returns:
            Number of sessions deleted
        """
        sessions = self.get_user_sessions(user_id, user_type)
        
        with self.lock:
            count = 0
            for session_id in sessions:
                if self._delete_session_unlocked(session_id):
                    count += 1
        
        logger.info(f"Deleted {count} sessions for {user_type} {user_id}")
        return count
    
    def _cleanup_loop(self):
        """Background thread to periodically clean up expired sessions"""
        logger.info("Session cleanup thread started")
        
        while self.running:
            time.sleep(self.cleanup_interval)
            self._cleanup_expired_sessions()
    
    def _cleanup_expired_sessions(self):
        """Remove all expired sessions"""
        current_time = time.time()
        expired = []
        
        with self.lock:
            for session_id, session in list(self.sessions.items()):
                if current_time - session['last_activity'] > self.timeout:
                    expired.append(session_id)
            
            for session_id in expired:
                self._delete_session_unlocked(session_id)
        
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
    
    def get_statistics(self):
        """
        Get session statistics
        
        Returns:
            Dictionary with statistics
        """
        with self.lock:
            total_sessions = len(self.sessions)
            buyer_sessions = sum(1 for s in self.sessions.values() 
                               if s['user_type'] == 'buyer')
            seller_sessions = total_sessions - buyer_sessions
            unique_users = len(self.user_sessions)
            
            return {
                'total_sessions': total_sessions,
                'buyer_sessions': buyer_sessions,
                'seller_sessions': seller_sessions,
                'unique_users': unique_users,
                'timeout': self.timeout
            }
    
    def shutdown(self):
        """Gracefully shutdown the session manager"""
        logger.info("Shutting down SessionManager")
        self.running = False
        
        if self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=2)


# Shopping Cart Manager (for buyers)
class ShoppingCart:
    """
    Helper class for managing shopping cart operations
    Works with SessionManager
    """
    
    def __init__(self, session_manager):
        self.session_manager = session_manager
    
    def add_item(self, session_id, item_id, quantity):
        """
        Add item to shopping cart
        
        Args:
            session_id: Buyer session ID
            item_id: Tuple (category, id)
            quantity: Number of units to add
            
        Returns:
            True if successful, False otherwise
        """
        cart = self.session_manager.get_session_data(session_id, 'cart', [])
        
        # Check if item already in cart
        for item in cart:
            if item['item_id'] == item_id:
                item['quantity'] += quantity
                return self.session_manager.set_session_data(session_id, 'cart', cart)
        
        # Add new item
        cart.append({
            'item_id': item_id,
            'quantity': quantity,
            'added_at': time.time()
        })
        
        return self.session_manager.set_session_data(session_id, 'cart', cart)
    
    def remove_item(self, session_id, item_id, quantity=None):
        """
        Remove item from shopping cart
        
        Args:
            session_id: Buyer session ID
            item_id: Tuple (category, id)
            quantity: Number of units to remove (None = remove all)
            
        Returns:
            True if successful, False otherwise
        """
        cart = self.session_manager.get_session_data(session_id, 'cart', [])
        
        updated_cart = []
        for item in cart:
            if item['item_id'] == item_id:
                if quantity is None:
                    # Remove entire item
                    continue
                else:
                    # Reduce quantity
                    item['quantity'] -= quantity
                    if item['quantity'] > 0:
                        updated_cart.append(item)
            else:
                updated_cart.append(item)
        
        return self.session_manager.set_session_data(session_id, 'cart', updated_cart)
    
    def get_cart(self, session_id):
        """Get shopping cart contents"""
        return self.session_manager.get_session_data(session_id, 'cart', [])
    
    def clear_cart(self, session_id):
        """Clear shopping cart"""
        return self.session_manager.set_session_data(session_id, 'cart', [])
    
    def get_cart_total(self, session_id, product_db_client):
        """
        Calculate total price of items in cart
        
        Args:
            session_id: Buyer session ID
            product_db_client: Client to query product prices
            
        Returns:
            Total price (float)
        """
        cart = self.get_cart(session_id)
        total = 0.0
        
        for item in cart:
            # Query product database for current price
            item_info = product_db_client.get_item(item['item_id'])
            if item_info and item_info.get('status') == 'success':
                price = item_info['data']['price']
                total += price * item['quantity']
        
        return total


# Example usage and testing
if __name__ == "__main__":
    print("Testing SessionManager...")
    
    # Create session manager with shorter timeout for testing
    manager = SessionManager(timeout=10, cleanup_interval=5)
    
    # Create some sessions
    buyer1_session = manager.create_session(1, 'buyer')
    seller1_session = manager.create_session(1, 'seller')
    buyer2_session = manager.create_session(2, 'buyer')
    
    print(f"\nCreated sessions:")
    print(f"  Buyer 1: {buyer1_session}")
    print(f"  Seller 1: {seller1_session}")
    print(f"  Buyer 2: {buyer2_session}")
    
    # Update session data
    manager.update_session(buyer1_session, {'last_search': 'laptops'})
    
    # Shopping cart operations
    cart_manager = ShoppingCart(manager)
    cart_manager.add_item(buyer1_session, (1, 100), 2)
    cart_manager.add_item(buyer1_session, (2, 200), 1)
    
    print(f"\nBuyer 1 cart: {cart_manager.get_cart(buyer1_session)}")
    
    # Get statistics
    stats = manager.get_statistics()
    print(f"\nSession statistics: {stats}")
    
    # Test timeout
    print(f"\nWaiting 11 seconds for session timeout...")
    time.sleep(11)
    
    # Try to validate expired session
    if manager.validate_session(buyer1_session):
        print("Session still valid")
    else:
        print("Session expired (as expected)")
    
    # Shutdown
    manager.shutdown()
    print("\nSessionManager shutdown complete")