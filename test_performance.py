"""
test_performance_progressive.py - Progressive Performance Testing

Starts with minimal load and gradually increases to identify bottlenecks.
Much simpler than the full test suite - focuses on core metrics.
"""

import sys
import os
import time
import threading
import statistics
from dataclasses import dataclass, field
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buyer_client.buyer_client import BuyerClient
from buyer_client.buyer_api import BuyerAPI
from seller_client.seller_client import SellerClient
from seller_client.seller_api import SellerAPI


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class Config:
    buyer_server_host: str = "localhost"
    buyer_server_port: int = 5001
    seller_server_host: str = "localhost"
    seller_server_port: int = 5002


CONFIG = Config()


# =============================================================================
# Simple Metrics
# =============================================================================

@dataclass
class SimpleMetrics:
    """Simple metrics collection."""
    response_times: List[float] = field(default_factory=list)
    operations_completed: int = 0
    errors: int = 0
    
    def record_operation(self, response_time: float, success: bool = True):
        """Record a single operation."""
        if success:
            self.response_times.append(response_time)
            self.operations_completed += 1
        else:
            self.errors += 1
    
    @property
    def avg_response_time_ms(self) -> float:
        if self.response_times:
            return statistics.mean(self.response_times) * 1000
        return 0
    
    @property
    def median_response_time_ms(self) -> float:
        if self.response_times:
            return statistics.median(self.response_times) * 1000
        return 0


# =============================================================================
# Simple Workloads
# =============================================================================

def simple_seller_workload(client_id: int, num_operations: int, metrics: SimpleMetrics):
    """
    Simple seller workload - just register items and display them.
    """
    try:
        print(f"    Seller {client_id}: Connecting...", flush=True)
        client = SellerClient(CONFIG.seller_server_host, CONFIG.seller_server_port)
        client.connect()
        api = SellerAPI(client)
        
        # Create account
        username = f"s{client_id}_{int(time.time()) % 100000}"
        print(f"    Seller {client_id}: Creating account {username}...", flush=True)
        api.create_account(username, "pass")
        api.login(username, "pass")
        print(f"    Seller {client_id}: Logged in", flush=True)
        
        # Perform operations
        for i in range(num_operations):
            op_start = time.time()
            
            try:
                if i % 2 == 0:
                    # Register item
                    api.register_item(
                        name=f"Item{client_id}_{i}",
                        category=(i % 10) + 1,
                        keywords=["test"],
                        condition="New",
                        sale_price=10.0 + i,
                        quantity=10
                    )
                else:
                    # Display items
                    api.display_items_for_sale()
                
                op_end = time.time()
                metrics.record_operation(op_end - op_start, success=True)
                
                if (i + 1) % 10 == 0:
                    print(f"    Seller {client_id}: {i + 1}/{num_operations} ops", flush=True)
                
            except Exception as e:
                print(f"    Seller {client_id}: Operation {i} failed: {e}", flush=True)
                metrics.record_operation(0, success=False)
        
        print(f"    Seller {client_id}: Logging out...", flush=True)
        api.logout()
        client.disconnect()
        print(f"    Seller {client_id}: Done!", flush=True)
        
    except Exception as e:
        print(f"    Seller {client_id}: CRITICAL ERROR: {e}", flush=True)
        metrics.errors += 1


def simple_buyer_workload(client_id: int, num_operations: int, metrics: SimpleMetrics):
    """
    Simple buyer workload - just search and view items.
    """
    try:
        print(f"    Buyer {client_id}: Connecting...", flush=True)
        client = BuyerClient(CONFIG.buyer_server_host, CONFIG.buyer_server_port)
        client.connect()
        api = BuyerAPI(client)
        
        # Create account
        username = f"b{client_id}_{int(time.time()) % 100000}"
        print(f"    Buyer {client_id}: Creating account {username}...", flush=True)
        api.create_account(username, "pass")
        api.login(username, "pass")
        print(f"    Buyer {client_id}: Logged in", flush=True)
        
        # Perform operations
        for i in range(num_operations):
            op_start = time.time()
            
            try:
                if i % 3 == 0:
                    # Search
                    api.search_items(category=(i % 10) + 1, keywords=["test"])
                elif i % 3 == 1:
                    # Display cart
                    api.display_cart()
                else:
                    # Search with different category
                    api.search_items(category=1, keywords=[])
                
                op_end = time.time()
                metrics.record_operation(op_end - op_start, success=True)
                
                if (i + 1) % 10 == 0:
                    print(f"    Buyer {client_id}: {i + 1}/{num_operations} ops", flush=True)
                
            except Exception as e:
                print(f"    Buyer {client_id}: Operation {i} failed: {e}", flush=True)
                metrics.record_operation(0, success=False)
        
        print(f"    Buyer {client_id}: Logging out...", flush=True)
        api.logout()
        client.disconnect()
        print(f"    Buyer {client_id}: Done!", flush=True)
        
    except Exception as e:
        print(f"    Buyer {client_id}: CRITICAL ERROR: {e}", flush=True)
        metrics.errors += 1


