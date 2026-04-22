// Implementacao do motor OMR.
//
// Pipeline:
//   1. imread(image_path)
//   2. resize para page_dimensions do template (pre-alinhamento grosseiro)
//   3. detect_fiducials: template matching nas 4 esquinas esperadas
//      - se 4 encontrados: getPerspectiveTransform + warpPerspective
//      - se <4: retorna OMR_ERR_MARKERS_NOT_FOUND
//      - se template nao tem fiduciais: pula alinhamento (modo sinteticos)
//   4. grayscale + threshold Otsu + BINARY_INV
//   5. para cada bolha do template: fill_ratio do ROI thresholded
//   6. classify: pico relativo ao baseline
//   7. serializa JSON

#include "omr.h"

#include <cstdlib>
#include <cstring>
#include <string>
#include <sstream>
#include <vector>

#include <opencv2/opencv.hpp>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {

struct Bubble {
    std::string question;
    std::string alternative;
    int cx;
    int cy;
};

struct Template {
    int page_w;
    int page_h;
    int bubble_w;
    int bubble_h;
    double thresh_low;
    double thresh_high;
    std::string id;
    std::vector<Bubble> bubbles;
    std::vector<cv::Point2f> fiducials;  // 4 posicoes esperadas dos marcadores
    int fiducial_size = 0;               // lado do quadrado fiducial (px)
};

Template parse_template(const std::string& template_json) {
    Template t;
    auto j = json::parse(template_json);

    t.id = j.value("id", std::string("unknown"));
    t.page_w = j.at("page_dimensions")[0].get<int>();
    t.page_h = j.at("page_dimensions")[1].get<int>();
    t.bubble_w = j.at("bubble_dimensions")[0].get<int>();
    t.bubble_h = j.at("bubble_dimensions")[1].get<int>();
    t.thresh_low = j.at("thresholds").value("low", 0.25);
    t.thresh_high = j.at("thresholds").value("high", 0.60);

    if (j.contains("fiducials")) {
        const auto& f = j["fiducials"];
        t.fiducial_size = f.value("size_px", 0);
        if (f.contains("positions")) {
            for (const auto& p : f["positions"]) {
                t.fiducials.emplace_back(p[0].get<float>(), p[1].get<float>());
            }
        }
    }

    for (const auto& block : j.at("blocks")) {
        auto alternatives = block.at("alternatives").get<std::vector<std::string>>();
        int origin_x = block.at("origin")[0].get<int>();
        int origin_y = block.at("origin")[1].get<int>();
        int bubble_gap = block.at("bubble_gap").get<int>();
        int label_gap = block.at("label_gap").get<int>();
        int q_start = block.at("questions").at("start").get<int>();
        int q_end = block.at("questions").at("end").get<int>();

        int row = 0;
        for (int q = q_start; q <= q_end; ++q) {
            int cy = origin_y + row * label_gap;
            for (size_t col = 0; col < alternatives.size(); ++col) {
                Bubble b;
                b.question = "q" + std::to_string(q);
                b.alternative = alternatives[col];
                b.cx = origin_x + static_cast<int>(col) * bubble_gap;
                b.cy = cy;
                t.bubbles.push_back(b);
            }
            ++row;
        }
    }
    return t;
}

