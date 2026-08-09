# GitScience security model

GitScience separates evidence integrity from evidence authenticity. Neither one
is equivalent to scientific truth.

## Integrity checks

`gitscience audit` verifies that:

- evidence and artifacts are committed and have no working-tree modifications;
- artifact, claim, model, and environment hashes match;
- dependency claim blobs match their locked commits and hashes;
- claim and model blobs exist at their recorded Git commits;
- evidence and artifact were committed together;
- the verification request and assertions match the current claim revision;
- evaluations match the artifact contents;
- the stored classification can be derived from those evaluations;
- repository paths cannot escape their expected directories.

Evidence that fails these checks cannot affect a claim's derived status.

## Authentication boundary

Version `0.1.0` does not yet implement cryptographic attestation. Evidence is
recorded with `authentication.method: none`, and the audit reports a warning.

An attacker who controls a repository can fabricate an internally consistent
artifact, evidence record, hashes, environment description, and Git commit.
That forgery passes integrity checks because Git proves that bytes were
versioned, not that a trusted computation produced them.

Use the strict policy when evidence authenticity is required:

```bash
gitscience audit --require-authenticated
```

This command currently fails for all unsigned MVP evidence. It is intended as a
safe gate for automated ingestion: an LLM or registry must not silently treat
unsigned local evidence as authenticated.

The audit never trusts an `authenticated: true` field by itself. Until a
signature-verification method is implemented, any claimed authentication method
other than `none` is rejected as unverifiable.

## Threats outside the MVP

The current implementation does not protect against:

- a malicious repository owner creating coherent fake evidence;
- a malicious or replaced verifier plugin;
- a compromised execution machine;
- rewritten Git history or impersonated Git author metadata;
- a scientifically incorrect model that produces numerically consistent data.
- an advisory review being mistaken for authenticated scientific approval;

A production trust layer should add signed attestations from configured keys,
protected CI identities, hash-pinned verifier environments, independent
reproductions, and optionally a transparency log. Statuses such as
`corroborated` describe the repository record; they are not declarations of
truth or authentication.
