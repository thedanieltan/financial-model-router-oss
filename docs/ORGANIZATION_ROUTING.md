# Organization-specific routing

`organization-routing-policy.v1` is an administrative overlay applied after the user job and base routing policy are parsed. A job cannot weaken it.

The policy supports private provider-manifest directories, private declarative vocabularies, provider allowlists and precedence, approved provider and package versions, local-only execution, prohibited execution modes, company template approval, and an audit-retention requirement. Every effective control is embedded in the route decision and covered by its deterministic ID and the downstream handoff hash chain.

```console
fmr route-job job.json --policy default \
  --organization-policy organization-policy.json --output decision.json
fmr prepare-handoff job.json \
  --organization-policy organization-policy.json --output handoff.json
```

Private provider discovery remains code-free. Provider adapter and executor code is loaded only after selection through installed entry points. A private manifest without its installed implementation can be evaluated, but cannot become executable.

Private vocabulary files use `industry-vocabulary.v1` and exact alias normalization. Conflicting IDs or aliases fail closed.

`audit_retention_days` is a routed governance requirement, not an automatic deletion schedule. Deployment operators must configure execution-ledger and artifact retention to meet or exceed it; FMR does not silently prune audit records.
