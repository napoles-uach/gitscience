/-
  Abstract bridge from scattering covariance to even transmission.

  This theorem does not establish that a particular physical model satisfies
  the assumptions. It verifies that the claimed transport symmetry follows
  from those assumptions without an additional logical step.
-/

structure TransportSymmetry (Twist Scattering Value : Type) where
  reverse : Twist -> Twist
  scattering : Twist -> Scattering
  transform : Scattering -> Scattering
  transmission : Scattering -> Value
  scattering_covariant : forall tau,
    scattering (reverse tau) = transform (scattering tau)
  transmission_invariant : forall matrix,
    transmission (transform matrix) = transmission matrix

theorem transport_symmetry_implies_even_transmission
    {Twist Scattering Value : Type}
    (system : TransportSymmetry Twist Scattering Value)
    (tau : Twist) :
    system.transmission (system.scattering (system.reverse tau)) =
      system.transmission (system.scattering tau) := by
  calc
    system.transmission (system.scattering (system.reverse tau)) =
        system.transmission (system.transform (system.scattering tau)) := by
          rw [system.scattering_covariant tau]
    _ = system.transmission (system.scattering tau) := by
          exact system.transmission_invariant (system.scattering tau)
