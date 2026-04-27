! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: numerical_safety
! DESC: Double-precision array operation — b(i) = a(i) * 2.0d0
!       Tests that the pass handles double (REAL(8)) types the same as
!       single precision; FIR uses f64 vs f32 but the structural pattern
!       is identical.
subroutine safe_double_precision(a, b, n)
  implicit none
  integer,     intent(in)  :: n
  real(kind=8), intent(in)  :: a(n)
  real(kind=8), intent(out) :: b(n)
  integer :: i
  do i = 1, n
    b(i) = a(i) * 2.0d0
  end do
end subroutine
