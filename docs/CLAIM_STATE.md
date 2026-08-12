# Canonical claim state

GitScience compiles each current claim revision into a deterministic
`gitscience-claim-state-v1` object before a human or LLM interprets it:

```text
versioned repository
        |
        v
deterministic claim-state compiler
        |
        +-- claim explain (human view)
        +-- claim state --json (machine view)
        +-- PhysicsIntern (advisory interpretation)
```

The compiler does not invoke a model and does not assign scientific truth. It
collects information already present in the repository and makes important
distinctions explicit:

- the exact claim and model revisions;
- the versioned study narrative and claim role, when declared;
- the transitive dependency closure and locked assumptions;
- the derived status and separate logical, computational, dependency,
  provenance, review, and revision dimensions;
- only integrity-valid evidence for the current claim hash;
- assertion outcomes normalized as `satisfied`, `failed`, or `indeterminate`;
- committed advisory reviews that target the current claim hash and retain a
  matching artifact digest;
- conditions, limitations, and open obligations;
- the research question, plain-language conclusion, scope summary, and
  remaining uncertainty;
- an interpretation policy stating that reviews cannot change status.

Inspect either representation with:

```bash
gitscience claim state GS-QT-0005 --json
gitscience claim explain GS-QT-0005
```

The JSON form is the integration boundary for agents, search indexes, and
future registry APIs. Its output is stable while repository contents remain
unchanged; it contains no compilation timestamp or model-generated field.

Study narrative is stored in `studies/STUDY_ID.yaml`, while claim-specific
narrative and `role` live in the claim record. These fields are explanatory:
they are versioned and exposed to agents, but they cannot alter derived status.
The `revision` dimension becomes `uncommitted` if the claim, model, or linked
study manifest has local changes.

Registry consumers should use the canonical exporter rather than assembling
claim summaries by hand:

```bash
gitscience registry export --claim GS-QT-0005 --output registry.json
```

Each study in that snapshot contains a complete `claim_index` plus coverage
metadata indicating how many claims have full states in the exported subset.

## Reading the dimensions

`logical` reports bundled formal-proof evidence independently from numerical
checks. `computational` reports finite verifier results without promoting them
to general proof. `dependencies` exposes unresolved assumptions, stale
premises, and missing revision locks. `provenance` reports whether selected
evidence and reviews are authenticated. `review` only reports the presence of
advisory opinions. `revision` warns when the claim or model has local changes.

The top-level `status.derived` remains the repository's concise state label.
For example, `conditional_corroborated` means that current computational
evidence satisfied its declared assertions, but at least one dependency is an
explicit assumption or otherwise unresolved.

## Trust boundary

The canonical object helps an LLM explain a scientific record; it does not make
the LLM a verifier. PhysicsIntern receives the same object emitted by `claim
state`, must preserve its scope and unresolved obligations, and writes an
advisory `RV-*` record. GitScience ignores that verdict when deriving claim
status. If no current integrity-valid evidence exists, a reviewer verdict of
`VERIFIED` or `REFUTED` is locally replaced with `INCONCLUSIVE` and the original
reported verdict remains in the review artifact for audit.
