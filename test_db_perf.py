"""
Database Performance Test and Diagnostics
Tests concurrent connections with multiple sellers and buyers
"""

import time
import threading
import json
from collections import defaultdict
import sys


from db_client.db_client import DatabaseClient

class PerformanceTester:
    def __init__(self, customer_host, customer_port, product_host, product_port):
        self.customer_host = customer_host
        self.customer_port = customer_port
        self.product_host = product_host
        self.product_port = product_port
        
        self.results = defaultdict(list)
        self.errors = []
        self.lock = threading.Lock()
    
    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")
    
    def test_single_connection(self):
        """Test basic connectivity"""
        self.log("Testing single connection...")
        
        try:
            client = DatabaseClient(self.customer_host, self.customer_port)
            
            start = time.time()
            response = client.query("PING", {})
            elapsed = time.time() - start
            
            self.log(f"✓ Single connection test: {elapsed:.3f}s - Response: {response}")
            client.close()
            return True
        
        except Exception as e:
            self.log(f"✗ Single connection test failed: {e}")
            return False
    
    def test_seller_registration(self, seller_id):
        """Test seller registration"""
        username = f"seller_{seller_id}"
        password = f"pass_{seller_id}"
        
        try:
            client = DatabaseClient(self.customer_host, self.customer_port)
            
            start = time.time()
            response = client.query("CREATE_SELLER", {
                "username": username,
                "password": password
            })
            elapsed = time.time() - start
            
            with self.lock:
                self.results[f"seller_{seller_id}_create"] = elapsed
            
            if response.get('status') == 'success':
                self.log(f"✓ Seller {seller_id} created in {elapsed:.3f}s")
            else:
                self.log(f"✗ Seller {seller_id} failed: {response.get('error_message', 'Unknown error')}")
                with self.lock:
                    self.errors.append(f"Seller {seller_id}: {response}")
            
            client.close()
            return response.get('status') == 'success'
        
        except Exception as e:
            with self.lock:
                self.errors.append(f"Seller {seller_id} exception: {e}")
            self.log(f"✗ Seller {seller_id} exception: {e}")
            return False
    
    def test_buyer_registration(self, buyer_id):
        """Test buyer registration"""
        username = f"buyer_{buyer_id}"
        password = f"pass_{buyer_id}"
        
        try:
            client = DatabaseClient(self.customer_host, self.customer_port)
            
            start = time.time()
            response = client.query("CREATE_BUYER", {
                "username": username,
                "password": password
            })
            elapsed = time.time() - start
            
            with self.lock:
                self.results[f"buyer_{buyer_id}_create"] = elapsed
            
            if response.get('status') == 'success':
                self.log(f"✓ Buyer {buyer_id} created in {elapsed:.3f}s")
            else:
                self.log(f"✗ Buyer {buyer_id} failed: {response.get('error_message', 'Unknown error')}")
                with self.lock:
                    self.errors.append(f"Buyer {buyer_id}: {response}")
            
            client.close()
            return response.get('status') == 'success'
        
        except Exception as e:
            with self.lock:
                self.errors.append(f"Buyer {buyer_id} exception: {e}")
            self.log(f"✗ Buyer {buyer_id} exception: {e}")
            return False
    
    def test_concurrent_operations(self, num_sellers=5, num_buyers=5):
        """Test concurrent seller and buyer creation"""
        self.log(f"\n{'='*60}")
        self.log(f"Testing {num_sellers} sellers + {num_buyers} buyers concurrently")
        self.log(f"{'='*60}\n")
        
        threads = []
        start_time = time.time()
        
        # Create seller threads
        for i in range(num_sellers):
            t = threading.Thread(target=self.test_seller_registration, args=(i,))
            threads.append(t)
        
        # Create buyer threads
        for i in range(num_buyers):
            t = threading.Thread(target=self.test_buyer_registration, args=(i,))
            threads.append(t)
        
        # Start all threads
        self.log(f"Starting {len(threads)} threads...")
        for t in threads:
            t.start()
        
        # Wait for completion with timeout
        timeout = 60  # 60 second timeout
        for i, t in enumerate(threads):
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                self.log(f"⚠ Timeout waiting for threads!")
                break
            
            t.join(timeout=remaining)
            if t.is_alive():
                self.log(f"⚠ Thread {i} still running after timeout")
        
        total_time = time.time() - start_time
        
        self.log(f"\n{'='*60}")
        self.log(f"Test completed in {total_time:.2f}s")
        self.log(f"{'='*60}\n")
        
        return total_time
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("PERFORMANCE SUMMARY")
        print("="*60)
        
        if self.results:
            times = list(self.results.values())
            print(f"\nTotal operations: {len(times)}")
            print(f"Average time: {sum(times)/len(times):.3f}s")
            print(f"Min time: {min(times):.3f}s")
            print(f"Max time: {max(times):.3f}s")
            
            print("\nIndividual timings:")
            for key, value in sorted(self.results.items()):
                print(f"  {key}: {value:.3f}s")
        
        if self.errors:
            print(f"\n⚠ Errors encountered: {len(self.errors)}")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("\n✓ No errors")
        
        print("="*60)
    
    def test_connection_pool_stats(self):
        """Get connection pool statistics"""
        self.log("\nConnection Pool Statistics:")
        
        try:
            client = DatabaseClient(self.customer_host, self.customer_port)
            stats = client.get_stats()
            
            for key, value in stats.items():
                print(f"  {key}: {value}")
            
            client.close()
        except Exception as e:
            self.log(f"Failed to get stats: {e}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python test_db_performance.py <customer_host> <customer_port> [product_host] [product_port]")
        print("Example: python test_db_performance.py localhost 5003 localhost 5004")
        sys.exit(1)
    
    customer_host = sys.argv[1]
    customer_port = int(sys.argv[2])
    
    product_host = sys.argv[3] if len(sys.argv) > 3 else customer_host
    product_port = int(sys.argv[4]) if len(sys.argv) > 4 else 5004
    
    tester = PerformanceTester(customer_host, customer_port, product_host, product_port)
    
    # Run tests
    print("\n" + "="*60)
    print("DATABASE PERFORMANCE TEST")
    print("="*60)
    print(f"Customer DB: {customer_host}:{customer_port}")
    print(f"Product DB: {product_host}:{product_port}")
    print("="*60 + "\n")
    
    # Test 1: Single connection
    if not tester.test_single_connection():
        print("\n⚠ Basic connectivity failed. Exiting.")
        return
    
    time.sleep(1)
    
    # Test 2: Concurrent operations
    tester.test_concurrent_operations(num_sellers=5, num_buyers=5)
    
    # Test 3: Connection pool stats
    tester.test_connection_pool_stats()
    
    # Summary
    tester.print_summary()


if __name__ == "__main__":
    main()