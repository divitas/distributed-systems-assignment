#!/bin/bash
# PA3 Startup Script
# Run this on each VM to start the appropriate components

# Usage:
#   ./start.sh customer_db <node_id>    # Start customer DB replica (0-4)
#   ./start.sh product_db <node_id>     # Start product DB replica (0-4)
#   ./start.sh buyer_server <replica_id> # Start buyer frontend replica (0-3)
#   ./start.sh seller_server <replica_id> # Start seller frontend replica (0-3)
#   ./start.sh all_on_vm <vm_number>    # Start all components assigned to this VM

set -e

COMPONENT=$1
ID=$2

case $COMPONENT in
    customer_db)
        echo "Starting Customer DB replica $ID..."
        python database/customer_db_replicated.py --node-id $ID
        ;;
    product_db)
        echo "Starting Product DB replica $ID (Raft)..."
        python database/product_db_replicated.py --node-id $ID
        ;;
    buyer_server)
        echo "Starting Buyer Frontend replica $ID..."
        python frontend/buyer_server_replicated.py --replica-id $ID
        ;;
    seller_server)
        echo "Starting Seller Frontend replica $ID..."
        python frontend/seller_server_replicated.py --replica-id $ID
        ;;
    all_on_vm)
        echo "Starting all components for VM $ID..."
        echo "Check config.py for which components run on which VM."
        echo "Adjust the commands below based on your deployment."
        echo ""
        echo "Example for VM1 (10.224.78.211):"
        echo "  python database/customer_db_replicated.py --node-id 0 &"
        echo "  python database/customer_db_replicated.py --node-id 1 &"
        echo "  python database/product_db_replicated.py --node-id 2 &"
        echo "  python frontend/buyer_server_replicated.py --replica-id 2 &"
        echo "  python frontend/seller_server_replicated.py --replica-id 2 &"
        ;;
    *)
        echo "Usage: $0 {customer_db|product_db|buyer_server|seller_server|all_on_vm} <id>"
        exit 1
        ;;
esac
