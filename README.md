# GitScience

GitScience is a local, Git-native prototype for publishing scientific claims
with explicit assumptions, formal proofs, computational evidence, and review
history. It does not certify scientific truth. It makes the structure and
provenance of an argument inspectable, reproducible, and correctable.

## What works today

- Direct numerical claims verified by a schema-limited Kwant plugin.
- Finite independent-occupancy tails checked by a schema-limited quantum-FMM plugin.
- Staged graphs with exact dependency-revision locks.
- Bundled formal implications checked by Lean `4.32.2`.
- Conditional statuses and transitive `stale` propagation when a premise changes.
- A deterministic canonical claim state for human and LLM interpretation.
- Optional advisory review through an external PhysicsIntern + LLM process.
- Integrity auditing, adversarial tests, and explicit unsigned-evidence warnings.

The reference cases study coherent transport in a helicoidal ribbon and
occupancy-controlled quantum fast multipole methods. The test suite includes
real Kwant integration when Kwant is installed.

The repository currently contains five Python packages:

- `gitscience`: claim, evidence, provenance, Git, and CLI operations;
- `gitscience_fmm`: a trusted finite-binomial occupancy-tail verifier;
- `gitscience_kwant`: a trusted verifier plugin for the helicoidal-ribbon case
  study.
- `gitscience_lean`: a trusted verifier for bundled Lean proof obligations.
- `gitscience_physics_intern`: an optional advisory reviewer that invokes an
  installed PhysicsIntern in an isolated subprocess.

The core discovers verifiers through the `gitscience.verifiers` entry-point
group. A verifier owns its request schema, supported experiments, assertions,
execution, artifact suffix, and provenance files.

## Install

Kwant contains compiled extensions, so use the provided conda-forge
environment:

```bash
conda env create -f environments/kwant-transport.yml
conda activate gitscience-kwant
python -m pip install -e . --no-deps --no-build-isolation
```

The formal example also needs Lean through
[elan](https://github.com/leanprover/elan). The repository pins the toolchain in
`lean-toolchain`.

## Reproducible demo

After activating the environment and making `lean` available on `PATH`:

```bash
./examples/twisted-ribbon/run-formal-demo.sh
./examples/quantum-fmm/run-demo.sh
```

Each script creates a separate repository under `/tmp`, commits every scientific
step, checks a lemma with Lean, checks a numerical proposition with Kwant, and
audits the generated evidence. Its final graph distinguishes:

```text
definition             declared
assumption             declared
lemma                  conditional_proven
corollary               conditional
numerical proposition  conditional_corroborated
```

Those conditional labels are deliberate: Lean proves an implication from an
explicit covariance assumption; it does not establish that the Hamiltonian and
leads satisfy that assumption.

## Direct workflow

From this repository root:

```bash
gitscience init /tmp/twisted-ribbon-science --name twisted-ribbon-study
gitscience -C /tmp/twisted-ribbon-science topic create \
  "Quantum transport in twisted ribbons" --code QT
gitscience -C /tmp/twisted-ribbon-science model create \
  helicoidal-ribbon-v1 --from examples/twisted-ribbon/model.yaml
gitscience -C /tmp/twisted-ribbon-science claim create \
  --from examples/twisted-ribbon/claim-energy-replication.yaml
gitscience -C /tmp/twisted-ribbon-science commit \
  -m "Propose energy-replication hypothesis"
gitscience -C /tmp/twisted-ribbon-science verify GS-QT-0001
gitscience -C /tmp/twisted-ribbon-science claim explain GS-QT-0001
gitscience -C /tmp/twisted-ribbon-science review GS-QT-0001 \
  --with physics_intern --model YOUR_PHYSICS_INTERN_MODEL
```

The concise `verify` command validates committed inputs, executes the installed
verifier, records hashes and environment metadata, and commits only the
generated evidence. Use `verify run` to leave evidence uncommitted for manual
review.

`claim state CLAIM_ID --json` deterministically compiles the claim, model,
dependency closure, normalized assertion outcomes, derived status dimensions,
scope limits, provenance, reviews, and open obligations. `claim explain`
renders a concise human view from that same object. See the
[canonical claim-state contract](docs/CLAIM_STATE.md).

The optional `review` command sends that canonical state to PhysicsIntern. It
records an `RV-*` report and its provenance, but that report is explicitly
advisory: it cannot authenticate evidence or change claim status. A review can
interpret a proposed claim with no evidence, but GitScience forces its verdict
to `INCONCLUSIVE` if the reviewer attempts `VERIFIED` or `REFUTED` in that
state. PhysicsIntern must be installed in the active Python environment and its
provider API key must already be exported.

## Formal argument graph

Claims can be typed as definitions, assumptions, lemmas, propositions,
theorems, corollaries, conjectures, or numerical propositions. Natural-language
and LaTeX statements coexist with explicit `depends_on` edges:

```bash
gitscience -C /tmp/twisted-ribbon-science claim graph
```

The bundled `lean_formal` verifier checks a logical bridge from scattering
covariance to even transmission. Kwant separately checks a finite numerical
instance. See [the formal graph prototype](docs/FORMAL_CLAIM_GRAPH.md).
The [staged verification workflow](docs/STAGED_VERIFICATION.md) explains
revision locks, conditional status, invalidation, and recovery.

## Staged workflow

Claims with `depends_on` edges lock every dependency to a Git commit and SHA-256
digest. Changing a premise makes affected descendants `stale`; historical
evidence remains valid for its original revisions.

```bash
gitscience claim obligations
gitscience claim relock GS-QT-0003
gitscience commit -m "Relock lemma dependencies"
gitscience verify GS-QT-0003
```

See [the MVP contract](docs/GITSCIENCE_MVP.md), the
[twisted-ribbon exercise](examples/twisted-ribbon/README.md), and the
[quantum-FMM occupancy exercise](examples/quantum-fmm/README.md). The
[security model](docs/SECURITY_MODEL.md) explains the boundary between
integrity, authentication, and scientific validity.

## Product validation

The reproducible [validation protocol](validation/README.md) rebuilds both case
studies and tests whether canonical state exposes assumptions, finite scope,
provenance, and prohibited generalizations. The
[initial report](docs/VALIDATION_REPORT.md) records 21/21 passing structural
checks after the protocol uncovered and prompted correction of an important
formal-verification classification bug. External human replication and blinded
LLM comparison remain explicitly pending.

## Prototype boundaries

- Evidence is unsigned and cannot authenticate its author or runner.
- The Lean theorem is an abstract bridge, not yet a matrix-level theorem derived
  from the implemented Hamiltonian.
- Correspondence between LaTeX, Lean, and Kwant is recorded but not formally
  verified.
- PhysicsIntern reviews are advisory and cannot change claim status.
- This is research software, not a production scientific registry.
