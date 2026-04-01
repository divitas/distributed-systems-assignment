"""
Performance Benchmark Script for PA3

Measures:
  - Average response time per client function
  - Average server throughput
  
Scenarios:
  1. 1 seller + 1 buyer
  2. 10 sellers + 10 buyers
  3. 100 sellers + 100 buyers

Failure conditions:
  A. No failures
  B. 1 seller frontend + 1 buyer frontend replica fail
  C. 1 non-leader product DB replica fails
  D. Product DB leader fails

Usage:
  python benchmark.py --scenario 1 --condition A --runs 10 --ops 1000
"""

import requests
import time
import threading
import statistics
import argparse
import json
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class BenchmarkClient:
    """Automated client for benchmarking."""

    def __init__(self, client_type, client_id, replicas):
        self.client_type = client_type  # 'buyer' or 'seller'
        self.client_id = client_id
        self.replicas = replicas
        self.current_idx = client_id % len(replicas)
        self.session_id = None
        self.user_id = None
        self.response_times = {}
        self.errors = 0
        self.ops_completed = 0

    def _get_url(self):
        r = self.replicas[self.current_idx]
        return f"http://{r['host']}:{r['port']}"

    def _failover(self):
        self.current_idx = (self.current_idx + 1) % len(self.replicas)

    def _post(self, endpoint, data):
        for _ in range(len(self.replicas)):
            try:
                start = time.time()
                r = requests.post(f"{self._get_url()}{endpoint}", json=data, timeout=30)
                elapsed = time.time() - start
                return r.json(), elapsed
            except Exception:
                self._failover()
        self.errors += 1
        return None, 0

    def _get(self, endpoint, params=None):
        for _ in range(len(self.replicas)):
            try:
                start = time.time()
                r = requests.get(f"{self._get_url()}{endpoint}", params=params, timeout=30)
                elapsed = time.time() - start
                return r.json(), elapsed
            except Exception:
                self._failover()
        self.errors += 1
        return None, 0

    def _record(self, op_name, elapsed):
        if op_name not in self.response_times:
            self.response_times[op_name] = []
        self.response_times[op_name].append(elapsed)
        self.ops_completed += 1

    def setup(self):
        """Create account and login."""
        username = f"{self.client_type}_{self.client_id}_{random.randint(1000,9999)}"
        prefix = self.client_type

        resp, _ = self._post(f"/{prefix}/create_account", {
            'username': username,
            'password': 'bench123',
            f'{prefix}_name': f'Bench {self.client_type} {self.client_id}',
            **({"seller_name": f"Bench Seller {self.client_id}"} if prefix == "seller"
               else {"buyer_name": f"Bench Buyer {self.client_id}"})
        })

        resp, _ = self._post(f"/{prefix}/login", {
            'username': username, 'password': 'bench123'
        })
        if resp and resp.get('status') == 'success':
            self.session_id = resp['data']['session_id']
            self.user_id = resp['data'].get('seller_id') or resp['data'].get('buyer_id')
            return True
        return False

    def run_seller_ops(self, num_ops):
        """Run a mix of seller operations."""
        item_ids = []
        for i in range(num_ops):
            op_choice = random.randint(1, 5)

            if op_choice <= 2 or not item_ids:
                # Register item
                resp, elapsed = self._post("/seller/register_item", {
                    'session_id': self.session_id,
                    'name': f'BenchItem_{self.client_id}_{i}',
                    'category': random.randint(1, 8),
                    'keywords': ['bench', 'test'],
                    'condition': 'New',
                    'price': round(random.uniform(1, 100), 2),
                    'quantity': random.randint(10, 1000)
                })
                self._record('register_item', elapsed)
                if resp and resp.get('status') == 'success':
                    item_ids.append(resp['data']['item_id'])

            elif op_choice == 3 and item_ids:
                # Change price
                resp, elapsed = self._post("/seller/change_price", {
                    'session_id': self.session_id,
                    'item_id': random.choice(item_ids),
                    'new_price': round(random.uniform(1, 200), 2)
                })
                self._record('change_price', elapsed)

            elif op_choice == 4 and item_ids:
                # Update units
                resp, elapsed = self._post("/seller/update_units", {
                    'session_id': self.session_id,
                    'item_id': random.choice(item_ids),
                    'quantity': 1
                })
                self._record('update_units', elapsed)

            elif op_choice == 5:
                # Display items
                resp, elapsed = self._get("/seller/display_items", {
                    'session_id': self.session_id
                })
                self._record('display_items', elapsed)

    def run_buyer_ops(self, num_ops):
        """Run a mix of buyer operations."""
        for i in range(num_ops):
            op_choice = random.randint(1, 5)

            if op_choice <= 2:
                # Search items
                resp, elapsed = self._post("/buyer/search_items", {
                    'session_id': self.session_id,
                    'category': random.randint(1, 8),
                    'keywords': ['bench']
                })
                self._record('search_items', elapsed)

            elif op_choice == 3:
                # Add to cart
                resp, elapsed = self._post("/buyer/add_to_cart", {
                    'session_id': self.session_id,
                    'item_id': f'{random.randint(1,8)}-1',
                    'quantity': 1
                })
                self._record('add_to_cart', elapsed)

            elif op_choice == 4:
                # Display cart
                resp, elapsed = self._get("/buyer/display_cart", {
                    'session_id': self.session_id
                })
                self._record('display_cart', elapsed)

            elif op_choice == 5:
                # Get seller rating
                resp, elapsed = self._get("/buyer/get_seller_rating", {
                    'session_id': self.session_id,
                    'seller_id': '1'
                })
                self._record('get_seller_rating', elapsed)


