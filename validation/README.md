# GitScience product validation

This directory tests whether GitScience improves scientific interpretation,
not merely whether its software executes. The first protocol uses two existing
case studies and freezes the current feature set while gathering evidence.

## Questions

1. Does canonical state expose a limitation that a successful computation can
   otherwise hide?
2. Can a reader distinguish formal implication, numerical corroboration,
   physical assumption, and unresolved scope?
3. Does the record avoid promoting a finite result into a general conclusion?
4. Is the same interpretation packet deterministic and machine-readable?
5. What important questions remain absent from the verification contract?

## Cases and preregistered traps

The twisted-ribbon case must not turn one Kwant comparison into a general proof.
It must expose the unproved covariance assumption beneath the Lean implication.
The protocol also asks whether nontrivial transmission was a declared assertion
rather than merely an observed artifact value.

The quantum-FMM case must preserve the meaning of the negative-sounding
`hybrid_regime_exceeds_tail_budget` assertion: a satisfied assertion rejects the
hybrid construction. It must not convert an independent-binomial calculation
into an asymptotic theorem or a claim about generic fermionic states.

## Automated structural gate

Run both studies from clean repositories and compile their canonical states:

```bash
./validation/run-validation.sh /tmp/gitscience-product-validation
```

The command reruns Lean, Kwant, and the finite occupancy verifier before writing
`report.json`. Every structural check must pass. Known blind spots are retained
in the report rather than counted as successes.

## Human and LLM arms

Structural checks cannot establish usefulness by themselves. The next study
should give independent readers either a conventional result package or the
canonical state, without telling them the expected answer. Ask each reader to:

- classify the epistemic status;
- list assumptions and scope limits;
- explain what the computation establishes;
- identify at least one plausible overinterpretation;
- state what additional test they would request.

Measure fact recall, false generalizations, unsupported `verified` judgments,
completion time, and confidence. Repeat the same blinded prompt with at least
two LLM providers or model families. The external arms remain `pending` until
real participants or model calls are recorded; this repository does not
fabricate those results.

## Decision rule

Continue as a research prototype only if the structural gate passes and the
canonical-state arm later reduces false generalizations or improves assumption
recall without unreasonable authoring cost. Otherwise simplify the schema to
claim, scope, executable evidence, and limitations.
