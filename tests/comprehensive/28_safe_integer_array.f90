! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Integer array copy — b(i) = a(i) + 1
!       Tests integer array handling; FIR emits addi instead of addf.
!       The structural pattern is the same as the float case.
subroutine safe_integer_array(a, b, n)
  implicit none
  integer, intent(in)  :: n
  integer, intent(in)  :: a(n)
  integer, intent(out) :: b(n)
  integer :: i
  do i = 1, n
    b(i) = a(i) + 1
  end do
end subroutine
