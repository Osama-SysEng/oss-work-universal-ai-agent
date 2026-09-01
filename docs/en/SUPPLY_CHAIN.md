# Supply-chain boundary

The supplemental archives are treated as references, not as automatically trusted source. The TimescaleDB repository remains an upstream database-extension project and is not copied into this application. The two Next.js archives contributed reviewed presentational ideas and a dependency manifest; their live API routes, seed data, and host-execution paths were not merged.

The web console pins a `pnpm-lock.yaml` file. Install with `pnpm install --frozen-lockfile --ignore-scripts` in a controlled build environment, review dependency advisories and licenses, generate an SBOM, and sign the resulting artifact. Runtime package installation remains disabled. A future update system should accept only signed artifacts with verified provenance and a tested rollback path.

The final ZIP intentionally excludes `node_modules`, `.next`, Python caches, runtime databases, logs, local secrets, and deployment secret files. Archive integrity and SHA-256 are checked during packaging, but a hash alone proves integrity of bytes, not that the source is free of vulnerabilities.
