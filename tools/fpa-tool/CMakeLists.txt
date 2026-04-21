set(LLVM_LINK_COMPONENTS
  Support
  Core
)

add_llvm_executable(fpa-tool
  main.cpp
)

target_link_libraries(fpa-tool PRIVATE
  # Our analysis library
  FPALoopAnalysis

  # mlir-opt infrastructure (MlirOptMain, pass manager, etc.)
  MLIROptLib
  MLIRPass
  MLIRSupport
  MLIRParser
  MLIRIR
  MLIRFuncDialect
  MLIRArithDialect

  # FIR
  FIRDialect
  FIRSupport
  FIRBuilder
)

# Tell CMake to install the tool alongside other LLVM tools (optional)
install(TARGETS fpa-tool DESTINATION bin)
