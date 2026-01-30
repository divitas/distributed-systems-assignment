# Quick Start Guide
## Online Marketplace Distributed System

This guide will help you quickly set up and test the system.

## Setup (5 minutes)

### 1. Extract the Project
```bash
tar -xzf online-marketplace.tar.gz
cd online-marketplace
```

### 2. Test on Single Machine First

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Start all servers
./scripts/start_all.sh
```

Wait a few seconds for all servers to initialize. You should see output indicating all 4 servers have started.

### 3. Test with CLI Clients

**Open a new terminal** for the seller client:
```bash
cd online-marketplace
python3 client/seller_client.py
```

Follow the prompts to:
1. Create an account
2. Login
3. Register an item for sale

**Open another terminal** for the buyer client:
```bash
cd online-marketplace
python3 client/buyer_client.py
```

Follow the prompts to:
1. Create an account
2. Login
3. Search for items
4. Add items to cart
5. Save cart

### 4. Run Performance Tests

**Open another terminal**:
```bash
cd online-marketplace
python3 tests/performance_test.py
```

This will run automated tests for all three scenarios and generate performance metrics.

### 5. Stop All Servers

```bash
./scripts/stop_all.sh
```

Or press Ctrl+C in the terminal running start_all.sh

---

## Deployment on 5 VMs (15 minutes)

### Prerequisites
- 5 VMs with Python 3.7+ installed
- Network connectivity between all VMs
- Firewall rules allowing TCP connections on ports 5001, 5002, 6001, 6002

### Step 1: Copy Project to All VMs

```bash
# On your local machine, copy to each VM
scp online-marketplace.tar.gz user@VM1:/home/user/
scp online-marketplace.tar.gz user@VM2:/home/user/
scp online-marketplace.tar.gz user@VM3:/home/user/
scp online-marketplace.tar.gz user@VM4:/home/user/
scp online-marketplace.tar.gz user@VM5:/home/user/
```

### Step 2: Extract on Each VM

```bash
# On each VM
tar -xzf online-marketplace.tar.gz
cd online-marketplace
```

### Step 3: Update Configuration

Edit `config.py` on ALL VMs with your actual VM IPs:

```python
# Example with real IPs
CUSTOMER_DB_HOST = "10.0.0.1"      # VM1 IP
CUSTOMER_DB_PORT = 5001

PRODUCT_DB_HOST = "10.0.0.2"       # VM2 IP
PRODUCT_DB_PORT = 5002

BUYER_FRONTEND_HOST = "10.0.0.3"   # VM3 IP
BUYER_FRONTEND_PORT = 6001

SELLER_FRONTEND_HOST = "10.0.0.4"  # VM4 IP
SELLER_FRONTEND_PORT = 6002
```

**Important**: Update ALL VMs with the same configuration!

### Step 4: Start Services on Each VM

**On VM1** (Customer Database):
```bash
cd online-marketplace
python3 database/init_db.py
python3 database/customer_db.py
```

**On VM2** (Product Database):
```bash
cd online-marketplace
python3 database/init_db.py
python3 database/product_db.py
```

**On VM3** (Buyer Frontend):
```bash
cd online-marketplace
python3 frontend/buyer_server.py
```

**On VM4** (Seller Frontend):
```bash
cd online-marketplace
python3 frontend/seller_server.py
```

**On VM5** (Test Clients):
```bash
cd online-marketplace

# Run seller client
python3 client/seller_client.py

# Or run buyer client (in another terminal)
python3 client/buyer_client.py

# Or run performance tests
python3 tests/performance_test.py
```

### Step 5: Verify Connectivity

If you get connection errors:

1. **Check firewall** on database and frontend VMs:
```bash
# Allow connections on required ports
sudo ufw allow 5001  # Customer DB
sudo ufw allow 5002  # Product DB
sudo ufw allow 6001  # Buyer Frontend
sudo ufw allow 6002  # Seller Frontend
```

2. **Verify servers are listening**:
```bash
netstat -tuln | grep -E '5001|5002|6001|6002'
```

3. **Test connectivity** from VM5:
```bash
telnet VM1_IP 5001
telnet VM2_IP 5002
telnet VM3_IP 6001
telnet VM4_IP 6002
```

---

## Testing Scenarios

### Scenario 1: Basic Functionality Test

1. Start all servers
2. Run 1 seller client, create account, add 5 items
3. Run 1 buyer client, search and add items to cart
4. Verify cart persistence: logout, login again, cart should be restored

### Scenario 2: Concurrent Users Test

1. Start all servers
2. Run 5 seller clients simultaneously (5 terminals)
3. Run 5 buyer clients simultaneously (5 terminals)
4. Each should be able to operate independently

### Scenario 3: Session Timeout Test

1. Start all servers
2. Login as buyer
3. Wait 6 minutes (session timeout is 5 minutes)
4. Try to perform an operation
5. Should get "Session expired" error
6. Login again should work

### Scenario 4: Frontend Crash Recovery Test

1. Start all servers and login as buyer
2. Add items to cart but DON'T save
3. Kill and restart buyer frontend server
4. Cart should still be there (proves stateless frontend)

### Scenario 5: Performance Test

```bash
python3 tests/performance_test.py
```

Runs automated tests:
- 1 seller + 1 buyer (10 runs, 100 ops each)
- 10 sellers + 10 buyers (10 runs, 50 ops each)
- 100 sellers + 100 buyers (10 runs, 5 ops each)

---

## Common Issues and Solutions

### Port Already in Use
```bash
# Find process using port
lsof -ti:5001 | xargs kill -9

# Or change port in config.py
```

### Connection Refused
- Ensure server is running: `ps aux | grep python`
- Check firewall: `sudo ufw status`
- Verify config.py has correct IPs

### Session Expired Too Quickly
- Increase SESSION_TIMEOUT in config.py (default is 300 seconds)

### Database Locked
```bash
# Remove and reinitialize
rm -f data/*.db
python3 database/init_db.py
```

### Import Errors
```bash
# Ensure you're in the project directory
cd online-marketplace

# Verify Python version
python3 --version  # Should be 3.7+
```

---

## Performance Testing Tips

1. **For accurate results**, ensure:
   - No other heavy processes running
   - Network is stable
   - All VMs have similar specs

2. **Interpreting results**:
   - Response time < 100ms = Excellent
   - Response time < 500ms = Good
   - Response time > 1000ms = Poor (check bottlenecks)

3. **Expected performance**:
   - Scenario 1: Very low latency, limited throughput
   - Scenario 2: Moderate latency, good throughput
   - Scenario 3: Higher latency, maximum throughput

---

## Next Steps

After successful testing:

1. Review the PERFORMANCE_REPORT.md template
2. Fill in your actual performance metrics
3. Analyze bottlenecks and explain performance differences
4. Document any issues encountered and solutions

---

## Support

If you encounter issues:

1. Check the full README.md for detailed documentation
2. Verify all configuration settings in config.py
3. Check server logs for error messages
4. Ensure network connectivity between VMs

---

**Happy Testing!** 🚀
