! nested_loops.f90
!
! Expected hint: !$OMP PARALLEL DO COLLAPSE(2)
! Reason: Both i and j loops are independent. Each (i,j) cell is written
!         exactly once using a(i,j) — no cross-iteration dependencies.

subroutine matrix_scale(a, n, m)
  implicit none
  integer, intent(in)    :: n, m
  real,    intent(inout) :: a(n, m)
  integer :: i, j

  do i = 1, n
    do j = 1, m
      a(i, j) = a(i, j) * 2.0
    end do
  end do

end subroutine matrix_scale
