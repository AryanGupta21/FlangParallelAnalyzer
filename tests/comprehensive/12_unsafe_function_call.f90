! EXPECTED: SAFE
! HINT: !$OMP PARALLEL DO
! CATEGORY: unsupported_unsafe
! DESC: External function call inside loop — a(i) = ext_func(a(i))
!       In Fortran, arguments to external functions are passed by reference.
!       In FIR the pass only sees a fir.store to a(i) (IV-indexed) and no
!       visible fir.load through the opaque call boundary.  Phase 3 therefore
!       classifies this as SAFE — a known false-positive limitation of the pass
!       (it cannot inspect side effects of external calls).
!       KNOWN LIMITATION: the pass trusts FIR structure; opaque calls are not
!       conservatively flagged.
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
