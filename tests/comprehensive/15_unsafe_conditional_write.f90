! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — conditional array write)
! CATEGORY: control_flow_complexity
! DESC: Conditional write — if (a(i) > 0) b(i) = a(i)
!       The array b is written conditionally; because the write is inside
!       an IF block the FIR contains additional control flow ops that make
!       the subscript trace non-trivial.  Conservative: UNSAFE.
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
