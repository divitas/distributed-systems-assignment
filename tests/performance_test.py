"""
Performance Testing Script
Tests the system with varying numbers of concurrent clients
Measures response time and throughput
"""

import socket
import threading
import time
import random
import statistics
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.protocol import Protocol
from shared.constants import *


class PerformanceTester:
    """Performance testing for the distributed marketplace"""
    
    def __init__(self):
        self.results = {
            'response_times': [],
            'operations_completed': 0,
            'errors': 0
        }
        self.lock = threading.Lock()
    
    def record_response_time(self, response_time):
        """Record a response time"""
        with self.lock:
            self.results['response_times'].append(response_time)
            self.results['operations_completed'] += 1
    
    def record_error(self):
        """Record an error"""
        with self.lock:
            self.results['errors'] += 1
    
    def get_statistics(self):
        """Calculate statistics from results"""
        with self.lock:
            if not self.results['response_times']:
                return None
            
            return {
                'avg_response_time': statistics.mean(self.results['response_times']),
                'median_response_time': statistics.median(self.results['response_times']),
                'min_response_time': min(self.results['response_times']),
                'max_response_time': max(self.results['response_times']),
                'std_dev': statistics.stdev(self.results['response_times']) if len(self.results['response_times']) > 1 else 0,
                'operations_completed': self.results['operations_completed'],
                'errors': self.results['errors']
            }
    
    def reset(self):
        """Reset statistics"""
        with self.lock:
            self.results = {
                'response_times': [],
                'operations_completed': 0,
                'errors': 0
            }


