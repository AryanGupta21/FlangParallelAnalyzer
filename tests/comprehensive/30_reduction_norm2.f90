! EXPECTED: REDUCTION
! HINT: !$OMP PARALLEL DO REDUCTION(+:norm2)
! CATEGORY: reduction
! DESC: L2-norm squared — norm2 += a(i)*a(i)
!       A self-dot-product; only one input array, multiply then accumulate.
!       Tests that the mulf->addf chain (squaring then summing) is recognised
!       as a reduction rather than misclassified.
subroutine reduction_norm2(a, norm2, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(in)    :: a(n)
  real,    intent(inout) :: norm2
  integer :: i
  do i = 1, n
    norm2 = norm2 + a(i) * a(i)
  end do
end subroutine
