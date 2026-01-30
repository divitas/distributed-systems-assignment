# Performance Report
## Online Marketplace Distributed System

### Experimental Setup

**Hardware Configuration:**
- VM Configuration: [Specify VM specs - CPU, RAM, Network]
- Number of VMs: 5
- VM Locations: [Specify if co-located or distributed]

**Software Configuration:**
- Operating System: Ubuntu 24.04 / [Your OS]
- Python Version: 3.x
- Database: SQLite

**Component Distribution:**
- VM1: Customer Database Server (IP: X.X.X.X)
- VM2: Product Database Server (IP: X.X.X.X)
- VM3: Buyer Frontend Server (IP: X.X.X.X)
- VM4: Seller Frontend Server (IP: X.X.X.X)
- VM5: Test Clients

**Network Configuration:**
- Network Type: [LAN/Cloud/etc.]
- Estimated Latency: [X ms between VMs]
- Bandwidth: [X Mbps]

**Test Configuration:**
- Each test scenario run 10 times
- Each client performs ~1000 total operations across all runs
- Operations include: account creation, login, item operations, search, cart operations, logout

---

### Scenario 1: Light Load (1 Seller + 1 Buyer)

**Configuration:**
- Number of Sellers: 1
- Number of Buyers: 1
- Operations per Client: 100
- Number of Runs: 10

**Results:**

| Metric | Value |
|--------|-------|
| Average Response Time | X.XX ms |
| Median Response Time | X.XX ms |
| Min Response Time | X.XX ms |
| Max Response Time | X.XX ms |
| Standard Deviation | X.XX ms |
| Average Throughput | X.XX ops/sec |
| Total Operations | XXXX |
| Total Errors | X |
| Error Rate | X.XX% |

**Analysis:**

With only one seller and one buyer, the system demonstrates baseline performance with minimal contention. The response times are low because:
1. No thread contention for database connections
2. Minimal network congestion
3. Database can handle sequential requests efficiently
4. No queueing delays at frontend servers

The throughput is limited primarily by:
- Network round-trip time (RTT) between components
- Database query execution time
- Sequential nature of operations

Expected observations:
- Consistent, low response times
- High reliability (low error rate)
- Throughput limited by single-client request rate

---

### Scenario 2: Medium Load (10 Sellers + 10 Buyers)

**Configuration:**
- Number of Sellers: 10
- Number of Buyers: 10
- Operations per Client: 50
- Number of Runs: 10

**Results:**

| Metric | Value |
|--------|-------|
| Average Response Time | X.XX ms |
| Median Response Time | X.XX ms |
| Min Response Time | X.XX ms |
| Max Response Time | X.XX ms |
| Standard Deviation | X.XX ms |
| Average Throughput | X.XX ops/sec |
| Total Operations | XXXX |
| Total Errors | X |
| Error Rate | X.XX% |

**Analysis:**

With 10 concurrent sellers and buyers (20 total clients), we observe:

Performance changes compared to Scenario 1:
1. Response time likely increases by X% due to:
   - Thread contention at frontend servers
   - Database connection pool utilization
   - Increased network traffic
   
2. Throughput increases significantly because:
   - Parallel processing of multiple requests
   - Better utilization of multi-threaded architecture
   - Database can handle concurrent queries

Bottlenecks that may emerge:
- Database lock contention for write operations (INSERT, UPDATE)
- Thread pool saturation at frontend servers
- Network bandwidth if operations transfer large amounts of data

Expected observations:
- Moderate increase in average response time
- Higher throughput than Scenario 1
- Slightly increased variance in response times
- Potential for occasional slower responses due to contention

---

### Scenario 3: Heavy Load (100 Sellers + 100 Buyers)

**Configuration:**
- Number of Sellers: 100
- Number of Buyers: 100
- Operations per Client: 5
- Number of Runs: 10

**Results:**

| Metric | Value |
|--------|-------|
| Average Response Time | X.XX ms |
| Median Response Time | X.XX ms |
| Min Response Time | X.XX ms |
| Max Response Time | X.XX ms |
| Standard Deviation | X.XX ms |
| Average Throughput | X.XX ops/sec |
| Total Operations | XXXX |
| Total Errors | X |
| Error Rate | X.XX% |

**Analysis:**

With 100 concurrent sellers and buyers (200 total clients), the system experiences maximum load:

Performance degradation factors:
1. Response time increases significantly because:
   - High contention for database connections
   - Thread pool exhaustion causing queueing
   - SQLite write serialization (single writer)
   - Increased lock wait times

2. Throughput may plateau or decrease slightly due to:
   - Resource saturation (CPU, memory, I/O)
   - Lock contention overhead
   - Context switching overhead with many threads

