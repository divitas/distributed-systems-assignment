"""
Load Testing Framework for Distributed Marketplace
Tests performance under different load scenarios
"""

import threading
import time
import random
import statistics
import json
import logging
from typing import List, Dict, Tuple
from datetime import datetime
import sys
import os

# Import the client classes
# Adjust these paths based on your project structure
try:
    from buyer_client.buyer_client import BuyerClient
    from seller_client.seller_client import SellerClient  
except ImportError:
    # Fallback if modules aren't in expected locations
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from buyer_client.buyer_client import BuyerClient
    from seller_client.seller_client import SellerClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Collects and calculates performance metrics"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.response_times = []  # List of response times in milliseconds
        self.operations_completed = 0
        self.operations_failed = 0
        self.operation_types = {}  # operation_name -> count
        self.start_time = None
        self.end_time = None
    
    def record_operation(self, operation_name, response_time_ms, success=True):
        """Record a single operation"""
        with self.lock:
            self.response_times.append(response_time_ms)
            
            if success:
                self.operations_completed += 1
            else:
                self.operations_failed += 1
            
            if operation_name not in self.operation_types:
                self.operation_types[operation_name] = 0
            self.operation_types[operation_name] += 1
    
    def start(self):
        """Mark test start time"""
        self.start_time = time.time()
    
    def end(self):
        """Mark test end time"""
        self.end_time = time.time()
    
    def get_summary(self):
        """Calculate and return summary statistics"""
        with self.lock:
            if not self.response_times:
                return {
                    'error': 'No operations recorded'
                }
            
            total_time = (self.end_time - self.start_time) if self.end_time else 0
            
            return {
                'total_operations': len(self.response_times),
                'successful_operations': self.operations_completed,
                'failed_operations': self.operations_failed,
                'total_time_seconds': round(total_time, 2),
                'avg_response_time_ms': round(statistics.mean(self.response_times), 2),
                'median_response_time_ms': round(statistics.median(self.response_times), 2),
                'min_response_time_ms': round(min(self.response_times), 2),
                'max_response_time_ms': round(max(self.response_times), 2),
                'std_dev_ms': round(statistics.stdev(self.response_times), 2) if len(self.response_times) > 1 else 0,
                'p95_response_time_ms': round(self._percentile(self.response_times, 95), 2),
                'p99_response_time_ms': round(self._percentile(self.response_times, 99), 2),
                'throughput_ops_per_sec': round(self.operations_completed / total_time, 2) if total_time > 0 else 0,
                'operation_breakdown': self.operation_types.copy()
            }
    
    def _percentile(self, data, percentile):
        """Calculate percentile of data"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


class ClientSimulator:
    """Simulates a buyer or seller client"""
    
    def __init__(self, client_type, client_id, server_address, 
                 operations_per_client=100, think_time=0.01):
        """
        Args:
            client_type: 'buyer' or 'seller'
            client_id: Unique identifier for this client
            server_address: (host, port) tuple
            operations_per_client: Number of operations to perform
            think_time: Delay between operations (seconds)
        """
        self.client_type = client_type
        self.client_id = client_id
        self.server_address = server_address
        self.operations_per_client = operations_per_client
        self.think_time = think_time
        self.metrics = PerformanceMetrics()
        
        # Create the appropriate client instance
        try:
            if client_type == 'buyer':
                self.client = BuyerClient(*server_address)
            else:
                self.client = SellerClient(*server_address)
        except Exception as e:
            logger.error(f"Failed to create {client_type} client: {e}")
            self.client = None
        
        # Store session data
        self.session_id = None
        self.user_id = None
        
        # Store created items for sellers
        self.created_items = []
    
    def run(self):
        """Execute the client simulation"""
        if not self.client:
            logger.error(f"{self.client_type} {self.client_id}: No client available")
            return
        
        try:
            # Connect to server
            self.client.connect()
            
            # Setup phase - create account and login
            username = f"{self.client_type}_{self.client_id}_{random.randint(1000, 9999)}"
            password = "testpass123"
            
            # Create account
            start = time.time()
            response = self._create_account(username, password)
            elapsed = (time.time() - start) * 1000
            success = response.get('status') == 'success'
            self.metrics.record_operation('create_account', elapsed, success=success)
            
            if not success:
                logger.error(f"{self.client_type} {self.client_id}: Account creation failed - {response.get('error_message')}")
                return
            
            self.user_id = response.get('data', {}).get(f'{self.client_type}_id')
            
            # Login
            start = time.time()
            response = self._login(username, password)
            elapsed = (time.time() - start) * 1000
            success = response.get('status') == 'success'
            self.metrics.record_operation('login', elapsed, success=success)
            
            if not success:
                logger.error(f"{self.client_type} {self.client_id}: Login failed - {response.get('error_message')}")
                return
            
            self.session_id = response.get('data', {}).get('session_id')
            
            if not self.session_id:
                logger.error(f"{self.client_type} {self.client_id}: No session ID received")
                return
            
            # Perform operations
            for i in range(self.operations_per_client):
                if self.client_type == 'buyer':
                    self._run_buyer_operation()
                else:
                    self._run_seller_operation()
                
                # Think time between operations
                if self.think_time > 0:
                    time.sleep(self.think_time)
            
            # Logout
            start = time.time()
            response = self._logout()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_operation('logout', elapsed,
                                        success=response.get('status') == 'success')
        
        except Exception as e:
            logger.error(f"{self.client_type} {self.client_id}: Error - {e}")
        
        finally:
            # Disconnect from server
            try:
                if self.client:
                    self.client.disconnect()
            except:
                pass
    
    def _create_account(self, username, password):
        """Create account using the client"""
        try:
            request = {
                "type": "CREATE_ACCOUNT",
                "data": {
                    "username": username,
                    "password": password
                }
            }
            return self.client.send_request(request)
        except Exception as e:
            logger.error(f"Create account error: {e}")
            return {'status': 'error', 'error_message': str(e)}
    
    def _login(self, username, password):
        """Login using the client"""
        try:
            request = {
                "type": "LOGIN",
                "data": {
                    "username": username,
                    "password": password
                }
            }
            return self.client.send_request(request)
        except Exception as e:
            logger.error(f"Login error: {e}")
            return {'status': 'error', 'error_message': str(e)}
    
    def _logout(self):
        """Logout using the client"""
        try:
            request = {
                "type": "LOGOUT",
                "session_id": self.session_id
            }
            return self.client.send_request(request)
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return {'status': 'error', 'error_message': str(e)}
    
    def _run_buyer_operation(self):
        """Perform a random buyer operation"""
        operations = [
            ('search_items', 0.4),
            ('get_item', 0.15),
            ('add_to_cart', 0.15),
            ('display_cart', 0.1),
            ('remove_from_cart', 0.05),
            ('get_seller_rating', 0.1),
            ('clear_cart', 0.05)
        ]
        
        operation = self._weighted_choice(operations)
        
        start = time.time()
        response = {'status': 'error'}
        
        try:
            if operation == 'search_items':
                # Search for items
                category = random.randint(0, 10)
                keywords = [f"keyword{random.randint(1, 20)}"] if random.random() > 0.5 else []
                
                request = {
                    "type": "SEARCH_ITEMS",
                    "session_id": self.session_id,
                    "data": {
                        "category": category,
                        "keywords": keywords
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'get_item':
                # Get a specific item (random item ID)
                item_id = random.randint(1, 1000)
                
                request = {
                    "type": "GET_ITEM",
                    "session_id": self.session_id,
                    "data": {
                        "item_id": item_id
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'add_to_cart':
                # Add random item to cart
                item_id = random.randint(1, 1000)
                quantity = random.randint(1, 5)
                
                request = {
                    "type": "ADD_TO_CART",
                    "session_id": self.session_id,
                    "data": {
                        "item_id": item_id,
                        "quantity": quantity
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'display_cart':
                # Display cart
                request = {
                    "type": "DISPLAY_CART",
                    "session_id": self.session_id
                }
                response = self.client.send_request(request)
            
            elif operation == 'remove_from_cart':
                # Remove random item from cart
                item_id = random.randint(1, 1000)
                quantity = random.randint(1, 3)
                
                request = {
                    "type": "REMOVE_FROM_CART",
                    "session_id": self.session_id,
                    "data": {
                        "item_id": item_id,
                        "quantity": quantity
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'get_seller_rating':
                # Get seller rating
                seller_id = random.randint(1, 100)
                
                request = {
                    "type": "GET_SELLER_RATING",
                    "session_id": self.session_id,
                    "data": {
                        "seller_id": seller_id
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'clear_cart':
                # Clear cart
                request = {
                    "type": "CLEAR_CART",
                    "session_id": self.session_id
                }
                response = self.client.send_request(request)
            
            elapsed = (time.time() - start) * 1000
            self.metrics.record_operation(operation, elapsed,
                                        success=response.get('status') == 'success')
        
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            self.metrics.record_operation(operation, elapsed, success=False)
            logger.debug(f"Buyer operation {operation} failed: {e}")
    
    def _run_seller_operation(self):
        """Perform a random seller operation"""
        operations = [
            ('register_item', 0.3),
            ('display_items', 0.25),
            ('change_price', 0.15),
            ('update_quantity', 0.15),
            ('get_rating', 0.15)
        ]
        
        operation = self._weighted_choice(operations)
        
        start = time.time()
        response = {'status': 'error'}
        
        try:
            if operation == 'register_item':
                # Register a new item
                item_name = f"Item_{random.randint(1000, 9999)}"
                category = random.randint(0, 10)
                keywords = [f"kw{i}" for i in range(random.randint(1, 5))]
                condition = random.choice(["New", "Used"])
                sale_price = round(random.uniform(10.0, 1000.0), 2)
                quantity = random.randint(1, 100)
                
                request = {
                    "type": "REGISTER_ITEM",
                    "session_id": self.session_id,
                    "data": {
                        "name": item_name,
                        "category": category,
                        "keywords": keywords,
                        "condition": condition,
                        "sale_price": sale_price,
                        "quantity": quantity
                    }
                }
                response = self.client.send_request(request)
                
                # Store created item ID for future operations
                if response.get('status') == 'success':
                    item_id = response.get('data', {}).get('item_id')
                    if item_id:
                        self.created_items.append(item_id)
            
            elif operation == 'display_items':
                # Display all items for this seller
                request = {
                    "type": "DISPLAY_ITEMS_FOR_SALE",
                    "session_id": self.session_id
                }
                response = self.client.send_request(request)
            
            elif operation == 'change_price':
                # Change price of an existing item
                if self.created_items:
                    item_id = random.choice(self.created_items)
                else:
                    item_id = random.randint(1, 1000)
                
                new_price = round(random.uniform(10.0, 1000.0), 2)
                
                request = {
                    "type": "CHANGE_ITEM_PRICE",
                    "session_id": self.session_id,
                    "data": {
                        "item_id": item_id,
                        "new_price": new_price
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'update_quantity':
                # Update quantity of an existing item
                if self.created_items:
                    item_id = random.choice(self.created_items)
                else:
                    item_id = random.randint(1, 1000)
                
                quantity_to_remove = random.randint(1, 10)
                
                request = {
                    "type": "UPDATE_UNITS_FOR_SALE",
                    "session_id": self.session_id,
                    "data": {
                        "item_id": item_id,
                        "quantity_to_remove": quantity_to_remove
                    }
                }
                response = self.client.send_request(request)
            
            elif operation == 'get_rating':
                # Get seller's own rating
                request = {
                    "type": "GET_SELLER_RATING",
                    "session_id": self.session_id
                }
                response = self.client.send_request(request)
            
            elapsed = (time.time() - start) * 1000
            self.metrics.record_operation(operation, elapsed,
                                        success=response.get('status') == 'success')
        
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            self.metrics.record_operation(operation, elapsed, success=False)
            logger.debug(f"Seller operation {operation} failed: {e}")
    
    def _weighted_choice(self, choices):
        """Make a weighted random choice"""
        operations, weights = zip(*choices)
        return random.choices(operations, weights=weights)[0]


class LoadTest:
    """Orchestrates load testing scenarios"""
    
    def __init__(self, buyer_server_address, seller_server_address):
        self.buyer_server_address = buyer_server_address
        self.seller_server_address = seller_server_address
    
    def run_scenario(self, num_buyers, num_sellers, operations_per_client=100,
                    think_time=0.01):
        """
        Run a load test scenario
        
        Args:
            num_buyers: Number of concurrent buyers
            num_sellers: Number of concurrent sellers
            operations_per_client: Operations each client performs
            think_time: Delay between operations (seconds)
            
        Returns:
            Dictionary with performance metrics
        """
        logger.info("="*80)
        logger.info(f"Starting Load Test Scenario")
        logger.info(f"  Buyers: {num_buyers}")
        logger.info(f"  Sellers: {num_sellers}")
        logger.info(f"  Operations per client: {operations_per_client}")
        logger.info(f"  Think time: {think_time}s")
        logger.info("="*80)
        
        # Create client simulators
        buyers = [
            ClientSimulator('buyer', i, self.buyer_server_address,
                          operations_per_client, think_time)
            for i in range(num_buyers)
        ]
        
        sellers = [
            ClientSimulator('seller', i, self.seller_server_address,
                          operations_per_client, think_time)
            for i in range(num_sellers)
        ]
        
        all_clients = buyers + sellers
        
        # Create and start threads
        threads = []
        for client in all_clients:
            t = threading.Thread(target=client.run)
            threads.append(t)
        
        # Start all threads
        start_time = time.time()
        
        for t in threads:
            t.start()
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Aggregate metrics
        aggregated = self._aggregate_metrics(all_clients, total_time)
        
        # Print results
        self._print_results(aggregated)
        
        return aggregated
    
    def _aggregate_metrics(self, clients, total_time):
        """Aggregate metrics from all clients"""
        all_response_times = []
        total_completed = 0
        total_failed = 0
        operation_breakdown = {}
        
        for client in clients:
            summary = client.metrics.get_summary()
            if 'error' not in summary:
                all_response_times.extend(client.metrics.response_times)
                total_completed += summary['successful_operations']
                total_failed += summary['failed_operations']
                
                for op, count in summary['operation_breakdown'].items():
                    operation_breakdown[op] = operation_breakdown.get(op, 0) + count
        
        if not all_response_times:
            return {'error': 'No operations completed'}
        
        return {
            'total_time_seconds': round(total_time, 2),
            'total_operations': len(all_response_times),
            'successful_operations': total_completed,
            'failed_operations': total_failed,
            'avg_response_time_ms': round(statistics.mean(all_response_times), 2),
            'median_response_time_ms': round(statistics.median(all_response_times), 2),
            'min_response_time_ms': round(min(all_response_times), 2),
            'max_response_time_ms': round(max(all_response_times), 2),
            'std_dev_ms': round(statistics.stdev(all_response_times), 2) if len(all_response_times) > 1 else 0,
            'p95_response_time_ms': round(self._percentile(all_response_times, 95), 2),
            'p99_response_time_ms': round(self._percentile(all_response_times, 99), 2),
            'throughput_ops_per_sec': round(total_completed / total_time, 2) if total_time > 0 else 0,
            'operation_breakdown': operation_breakdown
        }
    
    def _percentile(self, data, percentile):
        """Calculate percentile"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _print_results(self, metrics):
        """Print formatted results"""
        print("\n" + "="*80)
        print("LOAD TEST RESULTS")
        print("="*80)
        
        if 'error' in metrics:
            print(f"ERROR: {metrics['error']}")
            return
        
        print(f"Total Time:              {metrics['total_time_seconds']} seconds")
        print(f"Total Operations:        {metrics['total_operations']}")
        print(f"Successful:              {metrics['successful_operations']}")
        print(f"Failed:                  {metrics['failed_operations']}")
        print(f"\nResponse Time Statistics:")
        print(f"  Average:               {metrics['avg_response_time_ms']} ms")
        print(f"  Median:                {metrics['median_response_time_ms']} ms")
        print(f"  Min:                   {metrics['min_response_time_ms']} ms")
        print(f"  Max:                   {metrics['max_response_time_ms']} ms")
        print(f"  Std Dev:               {metrics['std_dev_ms']} ms")
        print(f"  95th Percentile:       {metrics['p95_response_time_ms']} ms")
        print(f"  99th Percentile:       {metrics['p99_response_time_ms']} ms")
        print(f"\nThroughput:              {metrics['throughput_ops_per_sec']} ops/sec")
        
        print(f"\nOperation Breakdown:")
        for op, count in sorted(metrics['operation_breakdown'].items()):
            print(f"  {op:25} {count:6} operations")
        
        print("="*80 + "\n")


