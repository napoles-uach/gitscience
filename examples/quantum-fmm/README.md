# Quantum-FMM occupancy GitScience exercise

This case study starts from the open direction in Berry et al., *Quantum
Simulation of Electronic Structure via Quantum Fast Multipole Method*, PRX
Quantum 7, 033025 (2026), DOI `10.1103/b2vn-zf6c`: bound the error of using the
simpler non-adaptive algorithm on a subspace of evenly distributed particles.

The graph deliberately separates four levels:

1. an assumed error bound for a non-adaptive FMM call on the capacity-limited
   subspace;
2. an abstract accumulation lemma checked by Lean;
3. an RDM occupancy-tail lemma that remains an open formal obligation;
4. a finite independent-occupancy calculation checked by the trusted
   `fmm_occupancy` plugin.

Run the complete staged demo from the repository root after installing
GitScience and making Lean available on `PATH`:

```bash
./examples/quantum-fmm/run-demo.sh /tmp/gitscience-quantum-fmm-demo
```

The occupancy verifier accepts only six bounded numeric fields and never runs
repository-supplied code. For the declared instance it computes finite binomial
tails and a union bound. It distinguishes:

- `B=Theta(eta)` with constant mean occupancy, where the fixed-slot near-field
  work is `B*c^2`;
- `B=Theta(eta/c)` with mean occupancy proportional to capacity, which requires
  a larger capacity;
- the inconsistent hybrid that reuses the constant-mean capacity after reducing
  the box count.

The successful numerical result remains `conditional_corroborated` because it
depends on an explicit independent-occupancy assumption. The dynamic control of
occupancy during kinetic steps and the generic spin-sector scope remain visible
as unresolved claims.