# =============================================================================
# Test Scenarios
# =============================================================================

def run_simple_test(name: str, num_sellers: int, num_buyers: int, ops_per_client: int):
    """
    Run a simple test scenario.
    """
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"  Sellers: {num_sellers}, Buyers: {num_buyers}")
    print(f"  Operations per client: {ops_per_client}")
    print(f"{'='*80}")
    
    # Create metrics objects
    seller_metrics = [SimpleMetrics() for _ in range(num_sellers)]
    buyer_metrics = [SimpleMetrics() for _ in range(num_buyers)]
    
    start_time = time.time()
    
    # Run clients
    with ThreadPoolExecutor(max_workers=num_sellers + num_buyers) as executor:
        futures = []
        
        # Submit sellers
        for i in range(num_sellers):
            future = executor.submit(simple_seller_workload, i, ops_per_client, seller_metrics[i])
            futures.append(future)
        
        # Submit buyers
        for i in range(num_buyers):
            future = executor.submit(simple_buyer_workload, i, ops_per_client, buyer_metrics[i])
            futures.append(future)
        
        # Wait for completion
        print("\n  Waiting for clients to complete...")
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"  Task failed: {e}")
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Aggregate metrics
    all_response_times = []
    total_ops = 0
    total_errors = 0
    
    for m in seller_metrics + buyer_metrics:
        all_response_times.extend(m.response_times)
        total_ops += m.operations_completed
        total_errors += m.errors
    
    # Print results
    print(f"\n{'='*80}")
    print(f"RESULTS: {name}")
    print(f"{'='*80}")
    print(f"Total Time:          {total_time:.2f} seconds")
    print(f"Total Operations:    {total_ops}")
    print(f"Total Errors:        {total_errors}")
    
    if all_response_times:
        avg_rt = statistics.mean(all_response_times) * 1000
        median_rt = statistics.median(all_response_times) * 1000
        throughput = total_ops / total_time if total_time > 0 else 0
        
        print(f"\nResponse Times:")
        print(f"  Average:           {avg_rt:.2f} ms")
        print(f"  Median:            {median_rt:.2f} ms")
        print(f"\nThroughput:          {throughput:.2f} ops/sec")
    else:
        print("\nNo operations completed!")
    
    print(f"{'='*80}\n")
    
    return {
        'name': name,
        'total_time': total_time,
        'total_ops': total_ops,
        'total_errors': total_errors,
        'avg_response_time_ms': statistics.mean(all_response_times) * 1000 if all_response_times else 0,
        'throughput': total_ops / total_time if total_time > 0 else 0
    }


# =============================================================================
# Main
# =============================================================================

