"""
Performance Testing Script
Tests the system with varying numbers of concurrent clients
Measures response time and throughput
Logs results to both terminal and file
"""

import socket
import threading
import time
import random
import statistics
import sys
import os
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.protocol import Protocol
from shared.constants import *


def setup_logging():
    """Setup logging to both file and console"""
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'performance_test_{timestamp}.log')
    
    # Create logger
    logger = logging.getLogger('PerformanceTest')
    logger.setLevel(logging.INFO)
    
    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(message)s')
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger, log_file


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


def run_scenario(logger, num_sellers, num_buyers, operations_per_client=10, num_runs=10):
    """
    Run a test scenario
    
    Args:
        logger: Logger instance
        num_sellers: Number of concurrent sellers
        num_buyers: Number of concurrent buyers
        operations_per_client: Number of operations each client performs
        num_runs: Number of times to run this scenario
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"SCENARIO: {num_sellers} Sellers, {num_buyers} Buyers")
    logger.info(f"Operations per client: {operations_per_client}")
    logger.info(f"Number of runs: {num_runs}")
    logger.info(f"{'='*70}")
    
    all_run_stats = []
    
    for run in range(num_runs):
        logger.info(f"\nRun {run + 1}/{num_runs}...")
        
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
            
            logger.info(f"  Completed in {total_time:.2f}s")
            logger.info(f"  Operations: {stats['operations_completed']}, Errors: {stats['errors']}")
            logger.info(f"  Avg Response Time: {stats['avg_response_time']*1000:.2f}ms")
            logger.info(f"  Throughput: {stats['throughput']:.2f} ops/sec")
    
    # Calculate aggregate statistics
    logger.info(f"\n{'='*70}")
    logger.info(f"AGGREGATE RESULTS ({num_runs} runs)")
    logger.info(f"{'='*70}")
    
    if all_run_stats:
        avg_response_times = [s['avg_response_time'] for s in all_run_stats]
        throughputs = [s['throughput'] for s in all_run_stats]
        
        logger.info(f"Average Response Time:")
        logger.info(f"  Mean:   {statistics.mean(avg_response_times)*1000:.2f}ms")
        logger.info(f"  Median: {statistics.median(avg_response_times)*1000:.2f}ms")
        logger.info(f"  StdDev: {statistics.stdev(avg_response_times)*1000:.2f}ms" if len(avg_response_times) > 1 else "  StdDev: N/A")
        
        logger.info(f"\nAverage Throughput:")
        logger.info(f"  Mean:   {statistics.mean(throughputs):.2f} ops/sec")
        logger.info(f"  Median: {statistics.median(throughputs):.2f} ops/sec")
        logger.info(f"  StdDev: {statistics.stdev(throughputs):.2f} ops/sec" if len(throughputs) > 1 else "  StdDev: N/A")
        
        total_ops = sum(s['operations_completed'] for s in all_run_stats)
        total_errors = sum(s['errors'] for s in all_run_stats)
        logger.info(f"\nTotal Operations: {total_ops}")
        logger.info(f"Total Errors: {total_errors}")
        logger.info(f"Error Rate: {(total_errors/total_ops*100) if total_ops > 0 else 0:.2f}%")
    
    return all_run_stats


def write_csv_summary(log_dir, scenarios):
    """Write a CSV summary of all scenarios"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_file = os.path.join(log_dir, f'performance_summary_{timestamp}.csv')
    
    with open(csv_file, 'w') as f:
        # Write header
        f.write("Scenario,Num_Sellers,Num_Buyers,Ops_Per_Client,Num_Runs,")
        f.write("Avg_Response_Time_ms,Median_Response_Time_ms,StdDev_Response_Time_ms,")
        f.write("Avg_Throughput_ops_sec,Median_Throughput_ops_sec,StdDev_Throughput_ops_sec,")
        f.write("Total_Operations,Total_Errors,Error_Rate_Percent\n")
        
        # Write data for each scenario
        for scenario in scenarios:
            name = scenario['name']
            num_sellers = scenario['num_sellers']
            num_buyers = scenario['num_buyers']
            ops_per_client = scenario['ops_per_client']
            num_runs = scenario['num_runs']
            stats = scenario['stats']
            
            if stats:
                avg_response_times = [s['avg_response_time'] for s in stats]
                throughputs = [s['throughput'] for s in stats]
                total_ops = sum(s['operations_completed'] for s in stats)
                total_errors = sum(s['errors'] for s in stats)
                
                avg_rt = statistics.mean(avg_response_times) * 1000
                median_rt = statistics.median(avg_response_times) * 1000
                stddev_rt = statistics.stdev(avg_response_times) * 1000 if len(avg_response_times) > 1 else 0
                
                avg_tp = statistics.mean(throughputs)
                median_tp = statistics.median(throughputs)
                stddev_tp = statistics.stdev(throughputs) if len(throughputs) > 1 else 0
                
                error_rate = (total_errors / total_ops * 100) if total_ops > 0 else 0
                
                f.write(f"{name},{num_sellers},{num_buyers},{ops_per_client},{num_runs},")
                f.write(f"{avg_rt:.2f},{median_rt:.2f},{stddev_rt:.2f},")
                f.write(f"{avg_tp:.2f},{median_tp:.2f},{stddev_tp:.2f},")
                f.write(f"{total_ops},{total_errors},{error_rate:.2f}\n")
    
    return csv_file


