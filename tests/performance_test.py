#!/usr/bin/env python3
"""
PA3 Performance Test Script
============================
Measures per scenario per mode:
  - One average response time (ms) across ALL API calls
  - One throughput number (ops/sec)

Scenarios:
  1. 1 seller + 1 buyer
  2. 10 sellers + 10 buyers concurrently
  3. 100 sellers + 100 buyers concurrently

Modes:
  normal                  - All replicas running
  frontend_fail           - One seller + one buyer frontend killed
  product_nonleader_fail  - One non-leader Product DB replica killed
  product_leader_fail     - Product DB leader killed (wait for re-election)

Usage:
  python3 performance_test.py --all --mode normal
  python3 performance_test.py --scenario 1 --mode normal
  python3 performance_test.py --all --mode frontend_fail
  python3 performance_test.py --all --mode normal --runs 3 --ops 100  (quick test)
"""

import argparse
import os
import sys
import time
import statistics
import csv
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from requests.exceptions import ConnectionError, Timeout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# =============================================================================
# Config
# =============================================================================

BUYER_URLS = [f"http://{r['host']}:{r['port']}" for r in config.BUYER_FRONTEND_REPLICAS]
SELLER_URLS = [f"http://{r['host']}:{r['port']}" for r in config.SELLER_FRONTEND_REPLICAS]

TIMEOUT = 10
TIMING_RUNS = 10
THROUGHPUT_OPS = 1000


# =============================================================================
# HTTP helpers
# =============================================================================

def post(replicas, endpoint, data):
    for url in replicas:
        try:
            r = requests.post(f"{url}{endpoint}", json=data, timeout=TIMEOUT)
            return r.json(), r.elapsed.total_seconds()
        except (ConnectionError, Timeout):
            continue
        except Exception:
            continue
    return None, 0


def get(replicas, endpoint, params):
    for url in replicas:
        try:
            r = requests.get(f"{url}{endpoint}", params=params, timeout=TIMEOUT)
            return r.json(), r.elapsed.total_seconds()
        except (ConnectionError, Timeout):
            continue
        except Exception:
            continue
    return None, 0


# =============================================================================
# Full workflow for one seller+buyer pair — returns list of elapsed times
# =============================================================================

def run_workflow(idx, run_id, seller_urls, buyer_urls):
    times = []
    ts = int(time.time() * 1000)

    s_user = f"ps_{idx}_{run_id}_{ts}"
    b_user = f"pb_{idx}_{run_id}_{ts}"

    # Seller: create + login
    resp, t = post(seller_urls, "/seller/create_account",
                   {"username": s_user, "password": "p", "seller_name": f"S{idx}"})
    times.append(t)
    if not resp or resp.get("status") != "success":
        return times

    resp, t = post(seller_urls, "/seller/login", {"username": s_user, "password": "p"})
    times.append(t)
    if not resp or resp.get("status") != "success":
        return times
    s_session = resp["data"]["session_id"]
    s_id = resp["data"]["seller_id"]

    # Seller: register item
    resp, t = post(seller_urls, "/seller/register_item", {
        "session_id": s_session, "name": f"Item{idx}", "category": (idx % 8) + 1,
        "keywords": ["test"], "condition": "New", "price": 9.99, "quantity": 500
    })
    times.append(t)
    item_id = resp["data"].get("item_id") if resp and resp.get("status") == "success" else None

    # Seller: change price
    if item_id:
        _, t = post(seller_urls, "/seller/change_price",
                    {"session_id": s_session, "item_id": item_id, "new_price": 15.0})
        times.append(t)

    # Seller: display items
    _, t = get(seller_urls, "/seller/display_items", {"session_id": s_session})
    times.append(t)

    # Seller: get rating
    _, t = get(seller_urls, "/seller/get_rating", {"session_id": s_session})
    times.append(t)

    # Buyer: create + login
    resp, t = post(buyer_urls, "/buyer/create_account",
                   {"username": b_user, "password": "p", "buyer_name": f"B{idx}"})
    times.append(t)
    if not resp or resp.get("status") != "success":
        return times

    resp, t = post(buyer_urls, "/buyer/login", {"username": b_user, "password": "p"})
    times.append(t)
    if not resp or resp.get("status") != "success":
        return times
    b_session = resp["data"]["session_id"]

    # Buyer: search
    _, t = post(buyer_urls, "/buyer/search_items",
                {"session_id": b_session, "category": (idx % 8) + 1, "keywords": ["test"]})
    times.append(t)

    if item_id:
        # Buyer: get item
        _, t = get(buyer_urls, "/buyer/get_item", {"session_id": b_session, "item_id": item_id})
        times.append(t)

        # Buyer: add to cart
        _, t = post(buyer_urls, "/buyer/add_to_cart",
                    {"session_id": b_session, "item_id": item_id, "quantity": 1})
        times.append(t)

        # Buyer: display cart
        _, t = get(buyer_urls, "/buyer/display_cart", {"session_id": b_session})
        times.append(t)

        # Buyer: save cart
        _, t = post(buyer_urls, "/buyer/save_cart", {"session_id": b_session})
        times.append(t)

        # Buyer: make purchase
        _, t = post(buyer_urls, "/buyer/make_purchase", {
            "session_id": b_session, "item_id": item_id, "quantity": 1,
            "card_name": "Test", "card_number": "1234567812345678",
            "expiration_date": "12/28", "security_code": "123"
        })
        times.append(t)

        # Buyer: get purchases
        _, t = get(buyer_urls, "/buyer/get_purchases", {"session_id": b_session})
        times.append(t)

        # Buyer: provide feedback
        _, t = post(buyer_urls, "/buyer/provide_feedback",
                    {"session_id": b_session, "item_id": item_id,
                     "seller_id": str(s_id), "thumbs": 1})
        times.append(t)

        # Buyer: get seller rating
        _, t = get(buyer_urls, "/buyer/get_seller_rating",
                   {"session_id": b_session, "seller_id": str(s_id)})
        times.append(t)

        # Buyer: remove from cart
        _, t = post(buyer_urls, "/buyer/remove_from_cart",
                    {"session_id": b_session, "item_id": item_id, "quantity": 1})
        times.append(t)

        # Buyer: clear cart
        _, t = post(buyer_urls, "/buyer/clear_cart", {"session_id": b_session})
        times.append(t)

    # Logout
    _, t = post(seller_urls, "/seller/logout", {"session_id": s_session})
    times.append(t)
    _, t = post(buyer_urls, "/buyer/logout", {"session_id": b_session})
    times.append(t)

    return times


