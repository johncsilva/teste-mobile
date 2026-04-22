#!/usr/bin/env bash
# Cross-compile libomr.a para iOS e monta libomr.xcframework.
#
# Gera 3 slices e agrupa em 1 xcframework:
#   - ios-arm64              (OS64)            -> iPhone/iPad fisico
#   - ios-arm64-simulator    (SIMULATORARM64)  -> Simulator em Mac Apple Silicon
#   - ios-x86_64-simulator   (SIMULATOR64)     -> Simulator em Mac Intel (opcional)
#
# Os dois simulator slices sao combinados via `lipo -create` numa lib fat
# (Apple convencionou que simulator arm64 + x86_64 moram juntos no mesmo
# slice do xcframework; device arm64 fica separado por causa da assinatura).
#
# Requisitos (SO macOS obrigatoriamente — Xcode nao roda em Linux):
#   - Xcode + Command Line Tools (xcrun, xcodebuild, lipo)
#   - cmake, curl, unzip, git
#
# Uso:
#   ./build-ios.sh            # builda os 3 slices + xcframework
#   ./build-ios.sh OS64       # builda apenas 1 slice (debug)
#
# Saidas:
#   build-ios/<PLATFORM>/libomr.a         # slices individuais
#   build-ios/libomr.xcframework/         # bundle final para app
#
# opencv-mobile + toolchain sao cacheados em vendor/ (gitignored).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPP_OMR_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$SCRIPT_DIR/vendor"
BUILD_ROOT="$CPP_OMR_DIR/build-ios"

OPENCV_VERSION="4.13.0"
OPENCV_IOS_ZIP="opencv-mobile-${OPENCV_VERSION}-ios.zip"
OPENCV_SIM_ZIP="opencv-mobile-${OPENCV_VERSION}-ios-simulator.zip"
OPENCV_URL_BASE="https://github.com/nihui/opencv-mobile/releases/latest/download"
OPENCV_IOS_DIR="$VENDOR_DIR/opencv-mobile-${OPENCV_VERSION}-ios"
OPENCV_SIM_DIR="$VENDOR_DIR/opencv-mobile-${OPENCV_VERSION}-ios-simulator"

# leetal/ios-cmake: toolchain CMake mantida que esconde as manhas do SDK
# Apple (CMAKE_OSX_SYSROOT, ONLY_ACTIVE_ARCH, codesign). Pin num commit
# conhecido para build reproducivel.
IOS_CMAKE_REPO="https://github.com/leetal/ios-cmake.git"
IOS_CMAKE_TAG="4.5.0"
IOS_CMAKE_DIR="$VENDOR_DIR/ios-cmake"
IOS_TOOLCHAIN="$IOS_CMAKE_DIR/ios.toolchain.cmake"

# iOS 13 cobre ~98% da base instalada em 2026 e e o minimo suportado
# pelo opencv-mobile 4.13.0 precompilado. Usuario pode sobrescrever:
#   IOS_DEPLOYMENT_TARGET=14.0 ./build-ios.sh
IOS_DEPLOYMENT_TARGET="${IOS_DEPLOYMENT_TARGET:-13.0}"

PLATFORMS="${*:-OS64 SIMULATORARM64 SIMULATOR64}"

# === Validacoes de ambiente ===
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERRO: build iOS exige macOS (uname -s = $(uname -s))."
    echo "Use GitHub Actions com runs-on: macos-latest — workflow em"
    echo ".github/workflows/ios.yml faz isso automaticamente."
    exit 1
fi

if ! command -v xcrun >/dev/null 2>&1; then
    echo "ERRO: xcrun nao encontrado. Instale Xcode Command Line Tools:"
    echo "  xcode-select --install"
    exit 1
fi

if ! xcrun --find xcodebuild >/dev/null 2>&1; then
    echo "ERRO: xcodebuild nao encontrado. Instale Xcode completo (nao apenas CLT)."
    exit 1
fi

mkdir -p "$VENDOR_DIR" "$BUILD_ROOT"

# === Baixa opencv-mobile iOS (device + simulator) ===
download_opencv() {
    local zip_name="$1"
    local extract_dir="$2"
    local zip_path="$VENDOR_DIR/$zip_name"

    if [[ -d "$extract_dir" ]]; then
        return 0
    fi

    echo ">> Baixando $zip_name..."
    if [[ ! -f "$zip_path" ]]; then
        curl -L --fail -o "$zip_path" "$OPENCV_URL_BASE/$zip_name"
    fi
    unzip -q "$zip_path" -d "$VENDOR_DIR"
    echo ">> Extraido em $extract_dir"
}

download_opencv "$OPENCV_IOS_ZIP" "$OPENCV_IOS_DIR"
download_opencv "$OPENCV_SIM_ZIP" "$OPENCV_SIM_DIR"

# === Clona leetal/ios-cmake toolchain ===
if [[ ! -f "$IOS_TOOLCHAIN" ]]; then
    echo ">> Clonando ios-cmake $IOS_CMAKE_TAG..."
    git clone --depth 1 --branch "$IOS_CMAKE_TAG" "$IOS_CMAKE_REPO" "$IOS_CMAKE_DIR"
fi

