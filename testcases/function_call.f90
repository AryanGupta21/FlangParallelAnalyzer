! function_call.f90
!
! Expected hint (Phase 1): UNKNOWN
! Expected hint (Phase 2+, with intrinsic whitelist): !$OMP PARALLEL DO
!   sqrt() is a pure intrinsic — no side effects.
!
! This test case is intentionally on the boundary: a naive pass marks it
! UNSAFE (conservative), but a smarter pass whitelists pure intrinsics.

subroutine apply_sqrt(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i

  do i = 1, n
    a(i) = sqrt(a(i))
  end do

end subroutine apply_sqrt
