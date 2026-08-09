# Staged verification

GitScience locks every dependency to an exact Git commit, SHA-256 digest, and
path. Verification evidence repeats those references. A result therefore says
not only which claims it used, but which revisions of those claims it used.

Create and commit parent nodes before creating their children. For the formal
twisted-ribbon example, the workflow is intentionally staged:

```bash
gitscience claim create --from formal-graph/01-definition-model.yaml
gitscience commit -m "Define transport model"

gitscience claim create --from formal-graph/02-assumption-covariance.yaml
gitscience commit -m "Declare covariance assumption"

gitscience claim create --from formal-graph/03-lemma-even-transmission.yaml
gitscience commit -m "State transport lemma"
gitscience verify GS-QT-0003
```

The same sequence continues for the corollary and numerical proposition. Use
`gitscience claim obligations` to inspect unresolved premises.

If a dependency changes, every affected descendant becomes `stale`. Historical
evidence remains integrity-valid for its original revisions, but it no longer
determines current status. Recovery is also staged:

```bash
gitscience claim relock GS-QT-0003
gitscience commit -m "Relock lemma dependencies"
gitscience verify GS-QT-0003
```

Then relock each dependent corollary or numerical proposition in order. Explicit
assumptions are allowed as premises, but successful children receive conditional
statuses such as `conditional_proven` or `conditional_corroborated`.
