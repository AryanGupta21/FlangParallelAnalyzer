add_executable(fpa-tool main.cpp)

target_link_libraries(fpa-tool PRIVATE
  # Our analysis library
  FPALoopAnalysis

  # mlir-opt infrastructure
  MLIROptLib
  MLIRPass
  MLIRSupport
  MLIRParser
  MLIRIR
  MLIRFuncDialect
  MLIRArithDialect

  # FIR dialect (apt: .a files via link_directories; source: cmake targets)
  FIRDialect
  FIRDialectSupport
  FIRBuilder
  FIRSupport
)

install(TARGETS fpa-tool DESTINATION bin)
