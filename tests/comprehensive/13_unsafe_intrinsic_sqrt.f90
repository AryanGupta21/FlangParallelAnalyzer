! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — in-place array update)
! CATEGORY: unsupported_unsafe
! DESC: Intrinsic math call — a(i) = sqrt(a(i))
!       Even though sqrt is pure, the pass sees the same array as both
!       source and destination and cannot confirm there is no aliasing.
!       Classified UNSAFE (conservative).
subroutine unsafe_intrinsic_sqrt(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 1, n
    a(i) = sqrt(a(i))
  end do
end subroutine
