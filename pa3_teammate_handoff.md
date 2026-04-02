# PA3 Implementation Handoff Summary

This document summarizes the changes successfully implemented thus far for **PA3** regarding the **Customer Database (Atomic Broadcast)** and **Frontend Replication**. 

You can hand this directly to your teammate as context for how to proceed with the **Raft Product DB** merge!

---

## What Has Been Completed 

### 1. Customer DB Replication (Rotating Sequencer Atomic Broadcast)
- **Architecture**: [database/customer_db.py](file:///Users/divita/Developer/distributed-systems-assignment/database/customer_db.py) was transformed from a single-node SQLite instance into a 5-node distributed cluster communicating over UDP for state replication and gRPC for client requests.
- **Protocol**: Built a robust **Rotating Sequencer Atomic Broadcast** engine ([AtomicBroadcastNode](file:///Users/divita/Developer/distributed-systems-assignment/database/customer_db.py#47-595)), where the responsibility for assigning a global sequence number rotates among the 5 replicas [(global_seq % 5)](file:///tmp/test_cluster.py#14-17).
- **Strict Consistency**: Enforced a majority delivery condition (`count >= 3`). The gRPC endpoints (like [CreateSeller](file:///Users/divita/Developer/distributed-systems-assignment/database/customer_db.py#1030-1039)) wait to respond to the frontend until their sequenced write has been acknowledged by a majority of the cluster.
- **Advanced Fault Tolerance (Gap Catch-up)**: 
  - Implemented 0.5s UDP heartbeats (`ACK` messages) exchanging sequence metadata.
  - Built a resilient NACK system. If a sequencer node crashes and reboots (losing its RAM), it parses peer heartbeats to detect gaps, broadcasts a NACK, and seamlessly recovers both unassigned requests and missed sequences without deadlocking.
- **Persistence**: Replicas maintain independent SQLite databases ([data/customer_0.db](file:///Users/divita/Developer/distributed-systems-assignment/data/customer_0.db) through `customer_4.db`) and track their start sequences across reboots.

### 2. Frontend Server Replication & Client Failover
- **Config Updates**: Replicated the stateless HTTP frontends by defining 4 unique VM endpoint addresses in [config.py](file:///Users/divita/Developer/distributed-systems-assignment/config.py) for both `BUYER_FRONTEND_REPLICAS` and `SELLER_FRONTEND_REPLICAS`.
- **Client Resilience**: Upgraded the CLI clients ([buyer_client.py](file:///Users/divita/Developer/distributed-systems-assignment/client/buyer_client.py) and [seller_client.py](file:///Users/divita/Developer/distributed-systems-assignment/client/seller_client.py)) with a native HTTP retry loop ([_request_with_failover](file:///Users/divita/Developer/distributed-systems-assignment/client/buyer_client.py#34-63)). If a user's connected frontend goes down, the client seamlessly catches the timeout/connection error and routes subsequent HTTP requests to the next live frontend replica entirely automatically.

### 3. API & Protocol Fixes
- **Protobuf Patch**: Fixed a legacy PA2 bug in [server/buyer_server.py](file:///Users/divita/Developer/distributed-systems-assignment/server/buyer_server.py) where it was calling `IncrementSellerItemsSold`. It now correctly uses the PA3 protobuf [UpdateSellerItemsSold](file:///Users/divita/Developer/distributed-systems-assignment/database/customer_db.py#1142-1151) with the proper [UpdateItemsSoldRequest](file:///Users/divita/Developer/distributed-systems-assignment/proto/customer.proto#34-35) structure.
- **Credit Card Validations**: Hardened the `/buyer/make_purchase` API. It now validates exactly 16 digits for the card number, exactly 3 digits for the CVV, and strictly checks that the `MM/YY` expiration date is mathematically in the future before routing to the 10%-random-failure SOAP Financial Service.

---

## Next Steps for Teammate (Raft Product DB)

Since the Customer DB replication is fully functional and stable, the remainder of the PA3 collated submission revolves entirely around the **Product DB**. 

**Here is the exact roadmap to merge the Raft logic:**

1. **Integrate PySyncObj**: Add `database/product_db_replicated.py` (which the teammate has written using the `pysyncobj` Raft library).
2. **Update Config**: Modify [config.py](file:///Users/divita/Developer/distributed-systems-assignment/config.py) to define a `PRODUCT_DB_REPLICAS` array containing the IPs, gRPC ports, and Raft replication ports for all 5 product replicas.
3. **Frontend Server gRPC Failover**:
   - Currently, [server/buyer_server.py](file:///Users/divita/Developer/distributed-systems-assignment/server/buyer_server.py) and [server/seller_server.py](file:///Users/divita/Developer/distributed-systems-assignment/server/seller_server.py) hardcode their [get_product_stub()](file:///Users/divita/Developer/distributed-systems-assignment/server/seller_server.py#33-36) connection to a single Product DB host.
   - The teammate needs to update [get_product_stub()](file:///Users/divita/Developer/distributed-systems-assignment/server/seller_server.py#33-36) in both frontend servers to utilize the `PRODUCT_DB_REPLICAS` array. 
   - They should implement a simple `try/except` gRPC failover loop (very similar to what was done in the CLI clients for HTTP). If the frontend tries to call a Product DB node that is down (or isn't the current Raft leader), the frontend should catch the gRPC exception and dynamically retry the next Product DB replica in the list until it succeeds.
