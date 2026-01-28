"""
test_performance.py - Performance Evaluation for Assignment

This script measures:
1. Average Response Time
2. Average Server Throughput

For three scenarios:
- Scenario 1: 1 seller, 1 buyer
- Scenario 2: 10 sellers, 10 buyers
- Scenario 3: 100 sellers, 100 buyers

Each scenario runs 10 iterations with 1000 API calls per client.
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
    
    # Test parameters
    num_iterations: int = 10
    operations_per_client: int = 1000


CONFIG = Config()


# =============================================================================
# Metrics Collection
# =============================================================================

@dataclass
class ClientMetrics:
    """Metrics for a single client."""
    client_id: int
    client_type: str  # "buyer" or "seller"
    response_times: List[float] = field(default_factory=list)
    operations_completed: int = 0
    errors: int = 0
    start_time: float = 0
    end_time: float = 0
    
    @property
    def total_time(self) -> float:
        return self.end_time - self.start_time
    
    @property
    def throughput(self) -> float:
        if self.total_time > 0:
            return self.operations_completed / self.total_time
        return 0
    
    @property
    def avg_response_time(self) -> float:
        if self.response_times:
            return statistics.mean(self.response_times)
        return 0
    
    @property
    def median_response_time(self) -> float:
        if self.response_times:
            return statistics.median(self.response_times)
        return 0


@dataclass
class ScenarioResults:
    """Results for a complete scenario."""
    scenario_name: str
    num_sellers: int
    num_buyers: int
    num_iterations: int
    ops_per_client: int
    client_metrics: List[ClientMetrics] = field(default_factory=list)
    iteration_times: List[float] = field(default_factory=list)
    
    def add_metrics(self, metrics: ClientMetrics):
        self.client_metrics.append(metrics)
    
    @property
    def total_operations(self) -> int:
        return sum(m.operations_completed for m in self.client_metrics)
    
    @property
    def total_errors(self) -> int:
        return sum(m.errors for m in self.client_metrics)
    
    @property
    def all_response_times(self) -> List[float]:
        times = []
        for m in self.client_metrics:
            times.extend(m.response_times)
        return times
    
    @property
    def avg_response_time(self) -> float:
        times = self.all_response_times
        if times:
            return statistics.mean(times) * 1000  # Convert to ms
        return 0
    
    @property
    def median_response_time(self) -> float:
        times = self.all_response_times
        if times:
            return statistics.median(times) * 1000  # Convert to ms
        return 0
    
    @property
    def p95_response_time(self) -> float:
        times = sorted(self.all_response_times)
        if times:
            idx = int(len(times) * 0.95)
            return times[idx] * 1000  # Convert to ms
        return 0
    
    @property
    def avg_throughput(self) -> float:
        """Average throughput across all iterations."""
        if self.iteration_times:
            total_ops = self.total_operations
            total_time = sum(self.iteration_times)
            if total_time > 0:
                return total_ops / total_time
        return 0
    
    def print_summary(self):
        print(f"\n{'='*70}")
        print(f"SCENARIO: {self.scenario_name}")
        print(f"{'='*70}")
        print(f"Configuration:")
        print(f"  Sellers: {self.num_sellers}")
        print(f"  Buyers: {self.num_buyers}")
        print(f"  Iterations: {self.num_iterations}")
        print(f"  Operations per client: {self.ops_per_client}")
        print(f"\nResults:")
        print(f"  Total Operations: {self.total_operations}")
        print(f"  Total Errors: {self.total_errors}")
        print(f"\nResponse Time (milliseconds):")
        print(f"  Average: {self.avg_response_time:.2f} ms")
        print(f"  Median:  {self.median_response_time:.2f} ms")
        print(f"  95th %%:  {self.p95_response_time:.2f} ms")
        print(f"\nThroughput:")
        print(f"  Average: {self.avg_throughput:.2f} operations/second")
        print(f"{'='*70}")


# =============================================================================
# Client Workloads
# =============================================================================

def seller_workload(client_id: int, num_operations: int) -> ClientMetrics:
    """
    Execute seller workload and collect metrics.
    
    Workload mix:
    - 20% RegisterItem
    - 30% DisplayItems
    - 25% ChangePrice
    - 25% UpdateUnits
    """
    metrics = ClientMetrics(client_id=client_id, client_type="seller")
    
    try:
        client = SellerClient(CONFIG.seller_server_host, CONFIG.seller_server_port)
        client.connect()
        api = SellerAPI(client)
        
        # Create account and login
        username = f"perf_seller_{client_id}_{time.time()}"
        api.create_account(username, "pass")
        api.login(username, "pass")
        
        # Track registered items for price/quantity updates
        registered_items = []
        
        metrics.start_time = time.time()
        
        for i in range(num_operations):
            op_start = time.time()
            
            try:
                # Decide which operation based on distribution
                op_choice = i % 20
                
                if op_choice < 4 or len(registered_items) == 0:
                    # 20% - Register new item
                    item_id = api.register_item(
                        name=f"Item_{client_id}_{i}",
                        category=(i % 10) + 1,
                        keywords=["perf", "test"],
                        condition="New" if i % 2 == 0 else "Used",
                        sale_price=10.0 + (i % 100),
                        quantity=100
                    )
                    registered_items.append(item_id)
                    
                elif op_choice < 10:
                    # 30% - Display items
                    api.display_items_for_sale()
                    
                elif op_choice < 15:
                    # 25% - Change price
                    if registered_items:
                        item_id = registered_items[i % len(registered_items)]
                        api.change_item_price(item_id, 15.0 + (i % 50))
                        
                else:
                    # 25% - Update units (but keep some available)
                    if registered_items:
                        item_id = registered_items[i % len(registered_items)]
                        try:
                            api.update_units_for_sale(item_id, 1)
                        except:
                            pass  # May fail if no units left
                
                op_end = time.time()
                metrics.response_times.append(op_end - op_start)
                metrics.operations_completed += 1
                
            except Exception as e:
                metrics.errors += 1
        
        metrics.end_time = time.time()
        
        api.logout()
        client.disconnect()
        
    except Exception as e:
        print(f"Seller {client_id} error: {e}")
        metrics.errors += 1
    
    return metrics


def buyer_workload(client_id: int, num_operations: int) -> ClientMetrics:
    """
    Execute buyer workload and collect metrics.
    
    Workload mix:
    - 40% Search
    - 20% GetItem
    - 20% AddToCart
    - 10% DisplayCart
    - 10% RemoveFromCart
    """
    metrics = ClientMetrics(client_id=client_id, client_type="buyer")
    
    try:
        client = BuyerClient(CONFIG.buyer_server_host, CONFIG.buyer_server_port)
        client.connect()
        api = BuyerAPI(client)
        
        # Create account and login
        username = f"perf_buyer_{client_id}_{time.time()}"
        api.create_account(username, "pass")
        api.login(username, "pass")
        
        # Track items found for cart operations
        found_items = []
        
        metrics.start_time = time.time()
        
        for i in range(num_operations):
            op_start = time.time()
            
            try:
                op_choice = i % 10
                
                if op_choice < 4:
                    # 40% - Search
                    category = (i % 10) + 1
                    items = api.search_items(category=category, keywords=["perf"])
                    if items:
                        found_items.extend([item.item_id for item in items[:3]])
                        
                elif op_choice < 6:
                    # 20% - GetItem
                    if found_items:
                        item_id = found_items[i % len(found_items)]
                        api.get_item(item_id)
                        
                elif op_choice < 8:
                    # 20% - AddToCart
                    if found_items:
                        item_id = found_items[i % len(found_items)]
                        try:
                            api.add_to_cart(item_id, 1)
                        except:
                            pass  # May fail if not available
                        
                elif op_choice < 9:
                    # 10% - DisplayCart
                    api.display_cart()
                    
                else:
                    # 10% - RemoveFromCart
                    cart = api.display_cart()
                    if cart:
                        try:
                            api.remove_from_cart(cart[0].item_id, 1)
                        except:
                            pass
                
                op_end = time.time()
                metrics.response_times.append(op_end - op_start)
                metrics.operations_completed += 1
                
            except Exception as e:
                metrics.errors += 1
        
        metrics.end_time = time.time()
        
        api.logout()
        client.disconnect()
        
    except Exception as e:
        print(f"Buyer {client_id} error: {e}")
        metrics.errors += 1
    
    return metrics


# =============================================================================
# Scenario Execution
# =============================================================================

def run_scenario(name: str, num_sellers: int, num_buyers: int, 
                 num_iterations: int, ops_per_client: int) -> ScenarioResults:
    """Run a complete scenario with multiple iterations."""
    
    results = ScenarioResults(
        scenario_name=name,
        num_sellers=num_sellers,
        num_buyers=num_buyers,
        num_iterations=num_iterations,
        ops_per_client=ops_per_client
    )
    
    print(f"\n{'#'*70}")
    print(f"Running: {name}")
    print(f"  {num_sellers} sellers, {num_buyers} buyers")
    print(f"  {num_iterations} iterations, {ops_per_client} ops/client")
    print(f"{'#'*70}")
    
    for iteration in range(num_iterations):
        print(f"\n  Iteration {iteration + 1}/{num_iterations}...", end=" ", flush=True)
        
        iteration_start = time.time()
        
        # Run all clients concurrently
        with ThreadPoolExecutor(max_workers=num_sellers + num_buyers) as executor:
            futures = []
            
            # Submit seller tasks
            for i in range(num_sellers):
                future = executor.submit(seller_workload, i, ops_per_client)
                futures.append(future)
            
            # Submit buyer tasks
            for i in range(num_buyers):
                future = executor.submit(buyer_workload, i + num_sellers, ops_per_client)
                futures.append(future)
            
            # Collect results
            for future in as_completed(futures):
                try:
                    metrics = future.result()
                    results.add_metrics(metrics)
                except Exception as e:
                    print(f"Task error: {e}")
        
        iteration_end = time.time()
        iteration_time = iteration_end - iteration_start
        results.iteration_times.append(iteration_time)
        
        print(f"done ({iteration_time:.2f}s)")
    
    return results


# =============================================================================
# Main
# =============================================================================

def main():
    print("\n" + "=" * 70)
    print("PERFORMANCE EVALUATION")
    print("=" * 70)
    print("\nThis will run three scenarios as required by the assignment:")
    print("  Scenario 1: 1 seller, 1 buyer")
    print("  Scenario 2: 10 sellers, 10 buyers")
    print("  Scenario 3: 100 sellers, 100 buyers")
    print(f"\nEach scenario: {CONFIG.num_iterations} iterations, "
          f"{CONFIG.operations_per_client} operations/client")
    
    # Verify servers are running
    import socket
    servers = [
        ("Buyer Server", CONFIG.buyer_server_host, CONFIG.buyer_server_port),
        ("Seller Server", CONFIG.seller_server_host, CONFIG.seller_server_port),
    ]
    
    for name, host, port in servers:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            sock.close()
        except:
            print(f"\nERROR: {name} not running on {host}:{port}")
            print("Please start all servers first.")
            return 1
    
    input("\nPress Enter to start performance tests...")
    
    all_results = []
    
    # Scenario 1: 1 seller, 1 buyer
    results1 = run_scenario(
        "Scenario 1: 1 Seller, 1 Buyer",
        num_sellers=1,
        num_buyers=1,
        num_iterations=CONFIG.num_iterations,
        ops_per_client=CONFIG.operations_per_client
    )
    all_results.append(results1)
    results1.print_summary()
    
    # Scenario 2: 10 sellers, 10 buyers
    results2 = run_scenario(
        "Scenario 2: 10 Sellers, 10 Buyers",
        num_sellers=10,
        num_buyers=10,
        num_iterations=CONFIG.num_iterations,
        ops_per_client=CONFIG.operations_per_client
    )
    all_results.append(results2)
    results2.print_summary()
    
    # Scenario 3: 100 sellers, 100 buyers
    results3 = run_scenario(
        "Scenario 3: 100 Sellers, 100 Buyers",
        num_sellers=100,
        num_buyers=100,
        num_iterations=CONFIG.num_iterations,
        ops_per_client=CONFIG.operations_per_client
    )
    all_results.append(results3)
    results3.print_summary()
    
    # Print comparison
    print("\n" + "=" * 70)
    print("PERFORMANCE COMPARISON")
    print("=" * 70)
    print(f"\n{'Scenario':<35} {'Avg Response (ms)':<20} {'Throughput (ops/s)':<20}")
    print("-" * 75)
    for r in all_results:
        print(f"{r.scenario_name:<35} {r.avg_response_time:<20.2f} {r.avg_throughput:<20.2f}")
    
    # Save results to file
    report = {
        "test_config": {
            "iterations": CONFIG.num_iterations,
            "operations_per_client": CONFIG.operations_per_client
        },
        "scenarios": []
    }
    
    for r in all_results:
        report["scenarios"].append({
            "name": r.scenario_name,
            "num_sellers": r.num_sellers,
            "num_buyers": r.num_buyers,
            "total_operations": r.total_operations,
            "total_errors": r.total_errors,
            "avg_response_time_ms": r.avg_response_time,
            "median_response_time_ms": r.median_response_time,
            "p95_response_time_ms": r.p95_response_time,
            "avg_throughput_ops_per_sec": r.avg_throughput
        })
    
    with open("performance_results.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nResults saved to: performance_results.json")
    
    # Print insights
    print("\n" + "=" * 70)
    print("ANALYSIS & INSIGHTS")
    print("=" * 70)
    
    print("""
Expected observations:

1. Response Time:
   - Scenario 1 should have the lowest response time (minimal contention)
   - Scenario 3 should have higher response times due to:
     * Thread contention on server
     * Lock contention in database storage
     * More concurrent connections

2. Throughput:
   - Scenario 1: Lower total throughput (only 2 clients)
   - Scenario 2: Higher throughput due to parallelism
   - Scenario 3: May show diminishing returns due to:
     * Server thread pool limits
     * Database lock contention
     * Context switching overhead

3. Scaling Analysis:
   - Linear scaling would mean 100x clients = 100x throughput
   - Sub-linear scaling is expected due to synchronization overhead
   - Response time increase indicates bottlenecks

Recommendations for improving performance:
- Use connection pooling for database connections
- Implement read-write locks instead of exclusive locks
- Consider sharding the product database by category
- Use async I/O instead of threads for better scalability
""")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())