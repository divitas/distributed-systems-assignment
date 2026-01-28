#!/usr/bin/env python3
"""
run_all_tests.py - Complete Test Runner (Cross-Platform)

This script:
1. Starts all server components
2. Waits for servers to be ready
3. Runs requirement tests
4. Runs performance tests
5. Stops all servers
6. Generates summary report

Works on Windows, Linux, and macOS.
"""

import subprocess
import sys
import os
import time
import socket
import signal
import json
from datetime import datetime
from typing import List, Optional

# =============================================================================
# Configuration
# =============================================================================

SERVERS = [
    {
        "name": "Customer DB",
        "script": "customer_db/customer_db_server.py",
        "port": 5003,
        "args": ["--port", "5003"]
    },
    {
        "name": "Product DB",
        "script": "product_db/product_db_server.py",
        "port": 5004,
        "args": ["--port", "5004"]
    },
    {
        "name": "Seller Server",
        "script": "seller_server/seller_server.py",
        "port": 5002,
        "args": ["--port", "5002"]
    },
    {
        "name": "Buyer Server",
        "script": "buyer_server/buyer_server.py",
        "port": 5001,
        "args": ["--port", "5001"]
    },
]

LOG_DIR = "logs"


# =============================================================================
# Helper Functions
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color
    
    @staticmethod
    def disable():
        """Disable colors (for Windows without ANSI support)."""
        Colors.RED = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.BLUE = ''
        Colors.NC = ''


# Check if Windows without ANSI support
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except:
        Colors.disable()


def print_header(text: str):
    print()
    print(f"{Colors.BLUE}{'='*70}{Colors.NC}")
    print(f"{Colors.BLUE}  {text}{Colors.NC}")
    print(f"{Colors.BLUE}{'='*70}{Colors.NC}")


def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.NC}")


def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.NC}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}! {text}{Colors.NC}")


def is_port_open(port: int, host: str = "localhost") -> bool:
    """Check if a port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


def wait_for_port(port: int, timeout: int = 30) -> bool:
    """Wait for a port to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open(port):
            return True
        time.sleep(0.5)
    return False


def check_required_files() -> bool:
    """Check if all required files exist."""
    required = [
        "customer_db/customer_db_server.py",
        "product_db/product_db_server.py",
        "seller_server/seller_server.py",
        "buyer_server/buyer_server.py",
        "test_requirements.py",
        "test_performance.py",
        "buyer_client/buyer_client.py",
        "buyer_client/buyer_api.py",
        "seller_client/seller_client.py",
        "seller_client/seller_api.py"
    ]
    
    print_header("Checking Required Files")
    
    missing = []
    for filename in required:
        if os.path.exists(filename):
            print_success(filename)
        else:
            print_error(f"{filename} - NOT FOUND")
            missing.append(filename)
    
    return len(missing) == 0


# =============================================================================
# Server Management
# =============================================================================

