# Guided scoping

FMR separates the user's business intent from the executable modelling job. A
workbook can provide evidence about statements, schedules and assumptions, but
it cannot establish why the user opened it or what decision they need to make.

The guided lifecycle is:

1. create a canonical `model-intent.v1`;
2. produce one or more `model-scope-candidate.v1` records;
3. return a hash-pinned `model-scope-assessment.v1`;
4. collect an explicit `scope-confirmation.v1`; and
5. carry that confirmation into `model-job.v2`, where it becomes part of every
   downstream route, handoff and execution hash.

Assessment evidence is categorical (`eligible`, `possible`, `blocked` or
`unsupported`). FMR does not manufacture probabilistic confidence scores. A
candidate is not selected merely because a provider can execute it.

Direct expert jobs remain supported. The confirmation requirement applies when
the guided lifecycle is used; an unconfirmed assessment cannot be promoted by
silently constructing a confirmation object.

WP-GUX-23 establishes these contracts and integrity boundaries. Family
playbooks, deterministic questions, workbook evidence and user interfaces are
delivered in the subsequent guided-scoping work packages.
