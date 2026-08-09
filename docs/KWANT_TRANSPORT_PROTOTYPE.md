# GitScience Kwant verifier

## Scope

This plugin restricts computational evidence to two trusted, schema-limited
Kwant experiments. It is a case study for coherent two-terminal transport, not
a general executor for arbitrary scientific code.

## Effective model

The scattering region is a spinful square-lattice ribbon with `width * length`
sites and two orbitals per site. Lattice coordinates `(x, y)` are embedded in a
helicoid,

```text
r(x, y) = (x, y cos(tau x), y sin(tau x)).
```

Nearest-neighbor hopping is

```text
H_ij = -t I + i lambda sigma . (n_bar x d_hat),
```

where `d_hat` is the embedded bond direction and `n_bar` is the local surface
normal at the bond midpoint. The two semi-infinite leads are untwisted,
spin-independent, and use `sigma_x` as a conservation law. Kwant therefore
orders their spin blocks by the eigenvalues `-1, +1`, which defines the reported
`P_x` convention.

This is an effective geometry-sensitive model. It is not yet an atomistic
graphene or material-specific nanoribbon, and its conclusions must not be
silently generalized to one.

## Evidence contract

Each GitScience verification writes an `artifacts/EV-NNNNNN.kwant.json` file
containing:

- all input parameters and a schema/model version;
- runs at `+tau`, `-tau`, `tau=0`, and `SOC=0` when requested;
- total and spin-resolved transmission and `P_x`;
- Hamiltonian Hermiticity and S-matrix unitarity residuals;
- propagating mode counts for each conserved-spin lead block, lead matching,
  and consistency between total and spin-decomposed transmission;
- pass/fail evaluations using caller-specified tolerances.

The verifier limits dimensions and rejects unknown fields. It does not accept
source code, shell commands, paths, or arbitrary Kwant builders.

## Validated reference point

The integration test uses Kwant 1.5.0 with `width=8`, `length=24`, `energy=1`,
`tau=0.08`, `t=1`, and `lambda=0.1`. On macOS ARM with the conda-forge build it
gives

```text
T(+tau)  = 3.8566995151063668
P_x(+tau) = 0.0056559705341641744
```

The opposite twist agrees in transmission within `3e-14` and reverses the
polarization within `9e-16`. Hermiticity, unitarity, spin decomposition, and
lead-mode matching pass. These values are a regression reference for this
effective model, not a material prediction.

## Local setup

Kwant includes compiled extensions, so use the conda-forge environment instead
of a generic virtual environment:

```bash
conda env create -f environments/kwant-transport.yml
conda activate gitscience-kwant
python -m pip install -e . --no-deps --no-build-isolation
gitscience verify CLAIM_ID
```

Before scientific use, add parameter sweeps in energy, length, and width. A
single paired run checks one numerical instance; it does not establish a general
symmetry theorem or convergence to an infinite-system limit.

## Small-twist scaling experiment

The trusted plugin also supports `small_twist_scaling`. For the same effective
model and fixed energy, it evaluates paired runs at `+tau` and `-tau`, extracts
the odd component of `P_x`, and fits it to a line through the origin. As a
companion diagnostic, it fits the even component of total transmission to a
quadratic function of `tau`.

For `width=8`, `length=24`, `energy=1`, `t=1`, `lambda=0.1`, and
`tau=[0, 0.01, 0.02, 0.03, 0.04]`, Kwant 1.5.0 gives

```text
P_x,odd slope                         = 0.04665420434406064
normalized maximum linear residual   = 0.047063784701997624
T quadratic coefficient              = -10.360643458243565
relative maximum quadratic residual  = 0.030115177707239597
```

The claim accepts a normalized linear residual below `0.06`. It is explicitly
recorded as an exploratory finite-range numerical hypothesis: the calculation
corroborates this parameter instance, but does not prove an asymptotic law or
establish behavior outside the sampled interval.

## Preregistered energy replication

After validating the workflow, a new numerical-instance claim was committed
before its result was computed. It predicted that twist-reversal parity would
persist at the previously untested point `energy=0.6` and `tau=0.12`, using the
same `width=8`, `length=24`, and `lambda=0.1` model.

Kwant 1.5.0 produced

```text
T(+tau)    = 3.9592716429061494
T(-tau)    = 3.9592716429061503
P_x(+tau)  = 0.0007014064473184521
P_x(-tau)  = -0.0007014064473177790
```

The absolute transmission-parity residual was `8.88e-16`, and the
polarization-odd residual was `6.73e-16`; both passed the preregistered `1e-7`
tolerance. This corroborates a second finite parameter point and is stronger
methodologically than selecting a tolerance after viewing the run, but it still
does not establish the symmetry for every energy or geometry.
