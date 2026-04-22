// Ponte JNI para o motor OMR.
//
// Expoe a API C de omr.h como metodos estaticos nativos da classe
// `br.com.testemobile.omr.OmrNative` (ver demo-app/app/src/main/java/...).
//
// Formato de retorno: sempre uma string JSON.
// - Sucesso: o conteudo de OmrResult.json_result (definido em CONTRACT.md).
// - Falha:   {"error": "<msg>", "status": <OmrStatus>}.
//
// Essa convencao evita ter que modelar OmrResult em Kotlin — o caller faz
// parse do JSON e verifica a presenca do campo "error".

#include <jni.h>
#include <string>
#include "omr.h"

namespace {

std::string make_error_json(OmrStatus status, const char* message) {
    std::string msg = (message != nullptr) ? message : "unknown error";
    // escape minimo de aspas no message (suficiente para as mensagens
    // geradas internamente pelo motor, que nao contem JSON arbitrario)
    std::string escaped;
    escaped.reserve(msg.size() + 8);
    for (char c : msg) {
        if (c == '"' || c == '\\') escaped.push_back('\\');
        escaped.push_back(c);
    }
    return std::string("{\"error\":\"") + escaped +
           "\",\"status\":" + std::to_string(static_cast<int>(status)) + "}";
}

}  // namespace

extern "C" JNIEXPORT jstring JNICALL
Java_br_com_testemobile_omr_OmrNative_nativeDetect(
        JNIEnv* env, jclass /*clazz*/,
        jstring jImagePath, jstring jTemplateJson) {
    const char* imagePath = env->GetStringUTFChars(jImagePath, nullptr);
    const char* templateJson = env->GetStringUTFChars(jTemplateJson, nullptr);

    std::string out;
    OmrResult* result = omr_detect(imagePath, templateJson);
    // O motor ja serializa erros estruturados em json_result (ver CONTRACT.md:
    // status "error" + error_code + metadata). Preservar esse JSON tal qual —
    // fabricar o fallback apenas quando o motor nao entregou nada (falha
    // catastrofica antes do pipeline rodar).
    if (result != nullptr && result->json_result != nullptr) {
        out.assign(result->json_result);
    } else {
        OmrStatus st = (result != nullptr) ? result->status : OMR_ERR_INTERNAL;
        const char* msg = (result != nullptr) ? result->error_message : nullptr;
        out = make_error_json(st, msg);
    }

    env->ReleaseStringUTFChars(jImagePath, imagePath);
    env->ReleaseStringUTFChars(jTemplateJson, templateJson);
    if (result != nullptr) {
        omr_free(result);
    }

    return env->NewStringUTF(out.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_br_com_testemobile_omr_OmrNative_nativeVersion(
        JNIEnv* env, jclass /*clazz*/) {
    const char* v = omr_version();
    return env->NewStringUTF(v != nullptr ? v : "unknown");
}
