# Scale and analytics plan

The supplied TimescaleDB archive is a mature PostgreSQL extension repository, not an application database layer that should be copied into OSS-Work. We use its relevant design ideas instead: time-oriented event storage, hypertables, continuous aggregates, retention windows, and a staged high-availability plan.

## Data path

| Stage | Component | Safety and scale control |
|---|---|---|
| Ingress | `TelemetryEvent` | UUID and tenant validation, bounded source/kind, payload size limit |
| Buffer | `TelemetryBatcher` | Maximum queue and batch sizes; explicit drop counter for backpressure visibility |
| Durable store | `telemetry_events` | TimescaleDB hypertable, tenant indexes, request idempotency |
| Audit store | `audit_events` | Separate append-oriented event record with redacted details |
| Analytics | `telemetry_hourly` | Incremental hourly summary for dashboard reads |
| Retention | Optional policy | Must be aligned with aggregate refresh windows |
| Availability | Staged replication | Define RPO/RTO and test failover before enabling replicas |

Continuous aggregates are useful because they incrementally refresh summarized data instead of recomputing a full aggregate each time [1]. Retention and refresh must be designed together; removing raw rows before the aggregate has safely materialized them can remove historical summary data [2]. PostgreSQL row-level security provides a database-side per-row restriction, but owners and BYPASSRLS roles require explicit review [3].

## What this does not claim

No archive or schema alone proves support for a particular user count. Capacity depends on event shape, write rate, query mix, retention, indexes, hardware, network, and operational limits. Establish a target service-level objective, then measure throughput, p95/p99 latency, queue depth, saturation, failover recovery, and data loss under representative load.

## Recommended rollout

Begin with a single staging database and a tenant-isolation test matrix. Add a bounded connection pool and a durable queue at the service boundary. Load-test raw inserts and aggregate reads separately. Only after backup/restore and failover drills pass should a production deployment add read replicas or a managed high-availability topology. PostgreSQL documents that synchronous and asynchronous replication trade latency against possible data loss [4].

## References

[1]: https://www.tigerdata.com/docs/learn/continuous-aggregates "Tiger Data: Understand continuous aggregates"
[2]: https://www.tigerdata.com/docs/learn/data-lifecycle/data-retention/data-retention-with-continuous-aggregates "Tiger Data: Data retention with continuous aggregates"
[3]: https://www.postgresql.org/docs/current/ddl-rowsecurity.html "PostgreSQL: Row Security Policies"
[4]: https://www.postgresql.org/docs/current/high-availability.html "PostgreSQL: High Availability, Load Balancing, and Replication"
