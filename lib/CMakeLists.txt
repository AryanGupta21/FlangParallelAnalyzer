# Use add_library instead of add_mlir_library.
#
# add_mlir_library resolves LINK_LIBS entries as cmake *targets*.
# For apt-installed LLVM the FIR libraries ship as pre-built .a files
# (libFIRDialect.a, etc.) without exported cmake targets, so
# add_mlir_library fails at configure time.
#
# add_library + target_link_libraries works for both cases:
#   - apt install  → linker finds libFIRDialect.a via link_directories()
#   - source build → cmake resolves FIRDialect as a proper target

add_library(FPALoopAnalysis STATIC
  LoopParallelAnalysis.cpp
  AccessClassifier.cpp
)

target_include_directories(FPALoopAnalysis PUBLIC
  "${CMAKE_SOURCE_DIR}/include"
)

target_link_libraries(FPALoopAnalysis PUBLIC
  # MLIR — proper cmake targets exported by find_package(MLIR)
  MLIRPass
  MLIRSupport
  MLIRFuncDialect
  MLIRArithDialect

  # FIR — .a files found via link_directories() set in root CMakeLists.txt
  FIRDialect
  FIRDialectSupport
  FIRSupport
)
