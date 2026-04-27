! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Two independent output arrays — out1(i) = a(i)+b(i), out2(i) = a(i)*b(i)
!       Multiple writes but all go to distinct elements indexed by i.
!       No aliasing between out1 and out2; both are pure output arrays.
subroutine safe_two_output(a, b, out1, out2, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n), b(n)
  real,    intent(out) :: out1(n), out2(n)
  integer :: i
  do i = 1, n
    out1(i) = a(i) + b(i)
    out2(i) = a(i) * b(i)
  end do
end subroutine
