# Online Marketplace - Test Report

## Test Execution Summary

**Date:** 2026-01-28 16:33:50

## Requirement Tests

✅ **All requirement tests PASSED**

## Performance Tests

✅ **Performance tests COMPLETED**

### Performance Results

```json
{
  "test_config": {
    "iterations": 10,
    "operations_per_client": 1000
  },
  "scenarios": [
    {
      "name": "Scenario 1: 1 Seller, 1 Buyer",
      "num_sellers": 1,
      "num_buyers": 1,
      "total_operations": 6967,
      "total_errors": 1047,
      "avg_response_time_ms": 0.9093579593032611,
      "median_response_time_ms": 0.8282661437988281,
      "p95_response_time_ms": 1.4960765838623047,
      "avg_throughput_ops_per_sec": 1874.301770136224
    },
    {
      "name": "Scenario 2: 10 Sellers, 10 Buyers",
      "num_sellers": 10,
      "num_buyers": 10,
      "total_operations": 0,
      "total_errors": 200,
      "avg_response_time_ms": 0,
      "median_response_time_ms": 0,
      "p95_response_time_ms": 0,
      "avg_throughput_ops_per_sec": 0.0
    },
    {
      "name": "Scenario 3: 100 Sellers, 100 Buyers",
      "num_sellers": 100,
      "num_buyers": 100,
      "total_operations": 0,
      "total_errors": 2000,
      "avg_response_time_ms": 0,
      "median_response_time_ms": 0,
      "p95_response_time_ms": 0,
      "avg_throughput_ops_per_sec": 0.0
    }
  ]
}
```

## Log Files

- Server logs: `logs/`
- Requirement test log: `logs/requirements_test.log`
- Performance test log: `logs/performance_test.log`