def run_benchmark(num_sellers, num_buyers, ops_per_client, num_runs):
    """Run the benchmark with the given parameters."""

    all_results = []

    for run in range(num_runs):
        print(f"\n--- Run {run + 1}/{num_runs} ---")

        seller_clients = []
        buyer_clients = []

        # Create seller clients
        for i in range(num_sellers):
            c = BenchmarkClient('seller', i, config.SELLER_FRONTEND_REPLICAS)
            if c.setup():
                seller_clients.append(c)

        # Create buyer clients
        for i in range(num_buyers):
            c = BenchmarkClient('buyer', i, config.BUYER_FRONTEND_REPLICAS)
            if c.setup():
                buyer_clients.append(c)

        print(f"  Setup: {len(seller_clients)} sellers, {len(buyer_clients)} buyers")

        start_time = time.time()
        threads = []

        for c in seller_clients:
            t = threading.Thread(target=c.run_seller_ops, args=(ops_per_client,))
            threads.append(t)

        for c in buyer_clients:
            t = threading.Thread(target=c.run_buyer_ops, args=(ops_per_client,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_time = time.time() - start_time
        total_ops = sum(c.ops_completed for c in seller_clients + buyer_clients)
        throughput = total_ops / total_time if total_time > 0 else 0

        # Aggregate response times by operation
        combined = {}
        for c in seller_clients + buyer_clients:
            for op, times in c.response_times.items():
                if op not in combined:
                    combined[op] = []
                combined[op].extend(times)

        run_result = {
            'run': run + 1,
            'total_ops': total_ops,
            'total_time': total_time,
            'throughput': throughput,
            'response_times': {
                op: {
                    'avg': statistics.mean(times),
                    'p50': statistics.median(times),
                    'p95': sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0],
                    'p99': sorted(times)[int(len(times) * 0.99)] if len(times) > 1 else times[0],
                    'count': len(times),
                }
                for op, times in combined.items()
            },
            'errors': sum(c.errors for c in seller_clients + buyer_clients),
        }
        all_results.append(run_result)

        print(f"  Throughput: {throughput:.1f} ops/sec, Total time: {total_time:.2f}s")
        for op, stats in run_result['response_times'].items():
            print(f"    {op}: avg={stats['avg']*1000:.1f}ms, p95={stats['p95']*1000:.1f}ms ({stats['count']} calls)")

    # Summary across runs
    print("\n" + "=" * 60)
    print("SUMMARY ACROSS ALL RUNS")
    print("=" * 60)

    avg_throughput = statistics.mean([r['throughput'] for r in all_results])
    print(f"Average throughput: {avg_throughput:.1f} ops/sec")

    # Average response time per operation
    all_ops = set()
    for r in all_results:
        all_ops.update(r['response_times'].keys())

    for op in sorted(all_ops):
        avgs = [r['response_times'][op]['avg'] for r in all_results if op in r['response_times']]
        if avgs:
            print(f"  {op}: avg response time = {statistics.mean(avgs)*1000:.1f}ms")

    return all_results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PA3 Performance Benchmark')
    parser.add_argument('--scenario', type=int, choices=[1, 2, 3], required=True,
                        help='1=1+1, 2=10+10, 3=100+100 clients')
    parser.add_argument('--runs', type=int, default=10, help='Number of runs')
    parser.add_argument('--ops', type=int, default=1000, help='Operations per client per run')
    args = parser.parse_args()

    scenarios = {1: (1, 1), 2: (10, 10), 3: (100, 100)}
    num_sellers, num_buyers = scenarios[args.scenario]

    print(f"Benchmark: Scenario {args.scenario} ({num_sellers} sellers, {num_buyers} buyers)")
    print(f"Runs: {args.runs}, Ops per client: {args.ops}")

    results = run_benchmark(num_sellers, num_buyers, args.ops, args.runs)

    # Save results
    output_file = f"benchmark_scenario{args.scenario}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")
