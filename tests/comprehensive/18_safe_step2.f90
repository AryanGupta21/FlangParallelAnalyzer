! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: correct_parallelization
! DESC: Stride-2 loop — b(i) = a(i) * 2.0, step 2
!       The induction variable still indexes distinct elements (i, i+2, i+4 ...).
!       Each iteration writes a distinct element of b; no cross-iteration deps.
subroutine safe_step2(a, b, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer :: i
  do i = 1, n, 2
    b(i) = a(i) * 2.0
  end do
end subroutine
