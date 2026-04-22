package br.com.testemobile.omr

/**
 * Ponte JNI para o motor OMR nativo (libomr.so).
 *
 * Os nomes de pacote + classe + metodo precisam bater exatamente com os
 * simbolos exportados em `android/jni/OmrJni.cpp`
 * (Java_br_com_testemobile_omr_OmrNative_nativeDetect / _nativeVersion).
 *
 * Retorno de `nativeDetect` e sempre uma string JSON:
 *   - Sucesso: shape de CONTRACT.md (`status: "ok"`, `questions`, `metadata`)
 *   - Erro estruturado do motor: `status: "error"`, `error_code`, `error_message`
 *   - Falha catastrofica no JNI: `{"error": "...", "status": <int>}`
 */
object OmrNative {

    init {
        System.loadLibrary("omr")
    }

    @JvmStatic
    external fun nativeDetect(imagePath: String, templateJson: String): String

    @JvmStatic
    external fun nativeVersion(): String
}