# =============================================================================
# Throughput worker
# =============================================================================

def run_throughput_worker(idx, num_ops, seller_urls, buyer_urls):
    ts = int(time.time() * 1000)
    s_user = f"tp_s_{idx}_{ts}"
    b_user = f"tp_b_{idx}_{ts}"

    resp, _ = post(seller_urls, "/seller/create_account",
                   {"username": s_user, "password": "p", "seller_name": f"TP{idx}"})
    if not resp or resp.get("status") != "success":
        return 0

    resp, _ = post(seller_urls, "/seller/login", {"username": s_user, "password": "p"})
    if not resp or resp.get("status") != "success":
        return 0
    s_session = resp["data"]["session_id"]
    s_id = resp["data"]["seller_id"]

    resp, _ = post(buyer_urls, "/buyer/create_account",
                   {"username": b_user, "password": "p", "buyer_name": f"TP{idx}"})
    if not resp or resp.get("status") != "success":
        return 0

    resp, _ = post(buyer_urls, "/buyer/login", {"username": b_user, "password": "p"})
    if not resp or resp.get("status") != "success":
        return 0
    b_session = resp["data"]["session_id"]

    item_ids = []
    for i in range(3):
        resp, _ = post(seller_urls, "/seller/register_item", {
            "session_id": s_session, "name": f"TPItem{idx}_{i}",
            "category": (i % 8) + 1, "keywords": ["tp"], "condition": "New",
            "price": 5.0, "quantity": 50000
        })
        if resp and resp.get("status") == "success":
            item_ids.append(resp["data"]["item_id"])

    if not item_ids:
        return 0

    completed = 0
    for c in range(num_ops):
        try:
            item_id = item_ids[c % len(item_ids)]
            op = c % 7
            if op == 0:
                get(seller_urls, "/seller/display_items", {"session_id": s_session})
            elif op == 1:
                post(buyer_urls, "/buyer/search_items",
                     {"session_id": b_session, "category": (c % 8) + 1, "keywords": []})
            elif op == 2:
                get(buyer_urls, "/buyer/get_item", {"session_id": b_session, "item_id": item_id})
            elif op == 3:
                post(buyer_urls, "/buyer/add_to_cart",
                     {"session_id": b_session, "item_id": item_id, "quantity": 1})
            elif op == 4:
                post(buyer_urls, "/buyer/make_purchase", {
                    "session_id": b_session, "item_id": item_id, "quantity": 1,
                    "card_name": "T", "card_number": "1234567812345678",
                    "expiration_date": "12/28", "security_code": "123"
                })
            elif op == 5:
                get(buyer_urls, "/buyer/get_purchases", {"session_id": b_session})
            elif op == 6:
                get(seller_urls, "/seller/get_rating", {"session_id": s_session})
            completed += 1
        except Exception:
            continue

    try:
        post(seller_urls, "/seller/logout", {"session_id": s_session})
        post(buyer_urls, "/buyer/logout", {"session_id": b_session})
    except Exception:
        pass

    return completed


# =============================================================================
# Scenario runner
# =============================================================================

