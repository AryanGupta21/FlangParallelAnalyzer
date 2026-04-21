! reduction.f90
!
! Expected hint: !$OMP PARALLEL DO REDUCTION(+:total)
! Reason: 'total' is a scalar accumulator written as total = total + expr.
!         This is a classic reduction pattern — safe with the REDUCTION clause.

subroutine dot_product_manual(a, b, n, total)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n), b(n)
  real,    intent(out) :: total
  integer :: i

  total = 0.0
  do i = 1, n
    total = total + a(i) * b(i)
  end do

end subroutine dot_product_manual
