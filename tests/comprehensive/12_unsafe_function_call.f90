! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — external call with unknown side effects)
! CATEGORY: unsupported_unsafe
! DESC: External function call inside loop — a(i) = ext_func(a(i))
!       The pass cannot see into ext_func; it may have side effects or
!       modify shared state. Conservative: UNSAFE.
subroutine unsafe_function_call(a, n)
  implicit none
  integer, intent(in)    :: n
  real,    intent(inout) :: a(n)
  real, external :: ext_func
  integer :: i
  do i = 1, n
    a(i) = ext_func(a(i))
  end do
end subroutine
