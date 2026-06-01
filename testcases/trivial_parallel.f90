! trivial_parallel.f90
!
! Expected hint: !$OMP PARALLEL DO
! Reason: b(i) is written using only the induction variable i.
!         a(i) is read-only. No cross-iteration dependencies.

subroutine scale(a, b, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer :: i

  do i = 1, n
    b(i) = a(i) * 2.0
  end do

end subroutine scale
