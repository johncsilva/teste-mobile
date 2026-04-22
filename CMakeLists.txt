cmake_minimum_required(VERSION 3.16)
project(cpp_omr CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(OpenCV REQUIRED)

include(FetchContent)
FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
    URL_HASH SHA256=d6c65aca6b1ed68e7a182f4757257b107ae403032760ed6ef121c9d55e81757d
)
FetchContent_MakeAvailable(nlohmann_json)

# biblioteca compartilhada (futuro FFI)
add_library(omr SHARED omr.cpp)
target_include_directories(omr PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(omr PRIVATE ${OpenCV_LIBS} nlohmann_json::nlohmann_json)

# opencv-mobile (Android) e compilado com -fopenmp=libomp e distribui .a
# estaticos — o linkage de OpenMP vira responsabilidade do consumidor.
# O NDK r27 *nao* traz libomp, entao usamos uma libomp.a buildada do
# LLVM 19 openmp runtime (ver android/scripts/build-libomp.sh).
# Anulamos tambem o -static-openmp que vem do OpenCVModules.cmake, senao
# o clang tenta resolver libomp via flag e falha antes de ver nossa .a.
if(ANDROID)
    set(LIBOMP_A "${CMAKE_CURRENT_SOURCE_DIR}/android/vendor/libomp/${ANDROID_ABI}/libomp.a")
    if(NOT EXISTS "${LIBOMP_A}")
        message(FATAL_ERROR
            "libomp.a nao encontrada em ${LIBOMP_A}. "
            "Rode android/scripts/build-libomp.sh antes do build.sh.")
    endif()
    target_link_libraries(omr PRIVATE "${LIBOMP_A}")
    target_link_options(omr PRIVATE -fopenmp SHELL:-Wl,--allow-multiple-definition)
endif()

# Android: empacota o JNI wrapper dentro da mesma libomr.so. Mantemos
# omr.cpp / omr.h limpos da dependencia <jni.h> — no desktop o wrapper
# nem entra no build. Kotlin carrega um unico .so, sem lib auxiliar.
if(ANDROID)
    target_sources(omr PRIVATE android/jni/OmrJni.cpp)
endif()

# CLI de teste (desktop + Android). No Android ele roda via
# `adb shell /data/local/tmp/omr_cli ...` e da smoke-test sem precisar
# de Gradle/JNI/APK — uteis para validar opencv-mobile cedo.
add_executable(omr_cli cli.cpp)
target_link_libraries(omr_cli PRIVATE omr)
