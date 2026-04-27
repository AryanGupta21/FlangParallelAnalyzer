! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — same array read+write)
! CATEGORY: aliasing_pointer
! DESC: Same dummy argument used as both source and destination — a(i) = a(i-1)*2
!       This is the canonical aliased-argument hazard.  The pass detects
!       the i-1 subscript offset and correctly marks UNSAFE.
subroutine unsafe_alias_inout(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  integer :: i
  do i = 2, n
    a(i) = a(i-1) * 2.0
  end do
end subroutine
