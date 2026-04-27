! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — multi-dimensional index)
! CATEGORY: control_flow_complexity
! DESC: Doubly-nested matrix loop — c(i,j) = a(i,j) + b(i,j)
!       The outer loop sees the inner DO as a nested op; the inner loop's
!       subscripts include the outer IV which appears as an "unknown" index
!       from the inner loop's perspective.  Both loops end up UNSAFE
!       (conservative, known limitation).
subroutine nested_outer(a, b, c, m, n)
  implicit none
  integer, intent(in)  :: m, n
  real,    intent(in)  :: a(m,n), b(m,n)
  real,    intent(out) :: c(m,n)
  integer :: i, j
  do i = 1, m
    do j = 1, n
      c(i,j) = a(i,j) + b(i,j)
    end do
  end do
end subroutine