// Detecta os 4 marcadores fiduciais (quadrados pretos) em janelas locais
// ao redor das posicoes esperadas. Retorna vetor do mesmo tamanho que
// expected_positions, com Point2f(-1,-1) para marcadores nao encontrados.
//
// Abordagem: matchTemplate com um patch totalmente preto do tamanho do
// fiducial. Metrica: TM_SQDIFF_NORMED (min=0 em match perfeito).
std::vector<cv::Point2f> detect_fiducials(const cv::Mat& gray,
                                          const std::vector<cv::Point2f>& expected,
                                          int size_px) {
    std::vector<cv::Point2f> detected(expected.size(), cv::Point2f(-1.f, -1.f));
    if (size_px <= 0 || expected.empty()) return detected;

    // Abordagem: threshold local na janela de busca + connected components,
    // pega o maior blob preto cuja area seja compativel com o marker esperado.
    // Mais robusto que matchTemplate para alvos binarios (um sem antialiasing
    // pode nao ter um pico nitido em qualquer metrica de template matching).
    constexpr int SEARCH_RADIUS = 150;  // +-150px (tolera rotacao ate ~8°)
    const double expected_area = static_cast<double>(size_px) * size_px;
    const double min_area = 0.3 * expected_area;  // ate ~55% encolhido
    const double max_area = 3.0 * expected_area;  // ate ~73% inflado

    for (size_t i = 0; i < expected.size(); ++i) {
        int ex = static_cast<int>(expected[i].x);
        int ey = static_cast<int>(expected[i].y);
        int x0 = std::max(0, ex - SEARCH_RADIUS);
        int y0 = std::max(0, ey - SEARCH_RADIUS);
        int x1 = std::min(gray.cols, ex + SEARCH_RADIUS);
        int y1 = std::min(gray.rows, ey + SEARCH_RADIUS);
        if (x1 <= x0 || y1 <= y0) continue;

        cv::Mat window = gray(cv::Rect(x0, y0, x1 - x0, y1 - y0));
        cv::Mat binary;
        // adaptiveThreshold local em vez de Otsu: captura real com celular
        // pode ter sombra atravessando a janela (ex: lampada de teto a noite).
        // Otsu global/local une o fiducial com a sombra num blob unico fora
        // da faixa de area, perdendo o marker. adaptiveThreshold compara cada
        // pixel com a media de uma vizinhanca pequena (51px), entao o
        // fiducial (muito mais escuro que seu entorno local) e sempre
        // destacado mesmo em regiao globalmente sombreada.
        cv::adaptiveThreshold(window, binary, 255,
                              cv::ADAPTIVE_THRESH_MEAN_C,
                              cv::THRESH_BINARY_INV, 51, 15);

        cv::Mat labels, stats, centroids;
        int n = cv::connectedComponentsWithStats(binary, labels, stats, centroids);

        // Filtros de forma: um fiducial real e um quadrado CHEIO. Excluimos
        // candidatos que sao mais proximos mas tem aspecto/preenchimento fora
        // da faixa esperada — tipicamente linhas/bordas de sombra que a
        // janela de busca pegou junto com o quadrado real. Sem esses filtros
        // o motor pode escolher um blob vizinho alongado (ex: dobra de pano
        // fora do papel, linha fina do rodape) em vez do fiducial.
        constexpr double MAX_ASPECT = 1.5;   // lado maior / lado menor
        constexpr double MIN_EXTENT = 0.70;  // area / (bbox_w * bbox_h)

        int best_label = -1;
        double best_dist = 1e9;
        for (int k = 1; k < n; ++k) {  // 0 = background
            double area = stats.at<int>(k, cv::CC_STAT_AREA);
            if (area < min_area || area > max_area) continue;

            int bw = stats.at<int>(k, cv::CC_STAT_WIDTH);
            int bh = stats.at<int>(k, cv::CC_STAT_HEIGHT);
            if (bw <= 0 || bh <= 0) continue;
            double aspect = static_cast<double>(std::max(bw, bh)) / std::min(bw, bh);
            double extent = area / static_cast<double>(bw * bh);
            if (aspect > MAX_ASPECT || extent < MIN_EXTENT) continue;

            // distancia do centroide ao centro esperado (dentro da janela)
            double cx = centroids.at<double>(k, 0);
            double cy = centroids.at<double>(k, 1);
            double dx = cx - (ex - x0);
            double dy = cy - (ey - y0);
            double dist = dx * dx + dy * dy;
            if (dist < best_dist) {
                best_dist = dist;
                best_label = k;
            }
        }

        if (best_label < 0) continue;
        detected[i] = cv::Point2f(
            static_cast<float>(x0 + centroids.at<double>(best_label, 0)),
            static_cast<float>(y0 + centroids.at<double>(best_label, 1))
        );
    }
    return detected;
}

double fill_ratio(const cv::Mat& thresh, int cx, int cy, int w, int h) {
    int x0 = std::max(0, cx - w / 2);
    int y0 = std::max(0, cy - h / 2);
    int x1 = std::min(thresh.cols, cx + w / 2);
    int y1 = std::min(thresh.rows, cy + h / 2);
    if (x1 <= x0 || y1 <= y0) return 0.0;

    cv::Rect roi(x0, y0, x1 - x0, y1 - y0);
    cv::Mat crop = thresh(roi);
    // apos threshold BINARY_INV: pixel preenchido (marcado) vira 255.
    double mean = cv::mean(crop)[0];
    return mean / 255.0;
}

