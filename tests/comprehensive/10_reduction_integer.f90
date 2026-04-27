! EXPECTED: REDUCTION
! HINT: !$OMP PARALLEL DO REDUCTION(+:isum)
! CATEGORY: reduction
! DESC: Integer sum reduction — isum += ia(i)
!       Tests that the addi (integer add) path is matched in Phase 4,
!       not just addf (floating-point add).
subroutine reduction_integer(ia, isum, n)
  implicit none
  integer, intent(in)    :: n
  integer, intent(in)    :: ia(n)
  integer, intent(inout) :: isum
  integer :: i
  do i = 1, n
    isum = isum + ia(i)
  end do
end subroutine
