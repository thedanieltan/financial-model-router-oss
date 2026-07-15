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

WP-GUX-23 establishes these contracts and integrity boundaries. WP-GUX-24 adds
the built-in `fmr.knowledge` registry with one provider-neutral playbook for each
initial family, five plain-language questions and a provenance registry.

WP-GUX-25 adds the deterministic assessment engine:

- `assess_model_intent` compares decision context and requested outcomes with
  the versioned playbooks, reports missing data and assumptions, and returns
  clarification, candidate, unsupported or contradictory states;
- `answer_scope_question` records only controlled answers and reissues the
  hash-pinned intent;
- prerequisites are fail-closed: for example, an operating-company DCF is
  blocked until a supported operating forecast is explicitly available; and
- `compile_confirmed_scope` accepts only an intact, explicitly confirmed
  selectable candidate and creates a provider-neutral `model-job.v2`.

Scoping never discovers providers. Provider availability therefore cannot turn
an unsuitable model family into a recommendation. Routing begins only after the
user confirms scope. Missing data and assumptions remain requirements; they are
not inferred from a workbook or invented by the engine.

WP-GUX-26 adds `model-scope-workbook-evidence.v1`. It converts a trusted
`workbook-map.v1` into hash-pinned observations about data concepts and workbook
capabilities. Applying that evidence requires deterministic recomputation from
the original workbook map. It may add observed data and a source reference to an
intent, but it preserves the objective, decision context, requested outcomes and
assumptions exactly. External links are warnings, and workbook structure never
establishes user intent.

Built-in playbooks are marked `synthetic_reviewed`, not
`practitioner_accepted`. FAST and ICAEW materials inform modelling-quality
provenance; they are not treated as automatic family-selection rules. SEC data
is referenced only for representative statement shapes. No third-party
workbooks are bundled.
