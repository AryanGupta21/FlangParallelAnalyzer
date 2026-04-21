cmake_minimum_required(VERSION 3.20)
project(FlangParallelAnalyzer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── Required paths ──────────────────────────────────────────────────────────
# Pass these on the cmake command line:
#   -DLLVM_BUILD_DIR=/path/to/llvm-project/build
#   -DLLVM_SOURCE_DIR=/path/to/llvm-project        (for Flang/FIR source headers)
set(LLVM_BUILD_DIR  "" CACHE PATH "LLVM/Flang build directory")
set(LLVM_SOURCE_DIR "" CACHE PATH "LLVM/Flang source directory")

if(NOT LLVM_BUILD_DIR)
  message(FATAL_ERROR
    "Set -DLLVM_BUILD_DIR=/path/to/llvm-project/build")
endif()
if(NOT LLVM_SOURCE_DIR)
  message(FATAL_ERROR
    "Set -DLLVM_SOURCE_DIR=/path/to/llvm-project")
endif()

# ── Find LLVM / MLIR ────────────────────────────────────────────────────────
list(APPEND CMAKE_PREFIX_PATH
  "${LLVM_BUILD_DIR}/lib/cmake/llvm"
  "${LLVM_BUILD_DIR}/lib/cmake/mlir"
)

find_package(LLVM REQUIRED CONFIG)
find_package(MLIR REQUIRED CONFIG)

list(APPEND CMAKE_MODULE_PATH
  "${LLVM_CMAKE_DIR}"
  "${MLIR_CMAKE_DIR}"
)

include(AddLLVM)
include(AddMLIR)
include(HandleLLVMOptions)

# ── Include directories ─────────────────────────────────────────────────────
include_directories(
  # LLVM / MLIR generated + source headers
  ${LLVM_INCLUDE_DIRS}
  ${MLIR_INCLUDE_DIRS}

  # Flang source headers (FIR dialect, optimizer)
  "${LLVM_SOURCE_DIR}/flang/include"

  # Flang generated headers (tablegen'd op definitions)
  "${LLVM_BUILD_DIR}/tools/flang/include"

  # This project's own headers
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

add_definitions(${LLVM_DEFINITIONS})

# ── Subdirectories ──────────────────────────────────────────────────────────
add_subdirectory(lib)
add_subdirectory(tools)