class TestClient:
    """Test client that performs operations"""
    
    def __init__(self, client_type, client_id, operations_count=10):
        self.client_type = client_type  # 'buyer' or 'seller'
        self.client_id = client_id
        self.operations_count = operations_count
        self.session_id = None
        self.user_id = None
        self.username = f"test_{client_type}_{client_id}_{int(time.time())}"
        self.password = "testpass123"
    
    def connect_to_server(self):
        """Connect to appropriate frontend server"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        
        if self.client_type == 'seller':
            sock.connect((config.SELLER_FRONTEND_HOST, config.SELLER_FRONTEND_PORT))
        else:
            sock.connect((config.BUYER_FRONTEND_HOST, config.BUYER_FRONTEND_PORT))
        
        return sock
    
    def make_request(self, sock, operation, data=None):
        """Make a request and measure response time"""
        start_time = time.time()
        
        try:
            request = Protocol.create_request(operation, data, self.session_id)
            Protocol.send_message(sock, request)
            response = Protocol.receive_message(sock)
            
            end_time = time.time()
            response_time = end_time - start_time
            
            return response, response_time
        except Exception as e:
            print(f"Error in request: {e}")
            return None, None
    
    def run_seller_operations(self, tester):
        """Run seller operations"""
        sock = None
        try:
            sock = self.connect_to_server()
            
            # Create account
            response, rt = self.make_request(
                sock,
                API_SELLER_CREATE_ACCOUNT,
                {
                    'username': self.username,
                    'password': self.password,
                    'seller_name': f"Seller {self.client_id}"
                }
            )
            
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
                self.user_id = response['data']['seller_id']
            else:
                tester.record_error()
                return
            
            # Login
            response, rt = self.make_request(
                sock,
                API_SELLER_LOGIN,
                {
                    'username': self.username,
                    'password': self.password
                }
            )
            
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
                self.session_id = response['data']['session_id']
            else:
                tester.record_error()
                return
            
            item_ids = []
            
            # Perform operations
            for i in range(self.operations_count):
                # Register item
                response, rt = self.make_request(
                    sock,
                    API_SELLER_REGISTER_ITEM,
                    {
                        'name': f"TestItem_{self.client_id}_{i}",
                        'category': random.randint(1, 8),
                        'keywords': [f"test{j}" for j in range(3)],
                        'condition': random.choice([CONDITION_NEW, CONDITION_USED]),
                        'price': round(random.uniform(10, 1000), 2),
                        'quantity': random.randint(1, 100)
                    }
                )
                
                if response and response['status'] == STATUS_SUCCESS:
                    tester.record_response_time(rt)
                    item_ids.append(response['data']['item_id'])
                else:
                    tester.record_error()
                
                # Get rating
                response, rt = self.make_request(sock, API_SELLER_GET_RATING)
                if response and response['status'] == STATUS_SUCCESS:
                    tester.record_response_time(rt)
                else:
                    tester.record_error()
                
                # Display items
                response, rt = self.make_request(sock, API_SELLER_DISPLAY_ITEMS)
                if response and response['status'] == STATUS_SUCCESS:
                    tester.record_response_time(rt)
                else:
                    tester.record_error()
                
                # Change price of a random item
                if item_ids:
                    item_id = random.choice(item_ids)
                    response, rt = self.make_request(
                        sock,
                        API_SELLER_CHANGE_PRICE,
                        {
                            'item_id': item_id,
                            'new_price': round(random.uniform(10, 1000), 2)
                        }
                    )
                    if response and response['status'] == STATUS_SUCCESS:
                        tester.record_response_time(rt)
                    else:
                        tester.record_error()
            
            # Logout
            response, rt = self.make_request(sock, API_SELLER_LOGOUT)
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
            else:
                tester.record_error()
            
        except Exception as e:
            print(f"Seller {self.client_id} error: {e}")
            tester.record_error()
        finally:
            if sock:
                sock.close()
    
    def run_buyer_operations(self, tester):
        """Run buyer operations"""
        sock = None
        try:
            sock = self.connect_to_server()
            
            # Create account
            response, rt = self.make_request(
                sock,
                API_BUYER_CREATE_ACCOUNT,
                {
                    'username': self.username,
                    'password': self.password,
                    'buyer_name': f"Buyer {self.client_id}"
                }
            )
            
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
                self.user_id = response['data']['buyer_id']
            else:
                tester.record_error()
                return
            
            # Login
            response, rt = self.make_request(
                sock,
                API_BUYER_LOGIN,
                {
                    'username': self.username,
                    'password': self.password
                }
            )
            
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
                self.session_id = response['data']['session_id']
            else:
                tester.record_error()
                return
            
            # Perform operations
            for i in range(self.operations_count):
                # Search items
                response, rt = self.make_request(
                    sock,
                    API_BUYER_SEARCH_ITEMS,
                    {
                        'category': random.randint(1, 8),
                        'keywords': [f"test{j}" for j in range(2)]
                    }
                )
                
                found_items = []
                if response and response['status'] == STATUS_SUCCESS:
                    tester.record_response_time(rt)
                    found_items = response['data'].get('items', [])
                else:
                    tester.record_error()
                
                # Get item details for a found item
                if found_items:
                    item_id = found_items[0]['item_id']
                    response, rt = self.make_request(
                        sock,
                        API_BUYER_GET_ITEM,
                        {'item_id': item_id}
                    )
                    if response and response['status'] == STATUS_SUCCESS:
                        tester.record_response_time(rt)
                    else:
                        tester.record_error()
                    
                    # Add to cart (if available)
                    if found_items[0]['quantity'] > 0:
                        response, rt = self.make_request(
                            sock,
                            API_BUYER_ADD_TO_CART,
                            {
                                'item_id': item_id,
                                'quantity': min(2, found_items[0]['quantity'])
                            }
                        )
                        if response:
                            tester.record_response_time(rt)
                        else:
                            tester.record_error()
                
                # Display cart
                response, rt = self.make_request(sock, API_BUYER_DISPLAY_CART)
                if response and response['status'] == STATUS_SUCCESS:
                    tester.record_response_time(rt)
                else:
                    tester.record_error()
                
                # Get purchases
                response, rt = self.make_request(sock, API_BUYER_GET_PURCHASES)
                if response and response['status'] == STATUS_SUCCESS:
                    tester.record_response_time(rt)
                else:
                    tester.record_error()
            
            # Save cart
            response, rt = self.make_request(sock, API_BUYER_SAVE_CART)
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
            else:
                tester.record_error()
            
            # Logout
            response, rt = self.make_request(sock, API_BUYER_LOGOUT)
            if response and response['status'] == STATUS_SUCCESS:
                tester.record_response_time(rt)
            else:
                tester.record_error()
            
        except Exception as e:
            print(f"Buyer {self.client_id} error: {e}")
            tester.record_error()
        finally:
            if sock:
                sock.close()
    
    def run(self, tester):
        """Run the test client"""
        if self.client_type == 'seller':
            self.run_seller_operations(tester)
        else:
            self.run_buyer_operations(tester)


def run_scenario(num_sellers, num_buyers, operations_per_client=10, num_runs=10):
    """
    Run a test scenario
    
    Args:
        num_sellers: Number of concurrent sellers
        num_buyers: Number of concurrent buyers
        operations_per_client: Number of operations each client performs
        num_runs: Number of times to run this scenario
    """
    print(f"\n{'='*70}")
    print(f"SCENARIO: {num_sellers} Sellers, {num_buyers} Buyers")
    print(f"Operations per client: {operations_per_client}")
    print(f"Number of runs: {num_runs}")
    print(f"{'='*70}")
    
    all_run_stats = []
    
    for run in range(num_runs):
        print(f"\nRun {run + 1}/{num_runs}...")
        
        tester = PerformanceTester()
        threads = []
        
        start_time = time.time()
        
        # Create seller threads
        for i in range(num_sellers):
            client = TestClient('seller', i, operations_per_client)
            thread = threading.Thread(target=client.run, args=(tester,))
            threads.append(thread)
        
        # Create buyer threads
        for i in range(num_buyers):
            client = TestClient('buyer', i, operations_per_client)
            thread = threading.Thread(target=client.run, args=(tester,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        stats = tester.get_statistics()
        if stats:
            stats['total_time'] = total_time
            stats['throughput'] = stats['operations_completed'] / total_time if total_time > 0 else 0
            all_run_stats.append(stats)
            
            print(f"  Completed in {total_time:.2f}s")
            print(f"  Operations: {stats['operations_completed']}, Errors: {stats['errors']}")
            print(f"  Avg Response Time: {stats['avg_response_time']*1000:.2f}ms")
            print(f"  Throughput: {stats['throughput']:.2f} ops/sec")
    
    # Calculate aggregate statistics
    print(f"\n{'='*70}")
    print(f"AGGREGATE RESULTS ({num_runs} runs)")
    print(f"{'='*70}")
    
    if all_run_stats:
        avg_response_times = [s['avg_response_time'] for s in all_run_stats]
        throughputs = [s['throughput'] for s in all_run_stats]
        
        print(f"Average Response Time:")
        print(f"  Mean:   {statistics.mean(avg_response_times)*1000:.2f}ms")
        print(f"  Median: {statistics.median(avg_response_times)*1000:.2f}ms")
        print(f"  StdDev: {statistics.stdev(avg_response_times)*1000:.2f}ms" if len(avg_response_times) > 1 else "  StdDev: N/A")
        
        print(f"\nAverage Throughput:")
        print(f"  Mean:   {statistics.mean(throughputs):.2f} ops/sec")
        print(f"  Median: {statistics.median(throughputs):.2f} ops/sec")
        print(f"  StdDev: {statistics.stdev(throughputs):.2f} ops/sec" if len(throughputs) > 1 else "  StdDev: N/A")
        
        total_ops = sum(s['operations_completed'] for s in all_run_stats)
        total_errors = sum(s['errors'] for s in all_run_stats)
        print(f"\nTotal Operations: {total_ops}")
        print(f"Total Errors: {total_errors}")
        print(f"Error Rate: {(total_errors/total_ops*100) if total_ops > 0 else 0:.2f}%")
    
    return all_run_stats


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("ONLINE MARKETPLACE PERFORMANCE TESTING")
    print("="*70)
    
    # Wait for servers to be ready
    print("\nWaiting for servers to be ready...")
    time.sleep(2)
    
    # Scenario 1: 1 seller, 1 buyer
    print("\n" + "="*70)
    print("SCENARIO 1: Light Load (1 Seller, 1 Buyer)")
    print("="*70)
    scenario1_stats = run_scenario(
        num_sellers=1,
        num_buyers=1,
        operations_per_client=100,  # 1000 operations total per client
        num_runs=10
    )
    
    # Scenario 2: 10 sellers, 10 buyers
    print("\n" + "="*70)
    print("SCENARIO 2: Medium Load (10 Sellers, 10 Buyers)")
    print("="*70)
    scenario2_stats = run_scenario(
        num_sellers=10,
        num_buyers=10,
        operations_per_client=50,  # 1000 operations total per client
        num_runs=10
    )
    
    # Scenario 3: 100 sellers, 100 buyers
    print("\n" + "="*70)
    print("SCENARIO 3: Heavy Load (100 Sellers, 100 Buyers)")
    print("="*70)
    scenario3_stats = run_scenario(
        num_sellers=100,
        num_buyers=100,
        operations_per_client=5,  # 1000 operations total per client
        num_runs=10
    )
    
    # Final summary
    print("\n" + "="*70)
    print("PERFORMANCE SUMMARY")
    print("="*70)
    
    scenarios = [
        ("Scenario 1 (1S+1B)", scenario1_stats),
        ("Scenario 2 (10S+10B)", scenario2_stats),
        ("Scenario 3 (100S+100B)", scenario3_stats)
    ]
    
    print(f"\n{'Scenario':<25} {'Avg RT (ms)':<15} {'Avg Throughput (ops/s)':<25}")
    print("-" * 70)
    
    for name, stats in scenarios:
        if stats:
            avg_rt = statistics.mean([s['avg_response_time'] for s in stats]) * 1000
            avg_tp = statistics.mean([s['throughput'] for s in stats])
            print(f"{name:<25} {avg_rt:<15.2f} {avg_tp:<25.2f}")
    
    print("\n" + "="*70)
    print("Testing complete!")
    print("="*70)


if __name__ == '__main__':
    main()
