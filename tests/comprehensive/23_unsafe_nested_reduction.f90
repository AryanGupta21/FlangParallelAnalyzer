! EXPECTED: UNSAFE
! HINT: loop-carried dependency (conservative — nested loop, multi-dim index)
! CATEGORY: control_flow_complexity
! DESC: Row-wise dot-product sum in a doubly-nested loop.
!       The outer loop accumulates into s(i); the inner loop is a reduction
!       over j.  Correct OMP would be: outer PARALLEL DO + inner REDUCTION.
!       The pass sees the outer loop as having external writes (s(i)) and the
!       inner loop as using the outer IV — both end up conservative UNSAFE.
subroutine unsafe_nested_reduction(a, b, s, m, n)
  implicit none
  integer, intent(in)  :: m, n
  real,    intent(in)  :: a(m,n), b(n)
  real,    intent(out) :: s(m)
  integer :: i, j
  do i = 1, m
    s(i) = 0.0
    do j = 1, n
      s(i) = s(i) + a(i,j) * b(j)
    end do
  end do
end subroutine
