// CLI de teste para o motor OMR.
// Uso: omr_cli <image_path> <template_json_path>
// Saida: json_result em stdout; codigo de saida 0 se OK, != 0 em erro.

#include "omr.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/resource.h>

static std::string read_file(const char* path) {
    std::ifstream f(path);
    if (!f) return {};
    std::ostringstream buf;
    buf << f.rdbuf();
    return buf.str();
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::fprintf(stderr, "Uso: %s <image> <template.json>\n", argv[0]);
        return 2;
    }
    std::string tmpl = read_file(argv[2]);
    if (tmpl.empty()) {
        std::fprintf(stderr, "Nao foi possivel ler template: %s\n", argv[2]);
        return 2;
    }

    OmrResult* r = omr_detect(argv[1], tmpl.c_str());
    std::puts(r->json_result ? r->json_result : "{}");
    int code = (r->status == OMR_OK) ? 0 : 1;
    omr_free(r);

    // Peak RSS em KB (ru_maxrss em Linux/Android e KB, em macOS e bytes).
    // Emitir em stderr pra nao contaminar o JSON de stdout.
    struct rusage ru{};
    if (getrusage(RUSAGE_SELF, &ru) == 0) {
        std::fprintf(stderr, "peak_rss_kb=%ld\n", ru.ru_maxrss);
    }
    return code;
}
