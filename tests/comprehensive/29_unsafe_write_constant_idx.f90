! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — write to non-IV index)
! CATEGORY: dependency_edge_case
! DESC: Write to a constant index — b(1) = b(1) + a(i)
!       All iterations write to b(1); this is an output dependency / race.
!       The subscript '1' is a constant, not IV-derived → unknown subscript
!       in Phase 3 → Phase 5 conservative UNSAFE.
subroutine unsafe_write_constant_idx(a, b, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(in)    :: a(n)
  real,    intent(inout) :: b(n)
  integer :: i
  do i = 1, n
    b(1) = b(1) + a(i)
  end do
end subroutine
