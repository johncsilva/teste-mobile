# omr-demo — Mini-app Android standalone

Prova de conceito da integracao `libomr.so` + JNI. Carrega o motor nativo
via `System.loadLibrary`, le um `template.json` do asset, chama
`OmrNative.nativeDetect(path, templateJson)` e exibe o JSON retornado.

**Escopo:** validar end-to-end no device (build → install → rodar) com
imagem pre-copiada via `adb push`. Camera / intent de galeria ficam
fora do escopo deste demo — integracao RN/Flutter fica para o app consumidor.

## Pre-requisitos

- JDK 17
- Android SDK (compileSdk 34, minSdk 21)
- `adb` no PATH + device arm64-v8a conectado (USB debugging ON)
- `libomr.so` arm64-v8a ja compilada em `build-android-arm64-v8a/`
  (rode `android/build.sh arm64-v8a` antes se faltar)

## Gerar o Gradle Wrapper (primeira vez)

Este diretorio nao versiona `gradlew` / `gradle-wrapper.jar`. Opcoes:

```bash
# A) via bootstrap (sem exigir gradle instalado — baixa distro em cache local)
cd android/demo-app
./bootstrap.sh

# B) se voce ja tem gradle no PATH
gradle wrapper --gradle-version 8.9
```

Tambem funciona abrir no Android Studio e aceitar "Sync Project with Gradle
Files" — o AS cuida do wrapper.

## Build

```bash
./gradlew :app:assembleDebug
```

A task `copyNativeLibs` roda antes do `preBuild` e copia a `.so` do
diretorio de build do motor para `app/src/main/jniLibs/arm64-v8a/`.
Se a `.so` estiver ausente, o build falha com mensagem explicita.

APK de saida: `app/build/outputs/apk/debug/app-debug.apk`.

## Install + smoke-test

```bash
# 1. instala no device
./gradlew :app:installDebug

# 2. empurra uma foto real pro /data/local/tmp
adb push ../../../omr-checker-benchmark/inputs/real/01-celular-lampada/sheet-01.jpg \
    /data/local/tmp/sheet.jpg

# 3. abre o app (pelo launcher ou via adb)
adb shell am start -n br.com.testemobile.omr/.MainActivity

# 4. no app, clica "Detect" (o path default ja aponta pra /data/local/tmp/sheet.jpg)
```

Esperado no `resultView`: JSON com `status: "ok"`, 30 questoes
(`q1`..`q30`) e `metadata.processing_ms` entre 500-2000 ms (depende do
SoC). Logcat: filtre por `omr-demo` ou `omr`.

## Trocar foto / template

- Outra foto: substitui `/data/local/tmp/sheet.jpg` via `adb push` e clica
  Detect de novo. Nenhum rebuild necessario.
- Outro template: adiciona outro `template-*.json` em
  `app/src/main/assets/` e troca o nome em `MainActivity.templateJson`.

## Estrutura

```
demo-app/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── app/
│   ├── build.gradle.kts        # copyNativeLibs + ABI filter
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── assets/template-01-celular-lampada.json  # schema v1
│       ├── java/br/com/testemobile/omr/
│       │   ├── OmrNative.kt    # binding JNI (nome casa com OmrJni.cpp)
│       │   └── MainActivity.kt
│       └── res/layout/activity_main.xml
```

## Troubleshooting

| Sintoma | Causa | Fix |
|---|---|---|
| `UnsatisfiedLinkError: Native method not found ... nativeDetect` | assinatura Kotlin != simbolo JNI | confirmar pacote+classe em `OmrNative.kt` = `Java_br_com_testemobile_omr_OmrNative_nativeDetect` |
| `java.lang.UnsatisfiedLinkError: dlopen failed` | `.so` ausente no APK | rodar `./gradlew copyNativeLibs` ou conferir `build-android-arm64-v8a/libomr.so` |
| `status: "error", error_code: "MARKERS_NOT_FOUND"` | foto sem os 4 quadrados fiduciais visiveis | recapturar com folha plana + boa luz |