OmrResult* make_result(OmrStatus status, const std::string& json_str, const std::string& err) {
    auto* r = new OmrResult();
    r->status = status;
    char* js = new char[json_str.size() + 1];
    std::memcpy(js, json_str.c_str(), json_str.size() + 1);
    r->json_result = js;
    if (err.empty()) {
        r->error_message = nullptr;
    } else {
        char* em = new char[err.size() + 1];
        std::memcpy(em, err.c_str(), err.size() + 1);
        r->error_message = em;
    }
    return r;
}

OmrResult* make_error(OmrStatus status, const std::string& code, const std::string& message, long elapsed_ms) {
    json j;
    j["status"] = "error";
    j["error_code"] = code;
    j["error_message"] = message;
    j["metadata"] = { {"processing_ms", elapsed_ms} };
    return make_result(status, j.dump(), message);
}

}  // namespace

extern "C" {

OmrResult* omr_detect(const char* image_path, const char* template_json) {
    // Barreira externa: nenhuma excecao C++ pode cruzar a fronteira FFI
    // (undefined behavior em funcao extern "C"). Capturamos std::bad_alloc,
    // std::exception e ... para garantir retorno estruturado mesmo em OOM.
    try {
        auto t0 = cv::getTickCount();
        if (!image_path || !template_json) {
            return make_error(OMR_ERR_IO, "IO", "image_path ou template_json nulo", 0);
        }

        Template tmpl;
        try {
            tmpl = parse_template(template_json);
        } catch (const std::exception& e) {
            return make_error(OMR_ERR_TEMPLATE_INVALID, "TEMPLATE_INVALID",
                              std::string("Falha ao parsear template: ") + e.what(), 0);
        }

    cv::Mat img = cv::imread(image_path, cv::IMREAD_COLOR);
    if (img.empty()) {
        return make_error(OMR_ERR_IO, "IO",
                          std::string("Nao foi possivel ler a imagem: ") + image_path, 0);
    }

    cv::Mat resized;
    if (img.cols != tmpl.page_w || img.rows != tmpl.page_h) {
        cv::resize(img, resized, cv::Size(tmpl.page_w, tmpl.page_h));
    } else {
        resized = img;
    }

    cv::Mat gray;
    cv::cvtColor(resized, gray, cv::COLOR_BGR2GRAY);

    // Fase 4.2: alinhamento via fiduciais (se o template tiver 4 posicoes).
    // Sem fiduciais (modo sinteticos): pula alinhamento, assume imagem ja alinhada.
    int markers_detected = 0;
    if (tmpl.fiducials.size() == 4 && tmpl.fiducial_size > 0) {
        auto detected = detect_fiducials(gray, tmpl.fiducials, tmpl.fiducial_size);
        std::vector<cv::Point2f> src, dst;
        for (size_t i = 0; i < detected.size(); ++i) {
            if (detected[i].x >= 0 && detected[i].y >= 0) {
                src.push_back(detected[i]);
                dst.push_back(tmpl.fiducials[i]);
                ++markers_detected;
            }
        }
        if (markers_detected < 4) {
            double freq = cv::getTickFrequency();
            long elapsed = static_cast<long>(1000.0 * (cv::getTickCount() - t0) / freq);
            return make_error(OMR_ERR_MARKERS_NOT_FOUND, "MARKERS_NOT_FOUND",
                              std::to_string(markers_detected) + " de 4 marcadores detectados. "
                              "Recapturar com folha plana e bem iluminada.", elapsed);
        }
        // getPerspectiveTransform (imgproc) resolve sistema linear exato para 4
        // pontos — equivalente a findHomography sem RANSAC. Escolhido no lugar
        // de findHomography porque calib3d nao esta em opencv-mobile (Fase 5).
        cv::Mat H = cv::getPerspectiveTransform(src, dst);
        if (H.empty()) {
            double freq = cv::getTickFrequency();
            long elapsed = static_cast<long>(1000.0 * (cv::getTickCount() - t0) / freq);
            return make_error(OMR_ERR_ALIGNMENT_FAILED, "ALIGNMENT_FAILED",
                              "getPerspectiveTransform nao convergiu", elapsed);
        }
        cv::Mat warped;
        cv::warpPerspective(gray, warped, H, cv::Size(tmpl.page_w, tmpl.page_h));
        gray = warped;
    }

    cv::Mat thresh;
    cv::threshold(gray, thresh, 0, 255, cv::THRESH_BINARY_INV | cv::THRESH_OTSU);

    // Agrupar por questao para classificar.
    json questions = json::object();
    std::string current_q;
    std::vector<std::pair<std::string, double>> ratios;

    // Classificacao por pico relativo ao baseline das outras alternativas:
    //   top = maior fill
    //   baseline = media dos outros fills
    //   selected = top se top >= MIN_ABS E top >= RATIO_BASELINE * baseline
    //   multi_mark = >=2 alternativas acima de MULTI_ABS E razao top/second < RATIO_MULTI
    //
    // Razao contra baseline e mais estavel que contra second, porque o second
    // pode ser inflado por bleed-over da bolha vizinha (em layouts densos como lg).
    constexpr double MIN_ABS = 0.08;
    constexpr double RATIO_BASELINE = 1.8;
    constexpr double MULTI_ABS = 0.12;
    constexpr double RATIO_MULTI = 1.3;

    auto classify = [&](const std::string& q, std::vector<std::pair<std::string, double>>& rs) {
        json qj;
        std::vector<double> fills;
        for (auto& pr : rs) fills.push_back(pr.second);
        qj["fill_ratios"] = fills;

        std::vector<size_t> idx(rs.size());
        for (size_t i = 0; i < idx.size(); ++i) idx[i] = i;
        std::sort(idx.begin(), idx.end(),
                  [&](size_t a, size_t b) { return rs[a].second > rs[b].second; });

        double top = rs[idx[0]].second;
        double second = rs.size() > 1 ? rs[idx[1]].second : 0.0;
        double others_sum = 0.0;
        for (size_t i = 1; i < idx.size(); ++i) others_sum += rs[idx[i]].second;
        double baseline = (idx.size() > 1) ? others_sum / (idx.size() - 1) : 0.0;

        size_t above_multi = 0;
        for (auto& pr : rs) if (pr.second >= MULTI_ABS) ++above_multi;

        std::vector<std::string> flags;
        if (above_multi >= 2 && top < RATIO_MULTI * second) {
            qj["selected"] = nullptr;
            flags.push_back("multi_mark");
        } else if (top >= MIN_ABS && (baseline == 0.0 || top >= RATIO_BASELINE * baseline)) {
            qj["selected"] = rs[idx[0]].first;
            qj["confidence"] = top;
            if (second > 0.0 && top < 1.3 * second) flags.push_back("ambiguous");
        } else {
            qj["selected"] = nullptr;
            flags.push_back("no_mark");
        }
        if (!flags.empty()) qj["flags"] = flags;
        questions[q] = qj;
    };

    for (const auto& b : tmpl.bubbles) {
        double r = fill_ratio(thresh, b.cx, b.cy, tmpl.bubble_w, tmpl.bubble_h);
        if (!current_q.empty() && b.question != current_q) {
            classify(current_q, ratios);
            ratios.clear();
        }
        current_q = b.question;
        ratios.emplace_back(b.alternative, r);
    }
    if (!current_q.empty()) classify(current_q, ratios);

    double freq = cv::getTickFrequency();
    long elapsed_ms = static_cast<long>(1000.0 * (cv::getTickCount() - t0) / freq);

    json j;
    j["status"] = "ok";
    j["questions"] = questions;
    j["metadata"] = {
        {"processing_ms", elapsed_ms},
        {"template_id", tmpl.id},
        {"markers_detected", markers_detected}
    };
        return make_result(OMR_OK, j.dump(), "");
    } catch (const std::bad_alloc&) {
        // Fallback leve: sem alocar mais heap no json (pode falhar de novo).
        auto* r = new (std::nothrow) OmrResult();
        if (!r) return nullptr;
        r->status = OMR_ERR_INTERNAL;
        r->json_result = nullptr;
        r->error_message = "out of memory";
        return r;
    } catch (const std::exception& e) {
        try {
            return make_error(OMR_ERR_INTERNAL, "INTERNAL", e.what(), 0);
        } catch (...) {
            return nullptr;
        }
    } catch (...) {
        try {
            return make_error(OMR_ERR_INTERNAL, "INTERNAL", "excecao desconhecida", 0);
        } catch (...) {
            return nullptr;
        }
    }
}

void omr_free(OmrResult* result) {
    if (!result) return;
    delete[] result->json_result;
    delete[] result->error_message;
    delete result;
}

const char* omr_version(void) {
    return "cpp-omr 0.1.0 (fase-4, sem fiduciais)";
}

}
