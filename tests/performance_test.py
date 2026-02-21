"""
Performance Test for PA2 - Online Marketplace Distributed System
Measures average response time and average server throughput for:
  - Scenario 1: 1 seller, 1 buyer
  - Scenario 2: 10 sellers, 10 buyers
  - Scenario 3: 100 sellers, 100 buyers

Usage:
  python3 performance_test.py --scenario 1
  python3 performance_test.py --scenario 2
  python3 performance_test.py --scenario 3
  python3 performance_test.py --all          # Run all scenarios
"""

import requests
import time
import threading
import random
import argparse
import json
import sys
import os
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean, stdev

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ========== LOGGING SETUP ==========
LOG_FILE = f"performance_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("perf_test")

# ========== CONFIGURATION ==========
# Update these to match your config.py
BUYER_FRONTEND = "http://10.224.79.148:6001"
SELLER_FRONTEND = "http://10.224.79.250:6002"

ITEM_CATEGORIES = {1: "Electronics", 2: "Books", 3: "Clothing", 4: "Home", 5: "Sports", 6: "Toys", 7: "Food", 8: "Other"}
SAMPLE_KEYWORDS = ["laptop", "phone", "book", "shirt", "ball", "toy", "snack", "chair", "camera", "watch"]

NUM_RUNS = 10
OPS_PER_RUN = 1000

# ========== HELPER FUNCTIONS ==========

def timed_request(method, url, **kwargs):
    """Make a request and return (response, elapsed_time_seconds)"""
    start = time.perf_counter()
    try:
        if method == "GET":
            r = requests.get(url, **kwargs, timeout=30)
        else:
            r = requests.post(url, **kwargs, timeout=30)
        elapsed = time.perf_counter() - start
        return r.json(), elapsed
    except Exception as e:
        elapsed = time.perf_counter() - start
        return None, elapsed


# ========== SELLER OPERATIONS ==========

class SellerWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.username = f"perf_seller_{worker_id}_{int(time.time())}"
        self.password = "testpass123"
        self.seller_name = f"Test Seller {worker_id}"
        self.session_id = None
        self.seller_id = None
        self.item_ids = []

    def create_account(self):
        resp, elapsed = timed_request("POST", f"{SELLER_FRONTEND}/seller/create_account", json={
            "username": self.username, "password": self.password, "seller_name": self.seller_name
        })
        if resp and resp.get("status") == "success":
            self.seller_id = resp["data"]["seller_id"]
        return elapsed

    def login(self):
        resp, elapsed = timed_request("POST", f"{SELLER_FRONTEND}/seller/login", json={
            "username": self.username, "password": self.password
        })
        if resp and resp.get("status") == "success":
            self.session_id = resp["data"]["session_id"]
            self.seller_id = resp["data"]["seller_id"]
        return elapsed

    def logout(self):
        resp, elapsed = timed_request("POST", f"{SELLER_FRONTEND}/seller/logout", json={
            "session_id": self.session_id
        })
        self.session_id = None
        return elapsed

    def register_item(self):
        category = random.randint(1, 8)
        item_name = f"TestItem_{self.worker_id}_{random.randint(1000, 9999)}"
        resp, elapsed = timed_request("POST", f"{SELLER_FRONTEND}/seller/register_item", json={
            "session_id": self.session_id,
            "item_name": item_name,
            "category": category,
            "keywords": random.sample(SAMPLE_KEYWORDS, min(3, len(SAMPLE_KEYWORDS))),
            "condition": random.choice(["new", "used"]),
            "price": round(random.uniform(5.0, 500.0), 2),
            "quantity": random.randint(1, 100)
        })
        if resp and resp.get("status") == "success":
            item_id = resp.get("data", {}).get("item_id")
            if item_id:
                self.item_ids.append(str(item_id))
        return elapsed

    def change_price(self):
        if not self.item_ids:
            return 0
        item_id = random.choice(self.item_ids)
        resp, elapsed = timed_request("POST", f"{SELLER_FRONTEND}/seller/change_price", json={
            "session_id": self.session_id,
            "item_id": item_id,
            "new_price": round(random.uniform(5.0, 500.0), 2)
        })
        return elapsed

    def display_items(self):
        resp, elapsed = timed_request("GET", f"{SELLER_FRONTEND}/seller/display_items", params={
            "session_id": self.session_id
        })
        return elapsed

    def get_rating(self):
        resp, elapsed = timed_request("GET", f"{SELLER_FRONTEND}/seller/get_rating", params={
            "session_id": self.session_id
        })
        return elapsed

    def run_operations(self, num_ops):
        """Run a mix of seller operations and return list of response times"""
        response_times = []

        # Setup: create account and login
        self.create_account()
        self.login()

        if not self.session_id:
            logger.info(f"  [Seller {self.worker_id}] Failed to login, skipping")
            return response_times

        # Register a few items first so we have items to work with
        for _ in range(min(5, num_ops)):
            elapsed = self.register_item()
            response_times.append(elapsed)

        # Run remaining operations as a random mix
        remaining = num_ops - len(response_times)
        operations = [
            self.register_item,
            self.change_price,
            self.display_items,
            self.get_rating,
        ]

        for _ in range(remaining):
            op = random.choice(operations)
            try:
                elapsed = op()
                response_times.append(elapsed)
            except Exception as e:
                pass

        # Cleanup
        try:
            self.logout()
        except:
            pass

        return response_times


