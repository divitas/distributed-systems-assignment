#!/bin/bash

# Startup script for Online Marketplace System
# This script starts all server components

echo "========================================="
echo "Starting Online Marketplace System"
echo "========================================="

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( dirname "$SCRIPT_DIR" )"

cd "$PROJECT_DIR"

# Initialize databases
echo "Initializing databases..."
python3 database/init_db.py

# Start Customer Database Server
echo "Starting Customer Database Server..."
python3 database/customer_db.py &
CUSTOMER_DB_PID=$!
sleep 1

# Start Product Database Server
echo "Starting Product Database Server..."
python3 database/product_db.py &
PRODUCT_DB_PID=$!
sleep 1

# Start Seller Frontend Server
echo "Starting Seller Frontend Server..."
python3 frontend/seller_server.py &
SELLER_FRONTEND_PID=$!
sleep 1

# Start Buyer Frontend Server
echo "Starting Buyer Frontend Server..."
python3 frontend/buyer_server.py &
BUYER_FRONTEND_PID=$!
sleep 1

echo ""
echo "========================================="
echo "All servers started successfully!"
echo "========================================="
echo "Customer DB PID: $CUSTOMER_DB_PID"
echo "Product DB PID: $PRODUCT_DB_PID"
echo "Seller Frontend PID: $SELLER_FRONTEND_PID"
echo "Buyer Frontend PID: $BUYER_FRONTEND_PID"
echo ""
echo "To stop all servers, run: ./scripts/stop_all.sh"
echo "Or use: kill $CUSTOMER_DB_PID $PRODUCT_DB_PID $SELLER_FRONTEND_PID $BUYER_FRONTEND_PID"
echo ""
echo "To start a seller client: python3 client/seller_client.py"
echo "To start a buyer client: python3 client/buyer_client.py"
echo "To run performance tests: python3 tests/performance_test.py"
echo "========================================="

# Save PIDs to file for stop script
echo "$CUSTOMER_DB_PID" > /tmp/marketplace_customer_db.pid
echo "$PRODUCT_DB_PID" > /tmp/marketplace_product_db.pid
echo "$SELLER_FRONTEND_PID" > /tmp/marketplace_seller_frontend.pid
echo "$BUYER_FRONTEND_PID" > /tmp/marketplace_buyer_frontend.pid

# Wait for user interrupt
echo ""
echo "Press Ctrl+C to stop all servers..."
wait
