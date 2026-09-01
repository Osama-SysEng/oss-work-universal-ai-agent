# Staging database profile

The compose file is for local or isolated staging only. It binds PostgreSQL to loopback, requires a reviewed pinned image through `TIMESCALE_IMAGE`, requires explicit database variables, loads the password from the ignored `deploy/secrets/postgres_password` file, and mounts the migration read-only.

Create the secret file outside version control, set `TIMESCALE_IMAGE`, `POSTGRES_USER`, and `POSTGRES_DB`, then start the profile from this directory. Do not expose port 6543 to a public interface. Apply the migration in a disposable staging database first and validate tenant-isolation tests before connecting any application worker.

This profile is not a high-availability deployment. Production requires managed backups or a tested backup system, monitoring, a recovery-point and recovery-time objective, failover drills, a bounded connection pool, and a separately reviewed network policy. PostgreSQL documents that replication topology involves trade-offs between synchronous durability and asynchronous performance [1].

## References

[1]: https://www.postgresql.org/docs/current/high-availability.html "PostgreSQL: High Availability, Load Balancing, and Replication"