# ========== BUYER OPERATIONS ==========

class BuyerWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.username = f"perf_buyer_{worker_id}_{int(time.time())}"
        self.password = "testpass123"
        self.buyer_name = f"Test Buyer {worker_id}"
        self.session_id = None
        self.buyer_id = None
        self.found_items = []

    def create_account(self):
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/create_account", json={
            "username": self.username, "password": self.password, "buyer_name": self.buyer_name
        })
        if resp and resp.get("status") == "success":
            self.buyer_id = resp["data"]["buyer_id"]
        return elapsed

    def login(self):
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/login", json={
            "username": self.username, "password": self.password
        })
        if resp and resp.get("status") == "success":
            self.session_id = resp["data"]["session_id"]
            self.buyer_id = resp["data"]["buyer_id"]
        return elapsed

    def logout(self):
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/logout", json={
            "session_id": self.session_id
        })
        self.session_id = None
        return elapsed

    def search_items(self):
        category = random.randint(1, 8)
        keywords = random.sample(SAMPLE_KEYWORDS, min(2, len(SAMPLE_KEYWORDS)))
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/search_items", json={
            "session_id": self.session_id,
            "category": category,
            "keywords": keywords
        })
        if resp and resp.get("status") == "success":
            items = resp.get("data", {}).get("items", [])
            for item in items:
                item_id = item.get("item_id")
                if item_id and str(item_id) not in self.found_items:
                    self.found_items.append(str(item_id))
        return elapsed

    def get_item(self):
        if not self.found_items:
            return self.search_items()
        item_id = random.choice(self.found_items)
        resp, elapsed = timed_request("GET", f"{BUYER_FRONTEND}/buyer/get_item", params={
            "session_id": self.session_id, "item_id": item_id
        })
        return elapsed

    def add_to_cart(self):
        if not self.found_items:
            return self.search_items()
        item_id = random.choice(self.found_items)
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/add_to_cart", json={
            "session_id": self.session_id,
            "item_id": item_id,
            "quantity": random.randint(1, 3)
        })
        return elapsed

    def remove_from_cart(self):
        item_id = random.choice(self.found_items) if self.found_items else "1"
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/remove_from_cart", json={
            "session_id": self.session_id,
            "item_id": item_id,
            "quantity": 1
        })
        return elapsed

    def display_cart(self):
        resp, elapsed = timed_request("GET", f"{BUYER_FRONTEND}/buyer/display_cart", params={
            "session_id": self.session_id
        })
        return elapsed

    def save_cart(self):
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/save_cart", json={
            "session_id": self.session_id
        })
        return elapsed

    def clear_cart(self):
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/clear_cart", json={
            "session_id": self.session_id
        })
        return elapsed

    def get_seller_rating(self):
        resp, elapsed = timed_request("GET", f"{BUYER_FRONTEND}/buyer/get_seller_rating", params={
            "session_id": self.session_id, "seller_id": "1"
        })
        return elapsed

    def get_purchases(self):
        resp, elapsed = timed_request("GET", f"{BUYER_FRONTEND}/buyer/get_purchases", params={
            "session_id": self.session_id
        })
        return elapsed

    def make_purchase(self):
        if not self.found_items:
            return self.search_items()
        item_id = random.choice(self.found_items)
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/make_purchase", json={
            "session_id": self.session_id,
            "item_id": item_id,
            "quantity": 1,
            "card_name": "Test User",
            "card_number": "4111111111111111",
            "expiration_date": "12/25",
            "security_code": "123"
        })
        return elapsed

    def provide_feedback(self):
        if not self.found_items:
            return self.search_items()
        item_id = random.choice(self.found_items)
        resp, elapsed = timed_request("POST", f"{BUYER_FRONTEND}/buyer/provide_feedback", json={
            "session_id": self.session_id,
            "item_id": item_id,
            "seller_id": "1",
            "thumbs": random.choice([0, 1])
        })
        return elapsed

    def run_operations(self, num_ops):
        """Run a mix of buyer operations and return list of response times"""
        response_times = []

        # Setup: create account and login
        self.create_account()
        self.login()

        if not self.session_id:
            logger.info(f"  [Buyer {self.worker_id}] Failed to login, skipping")
            return response_times

        # Search first to populate found_items
        for _ in range(min(5, num_ops)):
            elapsed = self.search_items()
            response_times.append(elapsed)

        # Run remaining operations as a random mix
        remaining = num_ops - len(response_times)
        operations = [
            self.search_items,
            self.get_item,
            self.add_to_cart,
            self.remove_from_cart,
            self.display_cart,
            self.save_cart,
            self.get_seller_rating,
            self.get_purchases,
            self.make_purchase,
            self.provide_feedback,
        ]

        for _ in range(remaining):
            op = random.choice(operations)
            try:
                elapsed = op()
                response_times.append(elapsed)
            except Exception as e:
                pass

        # Cleanup
        try:
            self.logout()
        except:
            pass

        return response_times


