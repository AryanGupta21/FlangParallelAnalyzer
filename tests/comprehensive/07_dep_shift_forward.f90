! EXPECTED: UNSAFE
! HINT: loop-carried dependency
! CATEGORY: dependency_edge_case
! DESC: Forward-shift write — a(i+1) = a(i) * 2.0
!       Iteration i writes a(i+1); iteration i+1 reads a(i+1).
!       Subscript i+1 is IV+1, same offset detection path.
subroutine dep_shift_forward(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 1, n-1
    a(i+1) = a(i) * 2.0
  end do
end subroutine
