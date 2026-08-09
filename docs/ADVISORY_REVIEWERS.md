# Advisory reviewers

GitScience separates deterministic verification from scientific review.

- A verifier executes a predefined, inspectable experiment and may affect the
  derived status of a claim through integrity-valid `EV-*` evidence.
- A reviewer analyzes a bounded dossier and produces an `RV-*` opinion.
- A review is always marked `advisory: true` and
  `affects_claim_status: false`.
- Neither a human-looking name nor an LLM verdict authenticates a record.

## PhysicsIntern adapter

`gitscience_physics_intern` reuses PhysicsIntern's reviewer prompt and provider
layer. It does not import PhysicsIntern into the GitScience core. The adapter
starts a subprocess in a temporary directory, passes a JSON dossier as data,
sets no shell command, applies a timeout, and limits the accepted output size.

Install PhysicsIntern in the same environment and export the provider key
expected by its selected model. Then inspect and run a review:

```bash
gitscience review inspect GS-QT-0001 --with physics_intern
gitscience review GS-QT-0001 --with physics_intern --model MODEL_KEY
gitscience review show RV-000001
```

The concise command commits only the review record, its JSON artifact, and the
updated counter. `gitscience review run` leaves those files uncommitted.

PhysicsIntern is deliberately denied the verifier role. Its report can identify
weak assumptions, missing controls, inconsistent interpretation, or suspicious
evidence, but deterministic evidence and authenticated human approval remain
separate controls.
