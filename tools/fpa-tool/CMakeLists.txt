# Lightweight driver — no MLIROptLib so no clang-cpp transitive dependency

add_executable(fpa-tool main.cpp)

target_link_libraries(fpa-tool PRIVATE
  FPALoopAnalysis

  # Pass manager + core IR
  MLIRPass
  MLIRSupport
  MLIRParser
  MLIRIR
  MLIRAsmParser
  MLIRBytecodeReader

  # Dialects we register
  MLIRFuncDialect
  MLIRArithDialect

  # FIR (linked as .a files via link_directories in root CMakeLists)
  FIRDialect
  FIRDialectSupport
  FIRSupport
)

install(TARGETS fpa-tool DESTINATION bin)
