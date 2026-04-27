! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — in-place update on same array)
! CATEGORY: dependency_edge_case
! DESC: In-place update using only i as subscript — a(i) = a(i) * 3.0
!       This is actually safe (same index read and written), but the tool
!       conservatively marks it UNSAFE because it sees the same array as
!       both R and W without being able to confirm the R precedes the W.
!       Known limitation: Phase 5 conservative fallback fires here.
subroutine dep_inplace(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 1, n
    a(i) = a(i) * 3.0
  end do
end subroutine
