# Local release qualification

FMR separates repository implementation evidence from deployment acceptance.
`fmr qualify-release` runs deterministic local gates and emits
`release-qualification.v1`. A passing implementation report does not make an
environment production-ready.

```bash
fmr qualify-release --output qualification.json
```

The implementation gates cover code-free provider discovery, a genuinely
competing executable family, packaged lifecycle contracts, the router/provider
dependency boundary, SQLite backup and restoration, legacy-ledger migration,
duplicate-claim exclusion, stale-claim recovery and fail-closed secret
references.

The ordinary command exits successfully when implementation gates pass. A
production gate is explicit:

```bash
fmr qualify-release \
  --deployment-evidence deployment-evidence.json \
  --require-production \
  --output qualification.json
```

Production acceptance requires evidence for all of:

- filesystem durability;
- a backup restoration drill;
- process supervision and restart behavior;
- resource and timeout limits;
- deployment secret-manager integration;
- a security review; and
- operator acceptance.

Each evidence item has a status and a durable reference to an external report,
ticket or immutable artifact. FMR validates those declarations but cannot prove
that an operator actually performed an environmental test. False evidence is an
operational governance failure, not something software can infer away.

The packaged template is
`fmr.fixtures/deployment-acceptance-evidence.template.json`. Production remains
blocked while the package version is an alpha version, even if every deployment
gate is declared passed. Stable version promotion is a separate, reviewable
release action.

## Upgrade and rollback procedure

1. Back up the execution ledger and verify the receipt hash.
2. Retain the installed wheel and configuration currently serving traffic.
3. Install the candidate wheel into a new environment.
4. Run `qualify-release` and the provider lifecycle smoke test against a copy of
   the ledger.
5. Stop new execution claims, allow active work to finish, and switch the
   supervised process to the candidate environment.
6. If startup or qualification fails, restore the previous environment and the
   pre-upgrade ledger backup. Never downgrade a live ledger without the tested
   backup.
7. Record the drill under `backup_restore_drill` and `process_supervision`.

Remote workers, distributed locking and multi-region recovery are outside this
local qualification and remain Phase 2 work.
