! EXPECTED: REDUCTION
! HINT: !$OMP PARALLEL DO REDUCTION(*:prod)
! CATEGORY: reduction
! DESC: Multiplicative reduction — prod *= a(i)
!       Same load->mulf->store chain as additive, operator is *.
subroutine reduction_product(a, prod, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(in)    :: a(n)
  real,    intent(inout) :: prod
  integer :: i
  do i = 1, n
    prod = prod * a(i)
  end do
end subroutine
