# Model acceptance

`model-acceptance-corpus.v1` packages synthetic or anonymized canonical inputs,
provider-neutral jobs and explicit output assertions. `fmr
run-acceptance-corpus` routes and executes every case through the normal handoff
and artifact-validation lifecycle.

Acceptance results contain hashes, package identities and assertion pass/fail
states. They do not copy financial values into the evidence ledger.

```bash
fmr run-acceptance-corpus corpus.json --output acceptance.json
fmr run-acceptance-corpus corpus.json --require-practitioner
```

Synthetic cases can prove implementation behavior but can never satisfy the
production gate. Production acceptance additionally requires at least one
representative anonymized case and an accepted review for every family in the
corpus. Reviews record a role and an external evidence reference, not a person's
identity or financial data.

FMR validates the structure and coverage of review declarations. It cannot
prove that an external reviewer is qualified or that an evidence URI is honest;
those remain owner and deployment governance responsibilities.

The bundled `synthetic-initial-families.v1.json` corpus exercises all five
executable Python Forecast packages: generic budget, SaaS budget, integrated
three-statement, operating-company DCF and debt-capacity/refinancing. Its
value-free result is suitable as an implementation review packet, but it remains
synthetic evidence and therefore cannot satisfy the production gate.
