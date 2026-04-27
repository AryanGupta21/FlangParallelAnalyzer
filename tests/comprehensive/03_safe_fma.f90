! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Fused multiply-add — d(i) = a(i)*b(i) + c(i)
!       Multiple reads from different arrays, single write; all IV-indexed.
subroutine safe_fma(a, b, c, d, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n), b(n), c(n)
  real,    intent(out) :: d(n)
  integer :: i
  do i = 1, n
    d(i) = a(i) * b(i) + c(i)
  end do
end subroutine
