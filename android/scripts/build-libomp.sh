#!/usr/bin/env bash
# Cross-compile libomp.a para cada ABI Android.
#
# Por que: opencv-mobile 4.13.0-android e compilada com -fopenmp=libomp
# + -static-openmp, e o NDK r27 nao inclui libomp nos prebuilts. Sem essa
# lib, o link de libomr.so falha com `undefined symbol: __kmpc_*`.
#
# A versao minima do LLVM OpenMP runtime com `__kmpc_dispatch_deinit`
# disponivel como simbolo definido e a 19.x (antes existia so como decl).
#
# Bionic (libc do Android) nao tem <nl_types.h> — a build upstream de
# libomp depende disso para i18n de mensagens. Usamos um shim que sempre
# retorna "catalog absent" (mensagens default em ingles).
#
# Uso:
#   ANDROID_NDK_ROOT=/path/to/ndk ./build-libomp.sh
#   ANDROID_NDK_ROOT=/path/to/ndk ./build-libomp.sh arm64-v8a
#
# Saida: android/vendor/libomp/<abi>/libomp.a

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$ANDROID_DIR/vendor"
LIBOMP_OUT="$VENDOR_DIR/libomp"

LLVM_VER="${LLVM_VER:-19.1.7}"
ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-21}"
ABIS="${*:-arm64-v8a armeabi-v7a}"

if [[ -z "${ANDROID_NDK_ROOT:-}" ]]; then
    echo "ERRO: ANDROID_NDK_ROOT nao setado."
    exit 1
fi

# === Download source LLVM openmp se necessario ===
WORK_DIR="$VENDOR_DIR/.llvm-openmp-$LLVM_VER"
if [[ ! -d "$WORK_DIR/openmp" ]]; then
    echo ">> Baixando openmp + cmake-modules $LLVM_VER do LLVM releases..."
    mkdir -p "$WORK_DIR"
    curl -sSL -o "$WORK_DIR/openmp.tar.xz" \
        "https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VER}/openmp-${LLVM_VER}.src.tar.xz"
    curl -sSL -o "$WORK_DIR/cmake.tar.xz" \
        "https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VER}/cmake-${LLVM_VER}.src.tar.xz"
    (cd "$WORK_DIR" && tar xf openmp.tar.xz && tar xf cmake.tar.xz)
    mv "$WORK_DIR"/openmp-*.src "$WORK_DIR/openmp"
    mv "$WORK_DIR"/cmake-*.src "$WORK_DIR/cmake"
fi

# === Shim de nl_types.h (bionic nao tem) ===
SHIM_DIR="$WORK_DIR/shim"
if [[ ! -f "$SHIM_DIR/nl_types.h" ]]; then
    mkdir -p "$SHIM_DIR"
    cat > "$SHIM_DIR/nl_types.h" <<'EOF'
#ifndef _SHIM_NL_TYPES_H
#define _SHIM_NL_TYPES_H
#ifdef __cplusplus
extern "C" {
#endif
typedef void* nl_catd;
static inline nl_catd catopen(const char* name, int flag) { (void)name; (void)flag; return (nl_catd)(-1); }
static inline char* catgets(nl_catd cat, int set_id, int msg_id, const char* dflt) {
    (void)cat; (void)set_id; (void)msg_id; return (char*)dflt;
}
static inline int catclose(nl_catd cat) { (void)cat; return 0; }
#ifdef __cplusplus
}
#endif
#endif
EOF
fi

# === Build para cada ABI ===
for ABI in $ABIS; do
    BUILD_DIR="$WORK_DIR/build-$ABI"
    echo ""
    echo "=============================================="
    echo ">> libomp.a para $ABI (API $ANDROID_API_LEVEL)"
    echo "=============================================="
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    cmake -S "$WORK_DIR/openmp" -B "$BUILD_DIR" \
        -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake" \
        -DANDROID_ABI="$ABI" \
        -DANDROID_PLATFORM="android-$ANDROID_API_LEVEL" \
        -DLIBOMP_ENABLE_SHARED=OFF \
        -DLIBOMP_OMPT_SUPPORT=OFF \
        -DLIBOMP_USE_HWLOC=OFF \
        -DCMAKE_BUILD_TYPE=Release \
        -DOPENMP_STANDALONE_BUILD=ON \
        -DOPENMP_ENABLE_LIBOMPTARGET=OFF \
        -DCMAKE_C_FLAGS="-I$SHIM_DIR" \
        -DCMAKE_CXX_FLAGS="-I$SHIM_DIR" \
        >/dev/null
    cmake --build "$BUILD_DIR" --target omp -j >/dev/null

    OUT_DIR="$LIBOMP_OUT/$ABI"
    mkdir -p "$OUT_DIR"
    cp "$BUILD_DIR/runtime/src/libomp.a" "$OUT_DIR/"
    SIZE_KB=$(($(stat -c '%s' "$OUT_DIR/libomp.a" 2>/dev/null || stat -f '%z' "$OUT_DIR/libomp.a") / 1024))
    echo ">> [$ABI] libomp.a = ${SIZE_KB} KB em $OUT_DIR"
done

echo ""
echo "libomp.a builds concluidos em $LIBOMP_OUT"