def main():
    """Main function to run all test scenarios"""
    
    # Configure server addresses
    buyer_server = ('localhost', 5001)
    seller_server = ('localhost', 5002)
    
    tester = LoadTest(buyer_server, seller_server)
    
    # Store results for comparison
    results = {}
    
    # Scenario 1: Light Load - 1 Buyer + 1 Seller
    print("\n" + "#"*80)
    print("# SCENARIO 1: Light Load - 1 Buyer + 1 Seller")
    print("#"*80)
    results['scenario_1'] = tester.run_scenario(
        num_buyers=1,
        num_sellers=1,
        operations_per_client=100,
        think_time=0.01
    )
    
    # Wait between scenarios
    time.sleep(2)
    
    # Scenario 2: Medium Load - 10 Buyers + 10 Sellers
    print("\n" + "#"*80)
    print("# SCENARIO 2: Medium Load - 10 Buyers + 10 Sellers")
    print("#"*80)
    results['scenario_2'] = tester.run_scenario(
        num_buyers=10,
        num_sellers=10,
        operations_per_client=100,
        think_time=0.01
    )
    
    # Wait between scenarios
    time.sleep(2)
    
    # Scenario 3: Heavy Load - 50 Buyers + 50 Sellers
    print("\n" + "#"*80)
    print("# SCENARIO 3: Heavy Load - 50 Buyers + 50 Sellers")
    print("#"*80)
    results['scenario_3'] = tester.run_scenario(
        num_buyers=50,
        num_sellers=50,
        operations_per_client=100,
        think_time=0.01
    )
    
    # Print comparison summary
    print("\n" + "="*80)
    print("SUMMARY COMPARISON")
    print("="*80)
    print(f"{'Scenario':<20} {'Clients':<15} {'Avg RT (ms)':<15} {'Throughput':<20} {'Errors':<10}")
    print("-"*80)
    
    for scenario_name, data in results.items():
        if 'error' not in data:
            scenario_label = scenario_name.replace('_', ' ').title()
            
            if scenario_name == 'scenario_1':
                clients = "1B + 1S"
            elif scenario_name == 'scenario_2':
                clients = "10B + 10S"
            else:
                clients = "50B + 50S"
            
            print(f"{scenario_label:<20} {clients:<15} {data['avg_response_time_ms']:<15.2f} "
                  f"{data['throughput_ops_per_sec']:<20.2f} {data['failed_operations']:<10}")
    
    print("="*80)
    
    # Save results to JSON
    output_file = f"load_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()