def run_scenario(num_pairs, mode, seller_urls, buyer_urls):
    label = f"{num_pairs}s+{num_pairs}b"
    print(f"\n{'='*60}")
    print(f"  Scenario: {label} | Mode: {mode}")
    print(f"{'='*60}")

    # ---- Response Time ----
    print(f"\n  [Response Time] {TIMING_RUNS} iterations...")
    all_times = []

    for run in range(TIMING_RUNS):
        sys.stdout.write(f"\r  Run {run + 1}/{TIMING_RUNS}...")
        sys.stdout.flush()

        if num_pairs == 1:
            times = run_workflow(0, run, seller_urls, buyer_urls)
            all_times.extend(times)
        else:
            with ThreadPoolExecutor(max_workers=min(num_pairs, 50)) as pool:
                futs = [pool.submit(run_workflow, i, run * 1000 + i, seller_urls, buyer_urls)
                        for i in range(num_pairs)]
                for f in as_completed(futs):
                    try:
                        all_times.extend(f.result())
                    except Exception:
                        pass
    print()

    valid = [t for t in all_times if t > 0]
    avg_ms = statistics.mean(valid) * 1000 if valid else 0
    print(f"  Avg Response Time: {avg_ms:.2f} ms ({len(valid)} calls)")

    # ---- Throughput ----
    print(f"\n  [Throughput] {THROUGHPUT_OPS} ops target...")

    if num_pairs == 1:
        start = time.time()
        completed = run_throughput_worker(0, THROUGHPUT_OPS, seller_urls, buyer_urls)
        elapsed = time.time() - start
    else:
        ops_per_worker = max(10, THROUGHPUT_OPS // num_pairs)
        start = time.time()
        completed = 0
        with ThreadPoolExecutor(max_workers=min(num_pairs, 50)) as pool:
            futs = [pool.submit(run_throughput_worker, i, ops_per_worker, seller_urls, buyer_urls)
                    for i in range(num_pairs)]
            for f in as_completed(futs):
                try:
                    completed += f.result()
                except Exception:
                    pass
        elapsed = time.time() - start

    throughput = completed / elapsed if elapsed > 0 else 0
    print(f"  Throughput: {throughput:.2f} ops/sec ({completed} ops in {elapsed:.1f}s)")

    return {
        "scenario": label,
        "mode": mode,
        "avg_response_time_ms": round(avg_ms, 2),
        "throughput_ops_per_sec": round(throughput, 2),
        "total_api_calls": len(valid),
        "throughput_total_ops": completed,
        "throughput_elapsed_sec": round(elapsed, 2),
    }


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="PA3 Performance Test")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3],
                        help="1=1+1, 2=10+10, 3=100+100")
    parser.add_argument("--mode", type=str, default="normal",
                        choices=["normal", "frontend_fail", "product_nonleader_fail", "product_leader_fail"])
    parser.add_argument("--all", action="store_true", help="Run all 3 scenarios")
    parser.add_argument("--runs", type=int, default=10, help="Timing iterations (default 10)")
    parser.add_argument("--ops", type=int, default=1000, help="Throughput ops (default 1000)")
    args = parser.parse_args()

    global TIMING_RUNS, THROUGHPUT_OPS
    TIMING_RUNS = args.runs
    THROUGHPUT_OPS = args.ops

    seller_urls = list(SELLER_URLS)
    buyer_urls = list(BUYER_URLS)

    print(f"\n{'='*60}")
    print(f"  PA3 Performance Test")
    print(f"  Mode: {args.mode}")
    print(f"  Timing runs: {TIMING_RUNS} | Throughput ops: {THROUGHPUT_OPS}")
    print(f"{'='*60}")

    if args.mode == "frontend_fail":
        print(f"\n  Dropping frontend: {seller_urls[-1]}")
        print(f"  Dropping frontend: {buyer_urls[-1]}")
        print("  KILL those processes first!\n")
        seller_urls = seller_urls[:-1]
        buyer_urls = buyer_urls[:-1]
    elif args.mode == "product_nonleader_fail":
        print("\n  KILL one non-leader Product DB replica first!\n")
    elif args.mode == "product_leader_fail":
        print("\n  KILL the Product DB leader and wait 5s first!\n")

    scenarios = {1: 1, 2: 10, 3: 100}
    results = []

    if args.all:
        for s in [1, 2, 3]:
            r = run_scenario(scenarios[s], args.mode, seller_urls, buyer_urls)
            results.append(r)
    elif args.scenario:
        r = run_scenario(scenarios[args.scenario], args.mode, seller_urls, buyer_urls)
        results.append(r)
    else:
        print("\nUsage:")
        print("  python3 performance_test.py --all --mode normal")
        print("  python3 performance_test.py --scenario 1 --mode normal")
        print("  python3 performance_test.py --all --mode normal --runs 3 --ops 100")
        return

    # Summary
    print(f"\n{'='*75}")
    print(f"{'SCENARIO':<15} {'MODE':<25} {'AVG RT (ms)':<15} {'THROUGHPUT (ops/s)'}")
    print(f"{'-'*75}")
    for r in results:
        print(f"{r['scenario']:<15} {r['mode']:<25} {r['avg_response_time_ms']:<15} {r['throughput_ops_per_sec']}")
    print(f"{'='*75}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"perf_{args.mode}_{ts}.csv"
    with open(fn, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)
    print(f"\nSaved: {fn}")


if __name__ == "__main__":
    main()