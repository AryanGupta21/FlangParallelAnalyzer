! EXPECTED: REDUCTION
! HINT: !$OMP PARALLEL DO REDUCTION(+:s)
! CATEGORY: reduction
! DESC: SAXPY-style sum reduction — s += alpha*x(i) + y(i)
!       The accumulator s is a scalar function argument; the RHS reads two
!       separate arrays with IV indexing.  Phase 4 matches the addf chain.
subroutine reduction_saxpy_sum(x, y, s, alpha, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(in)    :: x(n), y(n), alpha
  real,    intent(inout) :: s
  integer :: i
  do i = 1, n
    s = s + alpha * x(i) + y(i)
  end do
end subroutine
