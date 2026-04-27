! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Read-only traversal — prints nothing, just searches for maximum
!       value stored in a local scalar that is re-initialized each iteration.
!       No external writes at all → Phase 5 conservative fallback fires SAFE.
!       NOTE: This is a read-only loop (no INTENT(OUT) array writes).
subroutine safe_read_only(a, n, found)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  integer, intent(out) :: found
  integer :: i
  found = 0
  do i = 1, n
    if (a(i) > 0.0) found = 1
  end do
end subroutine
