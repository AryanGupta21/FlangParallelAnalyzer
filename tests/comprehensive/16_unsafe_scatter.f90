! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — indirect/scatter write)
! CATEGORY: dependency_edge_case
! DESC: Indirect (gather/scatter) access — b(idx(i)) = a(i)
!       The subscript of b is not the loop IV but a value loaded from idx.
!       Phase 3 classifies it as "unknown"; Phase 5 conservative → UNSAFE.
!       Even though this could be safe if idx is a permutation, the pass
!       cannot verify that statically.
subroutine unsafe_scatter(a, b, idx, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer, intent(in)  :: idx(n)
  integer :: i
  do i = 1, n
    b(idx(i)) = a(i)
  end do
end subroutine
