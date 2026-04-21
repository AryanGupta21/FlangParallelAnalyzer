set(LLVM_LINK_COMPONENTS
  Support
  Core
)

add_mlir_library(FPALoopAnalysis
  LoopParallelAnalysis.cpp

  LINK_LIBS PUBLIC
    # MLIR core
    MLIRPass
    MLIRSupport
    MLIRTransformUtils
    MLIRFuncDialect

    # Arith dialect (arith::ConstantOp, arith::AddIOp, etc.)
    MLIRArithDialect

    # FIR dialect from Flang
    FIRDialect
    FIRBuilder
    FIRSupport
)

target_include_directories(FPALoopAnalysis PUBLIC
  "${CMAKE_SOURCE_DIR}/include"
)
