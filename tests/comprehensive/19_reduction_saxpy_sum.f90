! EXPECTED: UNSAFE
! HINT: ! Parallelizability could not be determined
! CATEGORY: reduction
! DESC: Chained SAXPY reduction — s = s + alpha*x(i) + y(i)
!       This compiles to two chained addf ops in FIR:
!         tmp1 = addf(load(s), mulf(alpha, x(i)))
!         tmp2 = addf(tmp1, y(i))
!         store tmp2 → s
!       Phase 4 matches the pattern: load %acc → single-binop → store %acc.
!       Here the final store's source (tmp2) is the result of the OUTER addf
!       whose operand is tmp1 (not directly the loaded s).  The single-step
!       chain check does not follow the two-level chain, so Phase 4 fails to
!       match and Phase 5 conservative fallback fires UNSAFE.
!       KNOWN LIMITATION: multi-operator reduction expressions not detected.
subroutine reduction_saxpy_sum(x, y, s, alpha, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(in)    :: x(n), y(n), alpha
  real,    intent(inout) :: s
  integer :: i
  do i = 1, n
    s = s + alpha * x(i) + y(i)
  end do
end subroutine