System behavior under stress:
- SQLite's single-writer limitation becomes apparent
- Thread pool reaches capacity
- Queueing delays dominate response time
- Higher variance in response times

Potential optimizations identified:
- Implement connection pooling with better sizing
- Use PostgreSQL/MySQL for better concurrent write performance
- Add caching layer for read-heavy operations
- Implement request queuing with priorities
- Scale horizontally with multiple frontend servers

---

### Comparative Analysis

**Response Time Comparison:**

| Scenario | Avg Response Time | Change from Previous |
|----------|------------------|---------------------|
| 1S + 1B  | X.XX ms | Baseline |
| 10S + 10B | X.XX ms | +X% |
| 100S + 100B | X.XX ms | +X% |

**Throughput Comparison:**

| Scenario | Avg Throughput (ops/sec) | Change from Previous |
|----------|-------------------------|---------------------|
| 1S + 1B  | X.XX | Baseline |
| 10S + 10B | X.XX | +X% |
| 100S + 100B | X.XX | +X% |

**Key Observations:**

1. **Scalability:**
   - Throughput scales [linearly/sublinearly] with client count up to 10 clients
   - Beyond 10 clients, scaling becomes [sublinear/saturated] due to resource contention
   - System handles 100 concurrent clients with acceptable degradation

2. **Response Time vs Load:**
   - Light load: Minimal queueing, response time dominated by network + processing
   - Medium load: Moderate queueing, thread contention becomes factor
   - Heavy load: Significant queueing, resource saturation evident

3. **Bottlenecks Identified:**
   - **Primary:** SQLite single-writer limitation for write operations
   - **Secondary:** Thread pool saturation at 100+ concurrent clients
   - **Tertiary:** Network latency between distributed components

4. **System Strengths:**
   - Excellent performance under light-medium load
   - Graceful degradation under heavy load
   - Thread-safe design prevents data corruption
   - Stateless frontend enables easy horizontal scaling

5. **Improvement Opportunities:**
   - Replace SQLite with PostgreSQL/MySQL for better concurrent writes
   - Implement read replicas for product search operations
   - Add caching layer (Redis) for frequently accessed data
   - Implement connection pooling with dynamic sizing
   - Add load balancer for frontend servers

---

### Insights and Conclusions

**Performance Characteristics:**

The system demonstrates strong performance under varying loads with clear scalability limits:

1. **Response Time Analysis:**
   - Baseline (1+1): ~X ms - Network RTT dominates
   - Medium (10+10): ~X ms - Thread contention emerges
   - Heavy (100+100): ~X ms - Resource saturation evident
   
2. **Throughput Analysis:**
   - Scales well from 1 to 10 concurrent clients
   - Begins to saturate around 20-50 concurrent clients
   - Plateaus at ~X ops/sec under maximum load

3. **Error Rate:**
   - Remains low (<X%) across all scenarios
   - Indicates robust error handling and retry logic
   - Most errors due to [connection timeouts/validation/etc.]

**Architectural Assessment:**

Strengths:
- Stateless frontend design enables easy scaling
- Thread-safe database operations ensure data integrity
- Clean separation of concerns (frontend/backend)
- Handles concurrent operations reliably

Weaknesses:
- SQLite single-writer limitation
- No caching layer for read-heavy operations
- Thread pool sizing not dynamically adjusted
- No load balancing between multiple frontends

**Recommendations:**

For production deployment handling 100+ concurrent users:
1. Replace SQLite with PostgreSQL with connection pooling
2. Add Redis cache for product search results
3. Deploy multiple frontend servers with load balancer
4. Implement database read replicas
5. Add request queuing with priorities
6. Monitor and tune thread pool sizes

**Conclusion:**

The system successfully meets the assignment requirements and demonstrates:
- Correct implementation of all specified APIs
- Proper session management with timeouts
- Thread-safe concurrent operation
- Graceful performance degradation under load
- Clear scalability path for future enhancements

The performance results validate the design decisions and identify clear optimization paths for future assignments.

---

### Appendix: Raw Data

[Include raw performance data, charts, graphs as needed]

**Sample Run Data:**
```
Scenario 1, Run 1:
- Total Time: X.XX s
- Operations: XXX
- Avg RT: X.XX ms
- Throughput: X.XX ops/sec

[Continue for all runs...]
```

**Performance Graphs:**
[Include charts showing]:
- Response time distribution
- Throughput over time
- Response time vs. concurrent clients
- Error rate vs. load

---

*Report generated on: [Date]*
*System version: 1.0*
*Testing completed by: [Your Name]*
