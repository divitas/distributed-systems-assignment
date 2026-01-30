#!/bin/bash

# Stop script for Online Marketplace System

echo "========================================="
echo "Stopping Online Marketplace System"
echo "========================================="

# Read PIDs from files
if [ -f /tmp/marketplace_customer_db.pid ]; then
    CUSTOMER_DB_PID=$(cat /tmp/marketplace_customer_db.pid)
    echo "Stopping Customer DB (PID: $CUSTOMER_DB_PID)..."
    kill $CUSTOMER_DB_PID 2>/dev/null
    rm /tmp/marketplace_customer_db.pid
fi

if [ -f /tmp/marketplace_product_db.pid ]; then
    PRODUCT_DB_PID=$(cat /tmp/marketplace_product_db.pid)
    echo "Stopping Product DB (PID: $PRODUCT_DB_PID)..."
    kill $PRODUCT_DB_PID 2>/dev/null
    rm /tmp/marketplace_product_db.pid
fi

if [ -f /tmp/marketplace_seller_frontend.pid ]; then
    SELLER_FRONTEND_PID=$(cat /tmp/marketplace_seller_frontend.pid)
    echo "Stopping Seller Frontend (PID: $SELLER_FRONTEND_PID)..."
    kill $SELLER_FRONTEND_PID 2>/dev/null
    rm /tmp/marketplace_seller_frontend.pid
fi

if [ -f /tmp/marketplace_buyer_frontend.pid ]; then
    BUYER_FRONTEND_PID=$(cat /tmp/marketplace_buyer_frontend.pid)
    echo "Stopping Buyer Frontend (PID: $BUYER_FRONTEND_PID)..."
    kill $BUYER_FRONTEND_PID 2>/dev/null
    rm /tmp/marketplace_buyer_frontend.pid
fi

echo ""
echo "All servers stopped."
echo "========================================="
