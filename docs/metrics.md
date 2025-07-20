## Phase 1 Baseline

**Throughput**
- `rate(producer_messages_sent_total[5m])`: 457.62 TPS

**Latency**
- P50: 0.0021
- P95: 0.0064

**Errors**
- send_errors_total: 0

**Resource Usage**
- (fill in `docker stats` output)
CONTAINER ID   NAME                        CPU %     MEM USAGE / LIMIT     MEM %     NET I/O          BLOCK I/O        PIDS
7ceec7c7ee1d   fraud-platform-kafka-1      24.61%    791.8MiB / 7.653GiB   10.10%    375MB / 71.4MB   98.3kB / 351MB   85
d43496a83a64   fraud-platform-producer-1   14.02%    15.22MiB / 7.653GiB   0.19%     71.4MB / 375MB   0B / 131kB       6

**Notes**
- Prometheus scrape interval: 15s
- Metrics exported via `/metrics` on port 8001