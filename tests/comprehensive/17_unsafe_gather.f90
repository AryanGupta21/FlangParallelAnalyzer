! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — indirect/gather read)
! CATEGORY: dependency_edge_case
! DESC: Gather access — b(i) = a(idx(i))
!       The read subscript of a is data-dependent (not IV-derived).
!       Phase 3 sees an "unknown" subscript → Phase 5 conservative UNSAFE.
subroutine unsafe_gather(a, b, idx, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer, intent(in)  :: idx(n)
  integer :: i
  do i = 1, n
    b(i) = a(idx(i))
  end do
end subroutine
