// Motor OMR nativo — API C estavel para FFI.
// Ver CONTRACT.md para o shape do json_result e codigos de erro.

#ifndef OMR_H
#define OMR_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    OMR_OK = 0,
    OMR_ERR_IO = 1,
    OMR_ERR_TEMPLATE_INVALID = 2,
    OMR_ERR_MARKERS_NOT_FOUND = 3,
    OMR_ERR_ALIGNMENT_FAILED = 4,
    OMR_ERR_INTERNAL = 99
} OmrStatus;

typedef struct {
    OmrStatus status;
    const char* json_result;
    const char* error_message;
} OmrResult;

OmrResult* omr_detect(const char* image_path, const char* template_json);
void omr_free(OmrResult* result);
const char* omr_version(void);

#ifdef __cplusplus
}
#endif

#endif
