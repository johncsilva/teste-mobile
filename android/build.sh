#!/usr/bin/env bash
# Cross-compile libomr.so para Android (arm64-v8a, armeabi-v7a) usando
# opencv-mobile prebuilt. Saida em `build-<abi>/libomr.so`.
#
# Requisitos:
#   - Android NDK (r27+ recomendado) com toolchain Linux/Mac (Windows NDK
#     nao funciona nativamente no WSL — baixar NDK Linux)
#   - cmake, unzip, curl
#
# Uso:
#   ANDROID_NDK_ROOT=/path/to/android-ndk ./build.sh
#   ANDROID_NDK_ROOT=/path/to/android-ndk ./build.sh arm64-v8a
#
# O opencv-mobile e baixado automaticamente em vendor/ (gitignored).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPP_OMR_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$SCRIPT_DIR/vendor"

OPENCV_VERSION="4.13.0"
OPENCV_ZIP="opencv-mobile-${OPENCV_VERSION}-android.zip"
OPENCV_URL="https://github.com/nihui/opencv-mobile/releases/latest/download/${OPENCV_ZIP}"
OPENCV_DIR="$VENDOR_DIR/opencv-mobile-${OPENCV_VERSION}-android"

ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-21}"
ABIS="${*:-arm64-v8a armeabi-v7a}"

if [[ -z "${ANDROID_NDK_ROOT:-}" ]]; then
    echo "ERRO: ANDROID_NDK_ROOT nao setado."
    echo ""
    echo "Se ja tem NDK instalado via Android Studio:"
    echo "   export ANDROID_NDK_ROOT=\$ANDROID_HOME/ndk/<versao>"
    echo ""
    echo "Se precisa baixar NDK Linux:"
    echo "   curl -LO https://dl.google.com/android/repository/android-ndk-r27c-linux.zip"
    echo "   unzip android-ndk-r27c-linux.zip -d ~/android-ndk"
    echo "   export ANDROID_NDK_ROOT=~/android-ndk/android-ndk-r27c"
    exit 1
fi

if [[ ! -x "$ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake" ]] && \
   [[ ! -f "$ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake" ]]; then
    echo "ERRO: toolchain nao encontrada em $ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake"
    exit 1
fi

# === Baixa e extrai opencv-mobile se necessario ===
if [[ ! -d "$OPENCV_DIR" ]]; then
    echo ">> Baixando opencv-mobile $OPENCV_VERSION para Android..."
    mkdir -p "$VENDOR_DIR"
    if [[ ! -f "$VENDOR_DIR/$OPENCV_ZIP" ]]; then
        curl -L --fail -o "$VENDOR_DIR/$OPENCV_ZIP" "$OPENCV_URL"
    fi
    unzip -q "$VENDOR_DIR/$OPENCV_ZIP" -d "$VENDOR_DIR"
    echo ">> opencv-mobile extraido em $OPENCV_DIR"
fi

# === libomp.a (cross-compile via build-libomp.sh) ===
# opencv-mobile e compilado com -fopenmp=libomp -static-openmp e o NDK r27
# nao traz libomp nos prebuilts. build-libomp.sh gera a .a para cada ABI;
# aqui so disparamos se estiver faltando (idempotente, rebuild demora).
NEEDS_LIBOMP=0
for ABI in $ABIS; do
    if [[ ! -f "$SCRIPT_DIR/vendor/libomp/$ABI/libomp.a" ]]; then
        NEEDS_LIBOMP=1
        break
    fi
done
if [[ "$NEEDS_LIBOMP" == "1" ]]; then
    echo ""
    echo ">> libomp.a ausente para um ou mais ABIs — invocando build-libomp.sh..."
    "$SCRIPT_DIR/scripts/build-libomp.sh" $ABIS
fi

# === Build para cada ABI ===
for ABI in $ABIS; do
    BUILD_DIR="$CPP_OMR_DIR/build-android-$ABI"
    echo ""
    echo "=============================================="
    echo ">> Build para $ABI (API $ANDROID_API_LEVEL)"
    echo "=============================================="
    rm -rf "$BUILD_DIR"
    cmake -S "$CPP_OMR_DIR" -B "$BUILD_DIR" \
        -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake" \
        -DANDROID_ABI="$ABI" \
        -DANDROID_PLATFORM="android-$ANDROID_API_LEVEL" \
        -DANDROID_STL=c++_static \
        -DOpenCV_DIR="$OPENCV_DIR/sdk/native/jni" \
        -DCMAKE_BUILD_TYPE=Release
    cmake --build "$BUILD_DIR" -j

    SO="$BUILD_DIR/libomr.so"
    if [[ -f "$SO" ]]; then
        SIZE=$(stat -c '%s' "$SO" 2>/dev/null || stat -f '%z' "$SO")
        SIZE_KB=$((SIZE / 1024))
        echo ">> [$ABI] libomr.so = ${SIZE_KB} KB"
    else
        echo "ERRO: libomr.so nao gerada para $ABI"
        exit 1
    fi
done

echo ""
echo "=============================================="
echo ">> Build Android concluido"
echo "=============================================="
