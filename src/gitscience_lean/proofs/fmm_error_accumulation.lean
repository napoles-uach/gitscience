/-
  Abstract accumulation lemma for the quantum-FMM case study.

  A local error term may encode a good-subspace approximation error plus a
  bad-subspace tail contribution. This theorem proves only that local hybrid
  bounds accumulate by repeated addition. It does not establish the analytic
  local bound, an RDM tail estimate, or a physical occupancy model.
-/

structure ErrorBudget (Error : Type) where
  zero : Error
  add : Error -> Error -> Error
  le : Error -> Error -> Prop
  transitive : forall {a b c}, le a b -> le b c -> le a c
  add_mono_first : forall {a b}, le a b -> forall c, le (add a c) (add b c)

def accumulatedError {Error : Type} (budget : ErrorBudget Error)
    (stepError : Nat -> Error) : Nat -> Error
  | 0 => budget.zero
  | n + 1 => budget.add (accumulatedError budget stepError n) (stepError n)

theorem local_error_bounds_accumulate
    {Error : Type}
    (budget : ErrorBudget Error)
    (cumulative stepError : Nat -> Error)
    (initial : budget.le (cumulative 0) budget.zero)
    (step : forall n,
      budget.le (cumulative (n + 1)) (budget.add (cumulative n) (stepError n))) :
    forall steps,
      budget.le (cumulative steps) (accumulatedError budget stepError steps) := by
  intro steps
  induction steps with
  | zero => exact initial
  | succ n ih =>
      exact budget.transitive (step n) (budget.add_mono_first ih (stepError n))
