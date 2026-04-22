#!/usr/bin/env bash
# Gera o Gradle Wrapper (gradlew + gradle-wrapper.jar) sem exigir `gradle`
# instalado no sistema. Baixa o distro oficial em `.gradle-bootstrap/`
# uma unica vez, roda `gradle wrapper`, e deixa o diretorio local.
#
# Uso:
#   ./bootstrap.sh
#
# Depois:
#   ./gradlew :app:assembleDebug
#
# Alternativa: abrir o projeto no Android Studio — o Sync faz a mesma coisa.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GRADLE_VERSION="8.9"
CACHE_DIR=".gradle-bootstrap"
DISTRO_URL="https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip"
DISTRO_ZIP="$CACHE_DIR/gradle-${GRADLE_VERSION}-bin.zip"
DISTRO_DIR="$CACHE_DIR/gradle-${GRADLE_VERSION}"

if [[ -f "gradlew" && -f "gradle/wrapper/gradle-wrapper.jar" ]]; then
    echo ">> Wrapper ja existe. Nada a fazer."
    exit 0
fi

mkdir -p "$CACHE_DIR"

if [[ ! -d "$DISTRO_DIR" ]]; then
    if [[ ! -f "$DISTRO_ZIP" ]]; then
        echo ">> Baixando Gradle $GRADLE_VERSION..."
        curl -L --fail -o "$DISTRO_ZIP" "$DISTRO_URL"
    fi
    echo ">> Extraindo..."
    unzip -q "$DISTRO_ZIP" -d "$CACHE_DIR"
fi

GRADLE_BIN="$DISTRO_DIR/bin/gradle"
if [[ ! -x "$GRADLE_BIN" ]]; then
    echo "ERRO: $GRADLE_BIN nao encontrado apos extracao" >&2
    exit 1
fi

echo ">> Gerando wrapper via $GRADLE_BIN wrapper --gradle-version $GRADLE_VERSION..."
"$GRADLE_BIN" wrapper --gradle-version "$GRADLE_VERSION" --distribution-type bin

echo ""
echo ">> OK. Agora rode: ./gradlew :app:assembleDebug"
echo ">> (o diretorio $CACHE_DIR/ pode ser apagado — gitignored)"
