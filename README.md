# teste-mobile

Motor portátil de leitura de marcações ópticas (OMR — Optical Mark
Recognition) em C++/OpenCV, compilável para desktop Linux, Android (arm64) e
iOS (arm64). Inclui harness Python de benchmark reproduzível.

Propósito: repositório de testes e validação do motor OMR antes da
integração em produto. Engine é genérico (lê folhas de prova seguindo o
schema em `CONTRACT.md`) e não contém lógica de negócio.

## Status

| Plataforma | Build | Acurácia | Tempo (p50) | Notas |
|---|---|---|---|---|
| Desktop Linux | OK | 100% (190/190 sintéticos, 210/210 perturbados) | ~130 ms | OpenCV sistema |
| Android arm64-v8a | OK | 100% (120/120 em 4 folhas reais) | 221 ms | APK 10.4 MB, libomr.so 5.1 MB stripped |
| Android armeabi-v7a | — | — | — | Opcional (devices antigos 32-bit) |
| iOS arm64 | Em construção | — | — | opencv-mobile 4.13.0 ios disponível, build em `ios/` pendente |

Benchmark formal Android (N=120, 32 runs × 4 sheets, 2 warmup descartados):
p50=221 ms, p95=249 ms, p99=251 ms, RAM peak 28-29 MB.

## Estrutura

    teste-mobile/
    ├── omr.cpp, omr.h, cli.cpp   # motor + CLI (raiz = engine)
    ├── CMakeLists.txt            # build desktop
    ├── CONTRACT.md               # schema da API e formato do template
    ├── android/                  # cross-compile arm64-v8a + demo-app Kotlin
    │   ├── build.sh, jni/, scripts/
    │   └── demo-app/             # Android Activity de exemplo
    ├── ios/                      # (em construção) build xcframework
    └── benchmark/                # harness Python de validação + inputs sintéticos

## Build desktop (Linux)

Pré-requisitos:

    sudo apt install cmake libopencv-dev

Compilar:

    cmake -S . -B build
    cmake --build build -j

Artefatos em `build/`:
- `omr_cli` — CLI de teste (`./build/omr_cli <imagem> <template.v1.json>`)
- `libomr.so` — biblioteca compartilhada (para FFI/JSI)

`nlohmann/json` é baixado pelo CMake via FetchContent — sem instalação
manual.

## Build Android (cross-compile)

Pré-requisitos:
- Android NDK r27c (testado)
- `ANDROID_NDK_ROOT` exportado

Compilar:

    export ANDROID_NDK_ROOT=~/android-ndk/android-ndk-r27c
    ./android/build.sh arm64-v8a

Gera `build-android-arm64-v8a/libomr.so`. Primeira execução baixa
`opencv-mobile-4.13.0-android.zip` e builda `libomp.a` cross-compiled (dura
~4 min); execuções seguintes reusam.

Integração via JNI: ver `android/jni/OmrJni.cpp` e o app de exemplo em
`android/demo-app/` (Kotlin DSL, Gradle 8.9).

## Build iOS

Em construção. Requer macOS com Xcode e Command Line Tools. Plano:
cross-compilar `libomr.a` para arm64-device + arm64-simulator +
x86_64-simulator, consolidar em `libomr.xcframework` via
`xcodebuild -create-xcframework`.

opencv-mobile 4.13.0 para iOS foi verificado compatível (mesmos módulos do
Android, `imread/imwrite` presentes, usa GCD em vez de OpenMP).

## Benchmark

    cd benchmark
    python3 -m venv .venv && source .venv/bin/activate
    pip install numpy opencv-python pillow

    # Gerar inputs sintéticos e perturbados (se ainda não geraram):
    python3 build_templates.py
    python3 perturb.py

    # Rodar validação:
    python3 run_validation.py --detector cpp-omr --subset synthetic

Alvo em sintéticos: **≥95% acurácia, <500 ms/folha** em desktop.

### Baseline OMRChecker (opcional)

O repo não empacota o clone do OMRChecker. Para usá-lo como baseline
comparativo:

    git clone https://github.com/Udayraj123/OMRChecker.git benchmark/OMRChecker
    python3 run_validation.py --detector omrchecker --subset synthetic

### Fotos reais

O repo não inclui fotos reais de folhas preenchidas. Para reproduzir o
benchmark "real" com suas próprias amostras:

1. Imprima folhas geradas por `build_templates.py`
2. Preencha à mão, fotografe com celular
3. Coloque em `benchmark/inputs/real/<cenario>/` seguindo o schema de
   `CONTRACT.md`
4. Rode `python3 run_validation.py --detector cpp-omr --subset real`

## Arquitetura

`omr.cpp` implementa o pipeline:

1. **Detecção de marcadores fiduciais** — threshold + `connectedComponentsWithStats`
   isola 4 quadrados nos cantos da folha.
2. **Homografia perspectiva** — `getPerspectiveTransform` + `warpPerspective`
   alinha a folha com o template. Usa imgproc (não calib3d), compatível com
   opencv-mobile.
3. **Classificação de bolhas** — por fill ratio + confidence score, com
   detecção de `NO_MARK` / `MULTI_MARK` / `UNCLEAR`.
4. **Envelope JSON** — normalizado com `error_code` em todo retorno (sucesso
   ou falha), ver `CONTRACT.md`.

A mesma `omr.cpp` compila sem mudanças para desktop/Android/iOS. Dependências
transitivas (OpenMP no Android via `libomp.a` custom, GCD no iOS, sistema no
desktop) são resolvidas pelo build system de cada plataforma.

## Contribuindo

Este repo é um mirror de validação/benchmark — PRs são bem-vindos para
melhorias no motor, cobertura de plataformas (armeabi-v7a, iOS), e casos de
teste adicionais. Ver `CONTRACT.md` para a interface estável.

## Licença

MIT — ver [LICENSE](LICENSE).
