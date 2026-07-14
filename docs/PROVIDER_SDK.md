# Provider SDK

The Provider SDK is the public authoring path for local FMR providers. It keeps
manifest discovery code-free: `validate` reads JSON and TOML but never imports a
provider module. Provider code loads only during the explicit `test` command and
only through installed Python entry points.

## Start a provider

```bash
fmr-provider init my-provider ./my-provider
cd ./my-provider
python -m pip install -e .
fmr-provider validate .
fmr-provider test .
fmr-provider package . --destination dist
```

The scaffold is a complete handoff-only example with:

- a strict provider and model-package manifest;
- typed adapter and executor implementations;
- declared adapter and executor entry points;
- a synthetic provider-neutral fixture; and
- a value-free, hash-pinned provider receipt.

Replace the example package contract and implementation with the real provider.
Do not advertise a family, deliverable, format or validation check until the
executable conformance fixture proves it.

## Validation levels

`fmr-provider validate` performs static checks only. It validates the manifest,
registered family IDs, declared entry-point names and an optional version
transition. It is safe to run on untrusted source because it does not import it.

`fmr-provider test` is an explicit code-execution boundary. It loads the installed
adapter and executor, routes the synthetic fixture, compiles and validates the
handoff, runs the provider in the isolated provider process, checks artifacts and
then repeats the request to prove durable idempotency.

## Version and deprecation rules

Provider and package versions are pinned semantic versions. Versions never move
backwards. Removing packages or changing execution mode or executor requires a
provider major-version bump. Changing a package family or adapter, removing a
deliverable or output artifact, or adding mandatory data or assumptions requires
a package major-version bump.

Providers should announce deprecation before a major removal and retain the old
manifest and package version through the declared support window. Registry
lifecycle and automated deprecation enforcement belong to Phase 1.2.

Validate a release transition with:

```bash
fmr-provider validate . --previous-manifest previous-manifest.json
```

## Packaging

`fmr-provider package` first performs static validation and then creates a
deterministic ZIP submission bundle. It excludes Git metadata, virtual
environments, caches and existing distribution directories; refuses to overwrite
an existing archive; and emits its SHA-256, size and member count. A bundle is a
registry submission artifact, not proof of executable conformance or registry
approval.
