cmake_minimum_required(VERSION 3.20)

# C must be listed alongside CXX — LLVM's cmake modules run C compiler checks
project(FlangParallelAnalyzer C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── Required path ────────────────────────────────────────────────────────────
# Apt install (Codespaces):  -DLLVM_BUILD_DIR=/usr/lib/llvm-18
# Source build:              -DLLVM_BUILD_DIR=/path/to/llvm-project/build
set(LLVM_BUILD_DIR "" CACHE PATH "LLVM install or build directory")
set(LLVM_SOURCE_DIR "" CACHE PATH "LLVM source dir (source builds only)")

if(NOT LLVM_BUILD_DIR)
  message(FATAL_ERROR
    "Set -DLLVM_BUILD_DIR=/usr/lib/llvm-18  (apt)\n"
    "  or -DLLVM_BUILD_DIR=/path/to/llvm-project/build  (source)")
endif()

if(NOT LLVM_SOURCE_DIR)
  set(LLVM_SOURCE_DIR "${LLVM_BUILD_DIR}")
endif()

# ── Find LLVM / MLIR / Flang ─────────────────────────────────────────────────
list(APPEND CMAKE_PREFIX_PATH
  "${LLVM_BUILD_DIR}/lib/cmake/llvm"
  "${LLVM_BUILD_DIR}/lib/cmake/mlir"
  "${LLVM_BUILD_DIR}/lib/cmake/flang"
)

find_package(LLVM  REQUIRED CONFIG)
find_package(MLIR  REQUIRED CONFIG)
find_package(Flang CONFIG QUIET)   # optional — exports FIR targets if present

list(APPEND CMAKE_MODULE_PATH
  "${LLVM_CMAKE_DIR}"
  "${MLIR_CMAKE_DIR}"
)

include(AddLLVM)
include(AddMLIR)
include(HandleLLVMOptions)

# ── FIR libraries (apt: .a files, source build: cmake targets) ───────────────
# link_directories lets us write e.g. target_link_libraries(... FIRDialect ...)
# and the linker will find libFIRDialect.a in this path automatically.
link_directories("${LLVM_BUILD_DIR}/lib")

# ── Include directories ───────────────────────────────────────────────────────
include_directories(
  ${LLVM_INCLUDE_DIRS}
  ${MLIR_INCLUDE_DIRS}
  "${LLVM_BUILD_DIR}/include"
  "${LLVM_SOURCE_DIR}/flang/include"
  "${LLVM_BUILD_DIR}/tools/flang/include"
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

add_definitions(${LLVM_DEFINITIONS})

# ── Subdirectories ────────────────────────────────────────────────────────────
add_subdirectory(lib)
add_subdirectory(tools)
