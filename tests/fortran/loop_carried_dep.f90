! loop_carried_dep.f90
!
! Expected hint: UNSAFE
! Reason: a(i) = a(i) + a(i-1) — iteration i reads the value written
!         by iteration i-1. This is a loop-carried dependency; parallelizing
!         would produce incorrect results.

subroutine prefix_sum(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i

  do i = 2, n
    a(i) = a(i) + a(i-1)
  end do

end subroutine prefix_sum
