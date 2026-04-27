! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Independent element-wise scale — b(i) = a(i)*2.0
!       Each iteration reads a(i) and writes b(i); no overlap.
subroutine safe_scale(a, b, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer :: i
  do i = 1, n
    b(i) = a(i) * 2.0
  end do
end subroutine
