! EXPECTED: UNSAFE
! HINT: loop-carried dependency
! CATEGORY: dependency_edge_case
! DESC: Classic recurrence — a(i) = a(i) + a(i-1)
!       Iteration i reads a(i-1) which is written by iteration i-1.
!       The subscript i-1 is IV-1, detected by isIVPlusOffset().
subroutine dep_shift1(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 2, n
    a(i) = a(i) + a(i-1)
  end do
end subroutine
