# Initial product-validation report

Date: 2026-08-10

This evaluation asks whether GitScience exposes scientific qualifications that
can be hidden behind a successful computation. It is a product validation, not
a certification of the underlying physics.

## Execution

Both staged repositories were regenerated from empty directories. The protocol
then reran the bundled Lean proofs, the Kwant reference calculation, and the
finite quantum-FMM occupancy calculation before compiling canonical claim
state. The machine-readable baseline is
[`validation/results/2026-08-10.json`](../validation/results/2026-08-10.json).

The first clean run failed one of 21 structural checks. `elan` could not access
its home directory in the execution sandbox, and the Lean adapter incorrectly
classified elaboration failure as contradictory evidence. This exposed a real
epistemic bug: failure to find or execute a proof does not establish the
negation of a theorem. The adapter now reports `passes: null`, producing
`inconclusive`; contradiction would require a separate trusted proof of the
negated claim.

After setting the isolated `ELAN_HOME` and rerunning from new repositories, all
21 structural checks passed.

## What the state revealed

For the twisted ribbon, GitScience preserves the distinction among a
Kwant-corroborated numerical instance, an abstract Lean implication, and the
unproved physical covariance assumption. The final status is
`conditional_corroborated`, not `proven`. The artifact also shows nontrivial
transmission near 3.8567 in both directions, but nontriviality was not a
preregistered assertion. The model-to-code-to-Lean correspondence and behavior
across energies, geometries, and discretizations remain open.

For quantum FMM, the state preserves the independent-occupancy assumption and
the finite numerical scope. It records that the inconsistent hybrid has bad
probability bound 1.0 against a required maximum of `6.25e-8`, while the two
internally consistent regimes meet the budget. It does not connect that finite
diagnostic falsely to the general FMM corollary or promote it to an asymptotic
or generic fermionic statement.

## Decision

The current evidence supports continuing GitScience as a research prototype.
It does not yet establish adoption value. Independent human replication and a
blinded comparison of conventional versus canonical-state LLM interpretation
remain pending. Feature expansion should stay paused until at least one of
those external arms shows better assumption recall or fewer false
generalizations at acceptable authoring cost.

Reproduce the structural evaluation with:

```bash
ELAN_HOME=/path/to/elan-home \
./validation/run-validation.sh /tmp/gitscience-product-validation
```
