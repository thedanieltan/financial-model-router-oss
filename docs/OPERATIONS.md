# Local execution operations

## Boundary

FMR keeps operational state outside immutable financial receipts. The SQLite
ledger records hashed cache keys, lifecycle states, timestamps and closed detail
codes. It does not store model inputs, resolved secrets or calculated values.

The local operational layer provides:

- WAL-backed cross-process idempotency with a 30-second busy timeout;
- append-only lifecycle events;
- explicit stale-claim recovery;
- hash-pinned, non-overwriting SQLite backups;
- dry-run-first managed-artifact retention;
- aggregate value-free operational status; and
- allowlisted environment secret resolution with provider error redaction.

## Status and recovery

```bash
fmr operations-status --ledger /var/lib/fmr/executions.sqlite3
fmr recover-executions \
  --ledger /var/lib/fmr/executions.sqlite3 \
  --stale-after 300
```

Recovery changes only claims older than the supplied threshold. Recovered claims
become `abandoned` and can be reclaimed by the original handoff and idempotency
key. Recovery never selects another provider.

## Backup

```bash
fmr backup-execution-ledger \
  --ledger /var/lib/fmr/executions.sqlite3 \
  /var/backups/fmr/executions-2026-07-14.sqlite3
```

FMR uses SQLite's online backup operation and refuses an existing destination.
The receipt contains the backup path, byte count and SHA-256, but no execution
payloads.

## Artifact retention

Preview first:

```bash
fmr prune-execution-artifacts \
  --ledger /var/lib/fmr/executions.sqlite3 \
  --managed-output-root /var/lib/fmr/outputs \
  --older-than 2592000
```

Apply the same selection with `--apply`. Only completed artifacts whose resolved
paths share one child directory beneath the configured managed root qualify.
External paths, the managed root itself and split directories are never removed.
Pruned ledger entries retain value-free lifecycle events but no cached result.

## Secrets

`EnvironmentSecretResolver` reads only an explicit allowlist, optionally beneath
an environment prefix. Missing and undeclared references fail closed. Secret
values are sent to the isolated provider process over standard input, rejected if
echoed in a provider receipt and redacted from provider error messages.

Production deployments should inject a different resolver for their secret
manager. Jobs, handoffs and receipts must continue to contain references only.

## Deployment acceptance

This operational layer supports a single-host local service and coordinated
processes sharing one SQLite filesystem. It is not a distributed scheduler.
Before declaring a deployment production-ready, operators must separately test
filesystem durability, backup restoration, retention scheduling, secret-manager
integration, process supervision and resource limits in their own environment.
Remote workers and multi-region coordination remain Phase 2.0 work.
