! EXPECTED: UNSAFE
! HINT: loop-carried dependency
! CATEGORY: dependency_edge_case
! DESC: Cross-array stencil — b(i) = a(i) + a(i-1)
!       a is read-only but with offset subscript i-1.
!       b is write-only with IV subscript.
!       The i-1 read from a is a loop-carried dependence if a and b overlap
!       (e.g. called as b=>a).  The pass detects the i-1 subscript and
!       conservatively marks UNSAFE regardless of aliasing.
subroutine unsafe_cross_array_dep(a, b, n)
  implicit none
  integer, intent(in)  :: n
  real,    intent(in)  :: a(n)
  real,    intent(out) :: b(n)
  integer :: i
  do i = 2, n
    b(i) = a(i) + a(i-1)
  end do
end subroutine