# ========== TEST RUNNER ==========

def run_single_test(num_sellers, num_buyers, ops_per_client):
    """
    Run one test with given number of sellers and buyers.
    Each client performs ops_per_client operations.
    Returns (all_response_times, total_elapsed_time, total_ops_completed)
    """
    all_response_times = []
    lock = threading.Lock()

    def seller_task(worker_id):
        seller = SellerWorker(worker_id)
        times = seller.run_operations(ops_per_client)
        with lock:
            all_response_times.extend(times)
        return len(times)

    def buyer_task(worker_id):
        buyer = BuyerWorker(worker_id)
        times = buyer.run_operations(ops_per_client)
        with lock:
            all_response_times.extend(times)
        return len(times)

    total_ops = 0
    start_time = time.perf_counter()

    max_workers = num_sellers + num_buyers
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []

        for i in range(num_sellers):
            futures.append(executor.submit(seller_task, i))
        for i in range(num_buyers):
            futures.append(executor.submit(buyer_task, i))

        for future in as_completed(futures):
            try:
                ops = future.result()
                total_ops += ops
            except Exception as e:
                logger.info(f"  Worker error: {e}")

    total_time = time.perf_counter() - start_time

    return all_response_times, total_time, total_ops


def run_scenario(scenario_num, num_sellers, num_buyers):
    """Run a scenario with NUM_RUNS repetitions and report metrics"""
    # Each client does OPS_PER_RUN operations total
    # Split evenly among clients
    total_clients = num_sellers + num_buyers
    ops_per_client = OPS_PER_RUN // total_clients
    if ops_per_client < 10:
        ops_per_client = 10

    logger.info(f"\n{'='*70}")
    logger.info(f"SCENARIO {scenario_num}: {num_sellers} seller(s), {num_buyers} buyer(s)")
    logger.info(f"  Runs: {NUM_RUNS}")
    logger.info(f"  Operations per client per run: {ops_per_client}")
    logger.info(f"  Total operations per run: ~{ops_per_client * total_clients}")
    logger.info(f"{'='*70}")

    run_avg_response_times = []
    run_throughputs = []

    for run in range(1, NUM_RUNS + 1):
        logger.info(f"\n  --- Run {run}/{NUM_RUNS} ---")

        response_times, total_time, total_ops = run_single_test(
            num_sellers, num_buyers, ops_per_client
        )

        if response_times:
            avg_rt = mean(response_times)
            throughput = total_ops / total_time

            run_avg_response_times.append(avg_rt)
            run_throughputs.append(throughput)

            logger.info(f"  Completed {total_ops} ops in {total_time:.2f}s")
            logger.info(f"  Avg response time: {avg_rt*1000:.2f} ms")
            logger.info(f"  Throughput: {throughput:.2f} ops/sec")
        else:
            logger.info(f"  No operations completed!")

    # Final averages across all runs
    logger.info(f"\n{'='*70}")
    logger.info(f"SCENARIO {scenario_num} RESULTS ({num_sellers} sellers, {num_buyers} buyers)")
    logger.info(f"{'='*70}")

    if run_avg_response_times:
        overall_avg_rt = mean(run_avg_response_times)
        overall_avg_throughput = mean(run_throughputs)

        rt_std = stdev(run_avg_response_times) if len(run_avg_response_times) > 1 else 0
        tp_std = stdev(run_throughputs) if len(run_throughputs) > 1 else 0

        logger.info(f"  Average Response Time:  {overall_avg_rt*1000:.2f} ms (± {rt_std*1000:.2f} ms)")
        logger.info(f"  Average Throughput:     {overall_avg_throughput:.2f} ops/sec (± {tp_std:.2f} ops/sec)")
        logger.info(f"  Min Response Time:      {min(run_avg_response_times)*1000:.2f} ms")
        logger.info(f"  Max Response Time:      {max(run_avg_response_times)*1000:.2f} ms")
        logger.info(f"  Min Throughput:         {min(run_throughputs):.2f} ops/sec")
        logger.info(f"  Max Throughput:         {max(run_throughputs):.2f} ops/sec")

        return {
            "scenario": scenario_num,
            "sellers": num_sellers,
            "buyers": num_buyers,
            "avg_response_time_ms": round(overall_avg_rt * 1000, 2),
            "response_time_std_ms": round(rt_std * 1000, 2),
            "avg_throughput_ops_sec": round(overall_avg_throughput, 2),
            "throughput_std_ops_sec": round(tp_std, 2),
        }
    else:
        logger.info("  No data collected!")
        return None