def main():
    print("\n" + "=" * 80)
    print("PROGRESSIVE PERFORMANCE TESTING")
    print("=" * 80)
    print("\nThis will run tests with gradually increasing load:")
    print("  Phase 1: Single client smoke tests")
    print("  Phase 2: Small load (2-5 clients)")
    print("  Phase 3: Medium load (10-20 clients)")
    print("  Phase 4: Large load (50-100 clients)")
    
    # Verify servers
    import socket
    print("\nVerifying server connectivity...")
    for name, host, port in [
        ("Buyer Server", CONFIG.buyer_server_host, CONFIG.buyer_server_port),
        ("Seller Server", CONFIG.seller_server_host, CONFIG.seller_server_port),
    ]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            sock.close()
            print(f"  ✓ {name} at {host}:{port}")
        except:
            print(f"\n✗ ERROR: {name} not running on {host}:{port}")
            return 1
    
    input("\nPress Enter to start progressive testing...")
    
    results = []
    
    # Phase 1: Smoke Tests
    print("\n" + "#"*80)
    print("# PHASE 1: SMOKE TESTS (Minimal Load)")
    print("#"*80)
    
    print("\n--- Test 1.1: Single Seller ---")
    result = run_simple_test("1 Seller Only", num_sellers=1, num_buyers=0, ops_per_client=10)
    results.append(result)
    input("Press Enter to continue...")
    
    print("\n--- Test 1.2: Single Buyer ---")
    result = run_simple_test("1 Buyer Only", num_sellers=0, num_buyers=1, ops_per_client=10)
    results.append(result)
    input("Press Enter to continue...")
    
    print("\n--- Test 1.3: 1 Seller + 1 Buyer ---")
    result = run_simple_test("1 Seller + 1 Buyer", num_sellers=1, num_buyers=1, ops_per_client=10)
    results.append(result)
    input("Press Enter to continue...")
    
    # Phase 2: Small Load
    print("\n" + "#"*80)
    print("# PHASE 2: SMALL LOAD")
    print("#"*80)
    
    print("\n--- Test 2.1: 2 Sellers + 2 Buyers ---")
    result = run_simple_test("2 Sellers + 2 Buyers", num_sellers=2, num_buyers=2, ops_per_client=50)
    results.append(result)
    input("Press Enter to continue...")
    
    print("\n--- Test 2.2: 5 Sellers + 5 Buyers ---")
    result = run_simple_test("5 Sellers + 5 Buyers", num_sellers=5, num_buyers=5, ops_per_client=50)
    results.append(result)
    input("Press Enter to continue...")
    
    # Phase 3: Medium Load
    print("\n" + "#"*80)
    print("# PHASE 3: MEDIUM LOAD")
    print("#"*80)
    
    print("\n--- Test 3.1: 10 Sellers + 10 Buyers ---")
    result = run_simple_test("10 Sellers + 10 Buyers", num_sellers=10, num_buyers=10, ops_per_client=100)
    results.append(result)
    input("Press Enter to continue...")
    
    print("\n--- Test 3.2: 20 Sellers + 20 Buyers ---")
    result = run_simple_test("20 Sellers + 20 Buyers", num_sellers=20, num_buyers=20, ops_per_client=100)
    results.append(result)
    input("Press Enter to continue...")
    
    # Phase 4: Large Load (if user wants to continue)
    response = input("\nContinue to large load tests? (y/n): ")
    if response.lower() == 'y':
        print("\n" + "#"*80)
        print("# PHASE 4: LARGE LOAD")
        print("#"*80)
        
        print("\n--- Test 4.1: 50 Sellers + 50 Buyers ---")
        result = run_simple_test("50 Sellers + 50 Buyers", num_sellers=50, num_buyers=50, ops_per_client=100)
        results.append(result)
        input("Press Enter to continue...")
        
        print("\n--- Test 4.2: 100 Sellers + 100 Buyers ---")
        result = run_simple_test("100 Sellers + 100 Buyers", num_sellers=100, num_buyers=100, ops_per_client=100)
        results.append(result)
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY OF ALL TESTS")
    print("=" * 80)
    print(f"\n{'Test Name':<30} {'Time (s)':<12} {'Ops':<8} {'Errors':<8} {'Avg RT (ms)':<12} {'Throughput':<12}")
    print("-" * 90)
    
    for r in results:
        print(f"{r['name']:<30} {r['total_time']:<12.2f} {r['total_ops']:<8} "
              f"{r['total_errors']:<8} {r['avg_response_time_ms']:<12.2f} {r['throughput']:<12.2f}")
    
    print("=" * 90)
    
    # Save results
    with open("progressive_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: progressive_test_results.json")
    
    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    print("""
What to look for:

1. Smoke Tests (Phase 1):
   - Should all complete successfully with low response times
   - Establishes baseline performance
   - If these fail, there's a basic server/client issue

2. Small Load (Phase 2):
   - Response times should remain relatively stable
   - Throughput should scale roughly linearly
   - Errors should remain at 0

3. Medium Load (Phase 3):
   - May see slight increase in response times
   - Throughput scaling may start to level off
   - Should still have very low error rates

4. Large Load (Phase 4):
   - Response times will likely increase due to contention
   - Throughput may plateau or decrease
   - Watch for increased error rates

If the system hangs:
   - Check server logs for deadlocks
   - Look for connection pool exhaustion
   - Check for resource limits (threads, file descriptors)
   - Monitor CPU and memory usage
""")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())