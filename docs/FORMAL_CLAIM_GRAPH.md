# Formal claim graph

GitScience claims may be definitions, assumptions, lemmas, propositions,
theorems, corollaries, conjectures, or numerical propositions. `depends_on`
turns these records into a directed argument graph. Dependencies must exist
before a new node is created, which prevents dangling references and cycles in
the creation workflow.

A statement can carry both natural language and LaTeX:

```yaml
kind: lemma
statement:
  natural_language: Scattering covariance implies even transmission.
  latex: |
    \mathcal S_{-\tau}=\Phi(\mathcal S_\tau)
    \Longrightarrow T(E,-\tau)=T(E,\tau).
depends_on: [GS-QT-0001, GS-QT-0002]
```

Formal, computational, and scientific status remain separate. Lean proves a
logical implication from explicit assumptions. Kwant tests numerical instances.
Neither establishes that the assumptions adequately describe a physical
material; that obligation remains visible for scientific review.

Status is local to each node. GitScience does not promote a corollary merely
because one parent lemma is proven: unresolved assumptions remain visible and
must receive their own evidence or human acceptance policy.

The `lean_formal` verifier accepts only proofs bundled with its plugin. This
restriction avoids treating arbitrary repository-supplied Lean metaprograms as
safe data. The first proof is
`twist_transport_symmetry.lean`: covariance of the scattering representation
plus invariance of the transmission functional implies even transmission.

The prototype pins Lean `v4.32.2` in `lean-toolchain`. Install it with `elan`
and make the selected `lean` executable available on `PATH` before running a
formal verification.

The example files in `examples/twisted-ribbon/formal-graph` must be created in
numeric order, with a commit after each node so that the next node can lock its
dependency revisions. Their generated IDs form this chain:

```text
GS-QT-0001 definition
  -> GS-QT-0002 assumption
       -> GS-QT-0003 lemma (Lean)
            -> GS-QT-0004 corollary
                 -> GS-QT-0005 numerical proposition (Kwant)
```

After creating and committing the nodes, run the two independent checks:

```bash
gitscience verify GS-QT-0003
gitscience verify GS-QT-0005
gitscience claim graph
```

The expected distinction is `lemma: conditional_proven`, `corollary:
conditional`, and `numerical_proposition: conditional_corroborated` while the
physical covariance remains an explicit assumption. See
`docs/STAGED_VERIFICATION.md` for invalidation and relocking.