def print_comparison(results):
    """Print a comparison table of all scenarios"""
    logger.info(f"\n{'='*70}")
    logger.info("PERFORMANCE COMPARISON ACROSS SCENARIOS")
    logger.info(f"{'='*70}")
    logger.info(f"{'Scenario':<12} {'Sellers':<10} {'Buyers':<10} {'Avg RT (ms)':<15} {'Avg Throughput':<20}")
    logger.info(f"{'-'*70}")
    for r in results:
        if r:
            logger.info(f"  {r['scenario']:<10} {r['sellers']:<10} {r['buyers']:<10} "
                  f"{r['avg_response_time_ms']:<15} {r['avg_throughput_ops_sec']:<20}")
    logger.info(f"{'='*70}")


def main():
    global BUYER_FRONTEND, SELLER_FRONTEND, NUM_RUNS, OPS_PER_RUN

    parser = argparse.ArgumentParser(description="Performance Test for PA2")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3],
                        help="Run specific scenario (1, 2, or 3)")
    parser.add_argument("--all", action="store_true",
                        help="Run all three scenarios")
    parser.add_argument("--buyer-url", type=str, default=BUYER_FRONTEND,
                        help=f"Buyer frontend URL (default: {BUYER_FRONTEND})")
    parser.add_argument("--seller-url", type=str, default=SELLER_FRONTEND,
                        help=f"Seller frontend URL (default: {SELLER_FRONTEND})")
    parser.add_argument("--runs", type=int, default=NUM_RUNS,
                        help=f"Number of runs per scenario (default: {NUM_RUNS})")
    parser.add_argument("--ops", type=int, default=OPS_PER_RUN,
                        help=f"Total operations per run (default: {OPS_PER_RUN})")

    args = parser.parse_args()
    BUYER_FRONTEND = args.buyer_url
    SELLER_FRONTEND = args.seller_url
    NUM_RUNS = args.runs
    OPS_PER_RUN = args.ops

    logger.info("\n" + "=" * 70)
    logger.info("PA2 PERFORMANCE TEST")
    logger.info("=" * 70)
    logger.info(f"Buyer Frontend:  {BUYER_FRONTEND}")
    logger.info(f"Seller Frontend: {SELLER_FRONTEND}")
    logger.info(f"Runs per scenario: {NUM_RUNS}")
    logger.info(f"Operations per run: {OPS_PER_RUN}")

    # Quick connectivity check
    logger.info("\nChecking connectivity...")
    try:
        requests.get(f"{BUYER_FRONTEND}/docs", timeout=5)
        logger.info(f"  ✓ Buyer frontend reachable")
    except:
        logger.info(f"  ✗ Cannot reach buyer frontend at {BUYER_FRONTEND}")
        logger.info("  Make sure the buyer server is running on VM3")
        return

    try:
        requests.get(f"{SELLER_FRONTEND}/docs", timeout=5)
        logger.info(f"  ✓ Seller frontend reachable")
    except:
        logger.info(f"  ✗ Cannot reach seller frontend at {SELLER_FRONTEND}")
        logger.info("  Make sure the seller server is running on VM4")
        return

    results = []

    scenarios = {
        1: (1, 1),
        2: (10, 10),
        3: (100, 100),
    }

    if args.all:
        for s in [1, 2, 3]:
            num_sellers, num_buyers = scenarios[s]
            result = run_scenario(s, num_sellers, num_buyers)
            results.append(result)
        print_comparison(results)
    elif args.scenario:
        num_sellers, num_buyers = scenarios[args.scenario]
        result = run_scenario(args.scenario, num_sellers, num_buyers)
        results.append(result)
    else:
        logger.info("\nPlease specify --scenario 1/2/3 or --all")
        parser.print_help()
        return

    # Save results to JSON
    output_file = f"performance_results_{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump([r for r in results if r], f, indent=2)
    logger.info(f"\nResults saved to {output_file}")
    logger.info(f"Full log saved to {LOG_FILE}")


if __name__ == "__main__":
    main()