class ServerManager:
    """Manages server processes."""
    
    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        os.makedirs(LOG_DIR, exist_ok=True)
    
    def start_server(self, name: str, script: str, port: int, args: List[str]) -> bool:
        """Start a single server."""
        print(f"Starting {name} (port {port})... ", end="", flush=True)
        
        # Check if port is already in use
        if is_port_open(port):
            print_warning(f"Port {port} already in use!")
            return False
        
        # Start the server
        log_file = open(os.path.join(LOG_DIR, f"{script.split('/')[-1].replace('.py', '')}.log"), "w")
        
        try:
            process = subprocess.Popen(
                [sys.executable, script] + args,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            )
            self.processes.append(process)
            
            # Wait for port to be ready
            if wait_for_port(port, timeout=15):
                print_success(f"Started (PID: {process.pid})")
                return True
            else:
                print_error("Failed to start (timeout)")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def start_all(self) -> bool:
        """Start all servers."""
        print_header("Starting Servers")
        
        for server in SERVERS:
            if not self.start_server(
                server["name"],
                server["script"],
                server["port"],
                server["args"]
            ):
                return False
        
        print()
        print_success("All servers started successfully!")
        return True
    
    def stop_all(self):
        """Stop all servers."""
        print_header("Stopping Servers")
        
        for process in self.processes:
            try:
                if sys.platform == 'win32':
                    process.terminate()
                else:
                    os.kill(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
                print(f"Stopped process {process.pid}")
            except Exception as e:
                try:
                    process.kill()
                except:
                    pass
        
        self.processes.clear()
        print_success("All servers stopped")


# =============================================================================
# Test Execution
# =============================================================================

def run_test(name: str, script: str, log_file: str) -> int:
    """Run a test script and return exit code."""
    print_header(f"Running {name}")
    
    log_path = os.path.join(LOG_DIR, log_file)
    
    try:
        # Run test and display output in real-time
        process = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Also save to log file
        with open(log_path, 'w') as f:
            for line in process.stdout:
                print(line, end='')
                f.write(line)
        
        process.wait()
        return process.returncode
        
    except Exception as e:
        print_error(f"Error running {script}: {e}")
        return 1


def generate_report(req_result: int, perf_result: int):
    """Generate summary report."""
    print_header("Generating Report")
    
    report_file = "TEST_REPORT.md"
    
    with open(report_file, 'w') as f:
        f.write("# Online Marketplace - Test Report\n\n")
        f.write("## Test Execution Summary\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## Requirement Tests\n\n")
        if req_result == 0:
            f.write("✅ **All requirement tests PASSED**\n\n")
        else:
            f.write("⚠️ **Some requirement tests FAILED**\n\n")
        
        f.write("## Performance Tests\n\n")
        if perf_result == 0:
            f.write("✅ **Performance tests COMPLETED**\n\n")
        else:
            f.write("⚠️ **Performance tests had issues**\n\n")
        
        # Add performance results if available
        if os.path.exists("performance_results.json"):
            f.write("### Performance Results\n\n")
            f.write("```json\n")
            with open("performance_results.json", 'r') as pf:
                f.write(pf.read())
            f.write("\n```\n\n")
        
        f.write("## Log Files\n\n")
        f.write(f"- Server logs: `{LOG_DIR}/`\n")
        f.write(f"- Requirement test log: `{LOG_DIR}/requirements_test.log`\n")
        f.write(f"- Performance test log: `{LOG_DIR}/performance_test.log`\n")
    
    print_success(f"Report generated: {report_file}")


# =============================================================================
# Main
# =============================================================================

def main():
    print()
    print(f"{Colors.GREEN}{'#'*70}{Colors.NC}")
    print(f"{Colors.GREEN}#{'':^68}#{Colors.NC}")
    print(f"{Colors.GREEN}#{'ONLINE MARKETPLACE - COMPLETE TEST SUITE':^68}#{Colors.NC}")
    print(f"{Colors.GREEN}#{'':^68}#{Colors.NC}")
    print(f"{Colors.GREEN}{'#'*70}{Colors.NC}")
    print()
    
    # Check Python version
    if sys.version_info < (3, 8):
        print_error("Python 3.8+ required")
        return 1
    
    print_success(f"Python {sys.version.split()[0]}")
    
    # Check required files
    if not check_required_files():
        print_error("Missing required files. Ensure all files are in the current directory.")
        return 1
    
    # Initialize server manager
    server_manager = ServerManager()
    
    try:
        # Start servers
        if not server_manager.start_all():
            print_error("Failed to start all servers")
            return 1
        
        # Wait for servers to fully initialize
        print("\nWaiting for servers to initialize...")
        time.sleep(2)
        
        # Run requirement tests
        print("\n" + "="*70)
        print("Press Enter to start requirement tests (or Ctrl+C to cancel)...")
        input()
        
        req_result = run_test(
            "Requirement Tests",
            "test_requirements.py",
            "requirements_test.log"
        )
        
        if req_result == 0:
            print_success("Requirement tests PASSED")
        else:
            print_warning("Some requirement tests FAILED")
        
        # Run performance tests
        print("\n" + "="*70)
        print("Press Enter to start performance tests (or Ctrl+C to skip)...")
        try:
            input()
            
            perf_result = run_test(
                "Performance Tests",
                "test_performance.py",
                "performance_test.log"
            )
            
            if perf_result == 0:
                print_success("Performance tests COMPLETED")
            else:
                print_warning("Performance tests had issues")
        except KeyboardInterrupt:
            print("\nSkipping performance tests...")
            perf_result = -1
        
        # Generate report
        generate_report(req_result, perf_result)
        
        # Final summary
        print_header("Test Execution Complete")
        
        print("\nResults Summary:")
        print("-" * 40)
        
        if req_result == 0:
            print(f"  Requirement Tests: {Colors.GREEN}PASSED{Colors.NC}")
        else:
            print(f"  Requirement Tests: {Colors.RED}FAILED{Colors.NC}")
        
        if perf_result == 0:
            print(f"  Performance Tests: {Colors.GREEN}COMPLETED{Colors.NC}")
        elif perf_result == -1:
            print(f"  Performance Tests: {Colors.YELLOW}SKIPPED{Colors.NC}")
        else:
            print(f"  Performance Tests: {Colors.YELLOW}HAD ISSUES{Colors.NC}")
        
        print("\nGenerated Files:")
        print("  • TEST_REPORT.md")
        if os.path.exists("performance_results.json"):
            print("  • performance_results.json")
        print(f"  • {LOG_DIR}/*.log")
        
        if req_result == 0 and perf_result in [0, -1]:
            print()
            print(f"{Colors.GREEN}{'#'*70}{Colors.NC}")
            print(f"{Colors.GREEN}#{'':^68}#{Colors.NC}")
            print(f"{Colors.GREEN}#{'🎉 TESTS SUCCESSFUL! 🎉':^68}#{Colors.NC}")
            print(f"{Colors.GREEN}#{'':^68}#{Colors.NC}")
            print(f"{Colors.GREEN}{'#'*70}{Colors.NC}")
            return 0
        else:
            print()
            print(f"{Colors.YELLOW}{'#'*70}{Colors.NC}")
            print(f"{Colors.YELLOW}#{'':^68}#{Colors.NC}")
            print(f"{Colors.YELLOW}#{'⚠️  CHECK LOGS FOR DETAILS ⚠️':^68}#{Colors.NC}")
            print(f"{Colors.YELLOW}#{'':^68}#{Colors.NC}")
            print(f"{Colors.YELLOW}{'#'*70}{Colors.NC}")
            return 1
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
    
    finally:
        # Always stop servers
        server_manager.stop_all()


if __name__ == "__main__":
    sys.exit(main())