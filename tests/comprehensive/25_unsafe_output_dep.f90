! EXPECTED: UNSAFE
! HINT: loop-carried dependency (output dependency — write to fixed index)
! CATEGORY: dependency_edge_case
! DESC: Multiple iterations write to the same location — max_val = max(max_val, a(i))
!       Without a REDUCTION clause this is a classic output dependency / race.
!       The pass sees max_val (a scalar function arg) as RW but the binary op
!       is not addf/addi/mulf/muli, so Phase 4 doesn't match it.
!       Phase 5 conservative → UNSAFE.
subroutine unsafe_output_dep(a, max_val, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(in)    :: a(n)
  real,    intent(inout) :: max_val
  integer :: i
  do i = 1, n
    if (a(i) > max_val) max_val = a(i)
  end do
end subroutine
