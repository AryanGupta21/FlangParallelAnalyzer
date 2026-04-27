! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Array copy — c(i) = a(i) + b(i)
!       Three distinct arrays, all indexed by i; no cross-iteration deps.
subroutine safe_copy(a, b, c, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n), b(n)
  real,    intent(out) :: c(n)
  integer :: i
  do i = 1, n
    c(i) = a(i) + b(i)
  end do
end subroutine
