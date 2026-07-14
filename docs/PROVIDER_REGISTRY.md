# Provider registry

The local provider registry records immutable provider releases and their
conformance evidence. Discovery remains code-free: registry listing, auditing and
reconciliation parse manifests and receipts but never import provider modules.

```bash
fmr-registry --registry registry.json submit \
  manifest.json conformance.json package-receipt.json
fmr-registry --registry registry.json transition my-provider 1.0.0 active
fmr-registry --registry registry.json list
fmr-registry --registry registry.json audit
fmr-registry --registry registry.json reconcile
```

Submission verifies the provider manifest, passed conformance attestation and the
actual provider-bundle SHA-256. Reusing a provider ID and version with different
content is rejected. Only an available release with executable conformance can
be activated and exposed through `active_manifests()`.

Lifecycle states are `submitted`, `active`, `deprecated`, `incompatible` and
`withdrawn`. Records are retained across transitions. Audit recomputes manifest
and conformance hashes. Reconciliation marks submitted, active or deprecated
releases incompatible when evidence is corrupt or the runtime is unavailable;
it never silently activates or deletes a release.

This is a deterministic local registry and automation substrate. It is not a
public hosting service, trust marketplace, remote discovery protocol or signed
distribution channel. Those require separate operational acceptance.
