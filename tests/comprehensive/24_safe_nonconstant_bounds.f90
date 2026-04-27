! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: performance_edge_case
! DESC: Runtime-determined bounds — b(i) = a(i) * scale
!       Loop bounds (lo, hi) come from function arguments, shown as '?' in
!       the Bounds line.  The dependency analysis still runs correctly; the
!       only difference is the bounds field is uninformative.
subroutine safe_nonconstant_bounds(a, b, scale, lo, hi)
  implicit none
  integer, intent(in) :: lo, hi
  real,    intent(in) :: scale
  real,    intent(in)  :: a(hi)
  real,    intent(out) :: b(hi)
  integer :: i
  do i = lo, hi
    b(i) = a(i) * scale
  end do
end subroutine
