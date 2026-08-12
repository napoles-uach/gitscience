# Twisted-ribbon GitScience exercise

From the GitScience repository root, create a separate scientific repository:

```bash
gitscience init /tmp/twisted-ribbon-science --name twisted-ribbon-study
gitscience -C /tmp/twisted-ribbon-science topic create \
  "Quantum transport in twisted ribbons" --code QT
gitscience -C /tmp/twisted-ribbon-science model create \
  helicoidal-ribbon-v1 --from examples/twisted-ribbon/model.yaml
gitscience -C /tmp/twisted-ribbon-science study create \
  twisted-ribbon --from examples/twisted-ribbon/study.yaml
gitscience -C /tmp/twisted-ribbon-science claim create \
  --from examples/twisted-ribbon/claim-transmission.yaml
gitscience -C /tmp/twisted-ribbon-science claim create \
  --from examples/twisted-ribbon/claim-polarization.yaml
gitscience -C /tmp/twisted-ribbon-science claim create \
  --from examples/twisted-ribbon/claim-small-twist-linearity.yaml
gitscience -C /tmp/twisted-ribbon-science claim create \
  --from examples/twisted-ribbon/claim-energy-replication.yaml
```

The source paths above are resolved by the shell, so use absolute paths if the
commands are run outside the GitScience root. Configure a Git identity in the
new repository if needed, then commit the proposal:

```bash
gitscience -C /tmp/twisted-ribbon-science status
gitscience -C /tmp/twisted-ribbon-science commit \
  -m "Propose twisted-ribbon reference claims"
```

Inspect and run the trusted verification:

```bash
gitscience -C /tmp/twisted-ribbon-science verify inspect GS-QT-0001
gitscience -C /tmp/twisted-ribbon-science verify \
  GS-QT-0001 GS-QT-0002 GS-QT-0003 GS-QT-0004
gitscience -C /tmp/twisted-ribbon-science evidence show EV-000001
```

Verification refuses uncommitted claim or model revisions. Evidence records
the exact Git commits, file hashes, environment manifest, evaluated assertions,
and hash of the full Kwant result artifact. The concise `verify` command commits
only its generated evidence; use `verify run` to inspect and commit it manually.

## Formal graph variant

The files in `formal-graph/` express the same study as a definition, an explicit
physical assumption, a Lean-checked lemma, a conditional corollary, and a
Kwant-checked numerical proposition. Create them in numeric order in a fresh
repository, commit them, and run:

```bash
gitscience verify GS-QT-0003
gitscience verify GS-QT-0005
gitscience claim graph
gitscience registry export --claim GS-QT-0003 --claim GS-QT-0005 \
  --output twisted-ribbon-registry.json
```

Lean proves only the implication encoded by the lemma. The model-specific
scattering covariance remains an explicit assumption rather than being hidden
inside the formal verdict.
The exported registry discloses that the two full claim states are a curated
subset of the five-node study graph.