def main():
    """Main entry point"""
    # Setup logging
    logger, log_file = setup_logging()
    log_dir = os.path.dirname(log_file)
    
    logger.info("\n" + "="*70)
    logger.info("ONLINE MARKETPLACE PERFORMANCE TESTING")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Log file: {log_file}")
    logger.info("="*70)
    
    # Wait for servers to be ready
    logger.info("\nWaiting for servers to be ready...")
    time.sleep(2)
    
    # Store all scenario results for CSV export
    all_scenarios = []
    
    # Scenario 1: 1 seller, 1 buyer
    logger.info("\n" + "="*70)
    logger.info("SCENARIO 1: Light Load (1 Seller, 1 Buyer)")
    logger.info("="*70)
    scenario1_stats = run_scenario(
        logger,
        num_sellers=1,
        num_buyers=1,
        operations_per_client=100,
        num_runs=10
    )
    all_scenarios.append({
        'name': 'Light Load (1S+1B)',
        'num_sellers': 1,
        'num_buyers': 1,
        'ops_per_client': 100,
        'num_runs': 10,
        'stats': scenario1_stats
    })
    
    # Scenario 2: 10 sellers, 10 buyers
    logger.info("\n" + "="*70)
    logger.info("SCENARIO 2: Medium Load (10 Sellers, 10 Buyers)")
    logger.info("="*70)
    scenario2_stats = run_scenario(
        logger,
        num_sellers=10,
        num_buyers=10,
        operations_per_client=50,
        num_runs=10
    )
    all_scenarios.append({
        'name': 'Medium Load (10S+10B)',
        'num_sellers': 10,
        'num_buyers': 10,
        'ops_per_client': 50,
        'num_runs': 10,
        'stats': scenario2_stats
    })
    
    # Scenario 3: 100 sellers, 100 buyers
    logger.info("\n" + "="*70)
    logger.info("SCENARIO 3: Heavy Load (100 Sellers, 100 Buyers)")
    logger.info("="*70)
    scenario3_stats = run_scenario(
        logger,
        num_sellers=100,
        num_buyers=100,
        operations_per_client=5,
        num_runs=10
    )
    all_scenarios.append({
        'name': 'Heavy Load (100S+100B)',
        'num_sellers': 100,
        'num_buyers': 100,
        'ops_per_client': 5,
        'num_runs': 10,
        'stats': scenario3_stats
    })
    
    # Final summary
    logger.info("\n" + "="*70)
    logger.info("PERFORMANCE SUMMARY")
    logger.info("="*70)
    
    scenarios = [
        ("Scenario 1 (1S+1B)", scenario1_stats),
        ("Scenario 2 (10S+10B)", scenario2_stats),
        ("Scenario 3 (100S+100B)", scenario3_stats)
    ]
    
    logger.info(f"\n{'Scenario':<25} {'Avg RT (ms)':<15} {'Avg Throughput (ops/s)':<25}")
    logger.info("-" * 70)
    
    for name, stats in scenarios:
        if stats:
            avg_rt = statistics.mean([s['avg_response_time'] for s in stats]) * 1000
            avg_tp = statistics.mean([s['throughput'] for s in stats])
            logger.info(f"{name:<25} {avg_rt:<15.2f} {avg_tp:<25.2f}")
    
    # Write CSV summary
    csv_file = write_csv_summary(log_dir, all_scenarios)
    
    logger.info("\n" + "="*70)
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Log file saved to: {log_file}")
    logger.info(f"CSV summary saved to: {csv_file}")
    logger.info("Testing complete!")
    logger.info("="*70)


if __name__ == '__main__':
    main()