# Security Policy

## Supported release

Security reports should identify the release version, operating system, Python version, reproduction steps, and impact. Do not include secrets or personal data in an issue.

## Safe defaults

The release is simulation-first. Code execution and automatic package or update installation are disabled. Filesystem mutations require approval and remain confined to the configured root. External actions are not attempted.

## Before production use

Operators must review dependencies, configure a secret manager, isolate the service account, define retention and backup policies, add authentication and authorization, run static and dynamic security testing, and validate rollback in staging. A third-party security review is recommended for any live provider adapter.
