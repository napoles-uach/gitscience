# GitScience local MVP

GitScience versions scientific claims and computational attestations in an
ordinary Git repository. The MVP is local and supports trusted
`kwant_transport`, `fmm_occupancy`, and `lean_formal` verifier plugins. The core is
verifier-independent and loads plugins through the `gitscience.verifiers`
entry-point group.

## Core invariants

1. A claim is a proposal, not a truth declaration.
2. Verification never edits the claim it evaluates.
3. Evidence references the exact claim and model commits and file hashes.
4. Uncommitted claim or model revisions cannot be verified.
5. Downloaded claims cannot provide Python or shell code to this verifier.
6. A status is derived from evidence for the current claim hash.
7. Human and LLM views consume the same deterministic canonical claim state.
8. An advisory reviewer cannot change derived status.

The derived statuses are:

| Evidence for current revision | Claim status |
|---|---|
| none | `proposed` |
| at least one inconclusive result | `inconclusive` |
| corroborating result for a numerical instance | `corroborated` |
| corroborating numerical result for a general claim | `supported` |
| at least one contradictory result | `contested` |
| successful formal proof with no unresolved premises | `proven` |
| successful result depending on an explicit assumption | `conditional_*` |
| dependency revision changed | `stale` |

These labels describe the repository record. They are not declarations of
scientific truth. In version `0.1.0`, evidence is integrity-checked but unsigned;
see [`SECURITY_MODEL.md`](SECURITY_MODEL.md) before automated ingestion.

## Repository layout

```text
.gitscience/config.json
topics/QT.yaml
models/helicoidal-ribbon-v1.yaml
claims/GS-QT-0001.yaml
evidence/EV-000001.json
artifacts/EV-000001.kwant.json
```

The evidence record contains the attestor's Git identity, repository `HEAD`,
claim/model commits and hashes, evaluated assertions, environment manifest,
verifier name and version, verifier source hashes, and the result-artifact hash.

## Commands

```text
gitscience init PATH [--name NAME]
gitscience topic create NAME --code CODE
gitscience topic list
gitscience model create MODEL_ID --from MODEL.yaml
gitscience claim create --from CLAIM.yaml
gitscience claim list
gitscience claim show CLAIM_ID
gitscience claim log CLAIM_ID
gitscience claim graph
gitscience claim obligations
gitscience claim relock CLAIM_ID
gitscience claim state CLAIM_ID [--json]
gitscience claim explain CLAIM_ID
gitscience verify CLAIM_ID [CLAIM_ID ...]       # verify and commit evidence
gitscience verify inspect CLAIM_ID
gitscience verify run CLAIM_ID [CLAIM_ID ...]   # leave evidence uncommitted
gitscience evidence show EVIDENCE_ID
gitscience evidence list [--claim CLAIM_ID]
gitscience review CLAIM_ID --with REVIEWER [--model MODEL]
gitscience audit [--claim CLAIM_ID] [--require-authenticated]
gitscience status
gitscience diff
gitscience log
gitscience commit -m MESSAGE
```

`claim create` can also prompt for title and statement when given `--topic`,
`--model`, and a YAML `--request`. Use repeated `--assertion` and `--condition`
options to complete that record.

The normal authoring loop is intentionally short:

```bash
gitscience claim create --from hypothesis.yaml
gitscience commit -m "Propose hypothesis"
gitscience verify GS-QT-0001
```

The final command performs all provenance checks, writes the full evidence
record, and commits only the evidence and artifacts it generated. Other working
tree changes are not included. `verify run` keeps the evidence uncommitted for
manual review, while `verify inspect` previews the trusted execution contract
without running it.

## Twisted-ribbon exercise

Create the Kwant environment first:

```bash
conda env create -f environments/kwant-transport.yml
conda activate gitscience-kwant
python -m pip install -e . --no-deps --no-build-isolation
```

Then follow the complete exercise in
[`examples/twisted-ribbon/README.md`](../examples/twisted-ribbon/README.md).
It creates four numerical-instance claims, commits them, executes Kwant,
writes independent evidence, and commits the corroboration. The first two test
paired-point symmetries. The third uses a structured small-twist sweep to test
whether the odd component of spin polarization is approximately linear in
`tau` over a declared finite interval. The fourth preregisters a symmetry
replication at a different energy and twist before computing its result.

The trusted Kwant plugin currently exposes two experiment contracts:

| Experiment | Purpose |
|---|---|
| `point_symmetry` | Compare `+tau`, `-tau`, zero twist, and zero SOC at one parameter point |
| `small_twist_scaling` | Fit paired small-twist data to declared linear/quadratic scaling tests |

The trusted `fmm_occupancy` plugin exposes one finite, schema-limited contract:

| Experiment | Purpose |
|---|---|
| `independent_occupancy_regimes` | Compute finite binomial occupancy tails for two valid box regimes and reject their inconsistent hybrid |

See [`examples/quantum-fmm/README.md`](../examples/quantum-fmm/README.md).

## Deliberate MVP limits

- No remote registry, search, fetch, or push abstraction; normal Git remotes can
  be used manually.
- No cryptographic attestation beyond Git's existing commit-signing facilities.
- Advisory LLM reviews exist, but no authenticated human-review workflow yet.
- No generic code-execution verifier; each plugin must define a restricted
  schema and a real isolation boundary where appropriate.
- No large-artifact object store.
- No automatic promotion from a numerical instance to a general claim.
