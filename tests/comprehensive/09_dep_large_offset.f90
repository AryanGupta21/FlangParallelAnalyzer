! EXPECTED: UNSAFE
! HINT: loop-carried dependency
! CATEGORY: dependency_edge_case
! DESC: Large constant offset — a(i) = a(i-10) + 1.0
!       Even a stride-10 access creates a loop-carried dependence
!       (iteration i depends on iteration i-10).
!       isIVPlusOffset detects any nonzero constant k.
subroutine dep_large_offset(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 11, n
    a(i) = a(i-10) + 1.0
  end do
end subroutine
