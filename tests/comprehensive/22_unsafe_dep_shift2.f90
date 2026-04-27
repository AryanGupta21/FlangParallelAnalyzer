! EXPECTED: UNSAFE
! HINT: loop-carried dependency
! CATEGORY: dependency_edge_case
! DESC: Two-step recurrence — a(i) = a(i-1) + a(i-2)
!       Fibonacci-like update; both i-1 and i-2 are constant-offset reads.
!       Either offset alone is enough for the UNSAFE verdict.
subroutine unsafe_dep_shift2(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 3, n
    a(i) = a(i-1) + a(i-2)
  end do
end subroutine
