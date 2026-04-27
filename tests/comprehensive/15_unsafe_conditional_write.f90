! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: control_flow_complexity
! DESC: Conditional write — if (a(i) > 0.0) b(i) = a(i) else b(i) = 0.0
!       a is read-only with IV subscript; b is written with IV subscript in
!       both branches.  No cross-iteration dependency exists — iteration i
!       only touches a(i) and b(i) regardless of the branch taken.
!       The pass correctly returns SAFE: the IF control flow does not affect
!       the absence of loop-carried dependencies.
subroutine unsafe_conditional_write(a, b, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer :: i
  do i = 1, n
    if (a(i) > 0.0) then
      b(i) = a(i)
    else
      b(i) = 0.0
    end if
  end do
end subroutine
