# PostgreSQL and TimescaleDB data layer

The `db/timescale/001_telemetry.sql` migration is a **staging-ready reference**, not an instruction to run against production without review. It applies the supplied TimescaleDB direction to OSS-Work’s operational data: time-stamped telemetry and audit events, tenant-scoped indexes, request idempotency, row-level security, and an hourly continuous aggregate.

TimescaleDB continuous aggregates incrementally refresh summarized data in the background, which is useful for dashboards over large event streams [1]. Retention must be chosen together with aggregate refresh windows; deleting raw rows before the aggregate has safely materialized them can remove historical summaries [2]. PostgreSQL row-level security policies are default-deny when enabled without an applicable policy, and table owners or BYPASSRLS roles need special review [3].

The schema uses `organization_id` as the tenant key and expects the application to set `SET LOCAL app.organization_id = '<uuid>'` within every transaction. This is a defense-in-depth control, not a substitute for API authentication or authorization. The service role used for migrations must not be the same role used by tenant-facing requests.

## Scaling path

Start with one primary database, a bounded application connection pool, and read replicas only after measurement. For higher availability, use a tested PostgreSQL streaming-replication and failover design; PostgreSQL documents that synchronous and asynchronous replication trade latency against potential data loss [4]. Define recovery point and recovery time objectives before choosing a topology.

The SQL does not create users, open ports, provision credentials, enable public network access, or claim a capacity number. Those are deployment decisions that belong in infrastructure-as-code and an environment-specific review.

## References

[1]: https://www.tigerdata.com/docs/learn/continuous-aggregates "Tiger Data: Understand continuous aggregates"
[2]: https://www.tigerdata.com/docs/learn/data-lifecycle/data-retention/data-retention-with-continuous-aggregates "Tiger Data: Data retention with continuous aggregates"
[3]: https://www.postgresql.org/docs/current/ddl-rowsecurity.html "PostgreSQL: Row Security Policies"
[4]: https://www.postgresql.org/docs/current/high-availability.html "PostgreSQL: High Availability, Load Balancing, and Replication"