# === Build para cada PLATFORM ===
# leetal/ios-cmake mapeia PLATFORM -> (SDK, arch, deployment flags):
#   OS64            -> iphoneos,           arm64
#   SIMULATORARM64  -> iphonesimulator,    arm64
#   SIMULATOR64     -> iphonesimulator,    x86_64
build_platform() {
    local platform="$1"
    local build_dir="$BUILD_ROOT/$platform"

    # opencv-mobile distribui device e simulator em pastas separadas —
    # escolhemos baseado no PLATFORM (iphonesimulator usa o sim zip).
    local opencv_dir
    case "$platform" in
        OS64)
            opencv_dir="$OPENCV_IOS_DIR"
            ;;
        SIMULATORARM64|SIMULATOR64)
            opencv_dir="$OPENCV_SIM_DIR"
            ;;
        *)
            echo "ERRO: PLATFORM desconhecido '$platform'"
            exit 1
            ;;
    esac

    echo ""
    echo "=============================================="
    echo ">> Build para $platform (iOS $IOS_DEPLOYMENT_TARGET)"
    echo "=============================================="
    rm -rf "$build_dir"

    cmake -S "$CPP_OMR_DIR" -B "$build_dir" -G Xcode \
        -DCMAKE_TOOLCHAIN_FILE="$IOS_TOOLCHAIN" \
        -DPLATFORM="$platform" \
        -DDEPLOYMENT_TARGET="$IOS_DEPLOYMENT_TARGET" \
        -DENABLE_BITCODE=OFF \
        -DENABLE_ARC=OFF \
        -DENABLE_VISIBILITY=ON \
        -DOpenCV_DIR="$opencv_dir/lib/cmake/opencv4" \
        -DCMAKE_BUILD_TYPE=Release

    # Xcode generator usa multi-config; `--config Release` garante Release
    # mesmo quando o toolchain tem config default diferente.
    cmake --build "$build_dir" --config Release -- -quiet

    local a_file="$build_dir/Release-iphoneos/libomr.a"
    # Simulator builds caem em Release-iphonesimulator/
    if [[ ! -f "$a_file" ]]; then
        a_file="$build_dir/Release-iphonesimulator/libomr.a"
    fi

    if [[ ! -f "$a_file" ]]; then
        echo "ERRO: libomr.a nao gerada para $platform. Procurado em:"
        find "$build_dir" -name libomr.a 2>/dev/null || true
        exit 1
    fi

    # Normaliza caminho: copia para $build_dir/libomr.a para ficar previsivel
    cp "$a_file" "$build_dir/libomr.a"

    local size_bytes size_kb
    size_bytes=$(stat -f '%z' "$build_dir/libomr.a")
    size_kb=$((size_bytes / 1024))
    echo ">> [$platform] libomr.a = ${size_kb} KB"
}

for PLATFORM in $PLATFORMS; do
    build_platform "$PLATFORM"
done

# === Combina simulator arm64 + x86_64 em lib fat (convencao xcframework) ===
SIM_FAT_DIR="$BUILD_ROOT/simulator-fat"
SIM_ARM64_LIB="$BUILD_ROOT/SIMULATORARM64/libomr.a"
SIM_X86_64_LIB="$BUILD_ROOT/SIMULATOR64/libomr.a"

if [[ -f "$SIM_ARM64_LIB" && -f "$SIM_X86_64_LIB" ]]; then
    echo ""
    echo ">> Combinando simulator arm64 + x86_64 via lipo..."
    mkdir -p "$SIM_FAT_DIR"
    lipo -create "$SIM_ARM64_LIB" "$SIM_X86_64_LIB" -output "$SIM_FAT_DIR/libomr.a"
    lipo -info "$SIM_FAT_DIR/libomr.a"
fi

# === Monta xcframework ===
XCF="$BUILD_ROOT/libomr.xcframework"
DEVICE_LIB="$BUILD_ROOT/OS64/libomr.a"

if [[ ! -f "$DEVICE_LIB" ]]; then
    echo ""
    echo ">> OS64 nao foi buildado — pulando criacao do xcframework."
    echo ">> Para gerar o bundle completo, rode ./build-ios.sh sem argumentos."
    exit 0
fi

echo ""
echo "=============================================="
echo ">> Montando libomr.xcframework"
echo "=============================================="
rm -rf "$XCF"

XCF_ARGS=(-library "$DEVICE_LIB" -headers "$CPP_OMR_DIR")
if [[ -f "$SIM_FAT_DIR/libomr.a" ]]; then
    XCF_ARGS+=(-library "$SIM_FAT_DIR/libomr.a" -headers "$CPP_OMR_DIR")
fi
XCF_ARGS+=(-output "$XCF")

xcodebuild -create-xcframework "${XCF_ARGS[@]}"

echo ""
echo ">> xcframework montado em $XCF"
echo ">> Estrutura:"
find "$XCF" -maxdepth 2 -type d | sed "s|$XCF|libomr.xcframework|"

XCF_SIZE=$(du -sh "$XCF" | awk '{print $1}')
echo ""
echo "=============================================="
echo ">> Build iOS concluido — xcframework: $XCF_SIZE"
echo "=============================================="
