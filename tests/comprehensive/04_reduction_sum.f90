! EXPECTED: REDUCTION
! HINT: !$OMP PARALLEL DO REDUCTION(+:total)
! CATEGORY: reduction
! DESC: Classic dot-product sum — total += a(i)*b(i)
!       Scalar accumulator with additive reduction pattern.
subroutine reduction_sum(a, b, total, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n), b(n)
  real,    intent(inout) :: total
  integer :: i
  do i = 1, n
    total = total + a(i) * b(i)
  end do
end subroutine
