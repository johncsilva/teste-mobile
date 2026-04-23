# Contrato do Motor OMR Nativo

## Objetivo
Definir a interface pública do motor OMR que será implementada em C++/opencv-mobile e consumida por RN/Flutter via FFI/JSI.

## Princípios
- **Stateless**: sem estado global entre chamadas. Thread-safe por default.
- **Template-driven**: layout da folha é input, não assumido.
- **Single call**: uma única travessia de ponte por folha processada.
- **Error-explicit**: todo erro é estruturado, não exception silenciosa.
- **Sem fallback escondido**: se o motor não tem confiança, retorna `null` ou flag explícita — nunca chuta.

---

## API principal

### C (header exposto via FFI)

```c
// result.h

typedef enum {
    OMR_OK = 0,
    OMR_ERR_IO = 1,               // imread falhou / path inválido
    OMR_ERR_TEMPLATE_INVALID = 2, // json malformado ou schema inválido
    OMR_ERR_MARKERS_NOT_FOUND = 3, // fiduciais não detectados
    OMR_ERR_ALIGNMENT_FAILED = 4,  // warp/alinhamento não convergiu
    OMR_ERR_INTERNAL = 99
} OmrStatus;

typedef struct {
    OmrStatus status;
    const char* json_result;      // utf-8, owned pela lib (livre via omr_free)
    const char* error_message;    // utf-8, null se status == OMR_OK
} OmrResult;

// Processa uma folha. Thread-safe.
//
// image_path: utf-8, path para PNG/JPG
// template_json: utf-8, conteúdo do template (ver schema abaixo)
//
// Retorno: OmrResult alocado. Chamar omr_free quando terminar.
OmrResult* omr_detect(const char* image_path, const char* template_json);

// Libera memória alocada por omr_detect.
void omr_free(OmrResult* result);

// Versão da lib — útil para feature gating do lado do app.
const char* omr_version(void);
```

### Formato do `json_result` (sucesso)

```json
{
  "status": "ok",
  "questions": {
    "q1": { "selected": "A", "confidence": 0.95, "fill_ratios": [0.87, 0.02, 0.01, 0.03, 0.02] },
    "q2": { "selected": "B", "confidence": 0.91, "fill_ratios": [0.02, 0.85, 0.03, 0.02, 0.01] },
    "q3": { "selected": null, "flags": ["multi_mark"], "fill_ratios": [0.80, 0.01, 0.75, 0.02, 0.01] },
    "q4": { "selected": null, "flags": ["no_mark"], "fill_ratios": [0.02, 0.01, 0.03, 0.02, 0.01] }
  },
  "metadata": {
    "processing_ms": 420,
    "template_id": "edu-30q-5alt-2col-med",
    "markers_detected": 4,
    "fiducials": [[285.4, 290.7], [3115.2, 287.1], [280.9, 4636.8], [3120.5, 4632.4]],
    "image_size": [4160, 3120]
  }
}
```

### Campos de metadata

| Campo | Tipo | Descrição |
|---|---|---|
| `processing_ms` | int | Tempo total do pipeline em milissegundos |
| `template_id` | string | Valor de `id` do template |
| `markers_detected` | int | Quantos dos 4 fiduciais foram localizados (0..4) |
| `fiducials` | `[[x,y], [x,y], [x,y], [x,y]]` ou `null` | Coordenadas dos 4 marcadores detectados no **espaço da imagem de entrada** (mesma resolução da foto passada em `image_path`). Ordem idêntica à do template (`positions[0..3]`). Se um marcador não foi detectado, seu slot é `null`. Campo é `null` quando o template não declara `fiducials`. Útil para overlay de auditoria e homografia no cliente. |
| `image_size` | `[width, height]` | Dimensões da imagem de entrada em pixels. Pareado com `fiducials` para o cliente converter coordenadas se exibir em resolução diferente. |

### Formato do `json_result` (erro estrutural)

Mesmo shape, mas sem `questions`:
```json
{
  "status": "error",
  "error_code": "MARKERS_NOT_FOUND",
  "error_message": "Apenas 2 de 4 marcadores fiduciais encontrados. Recapturar com a folha plana e bem iluminada.",
  "metadata": { "processing_ms": 180 }
}
```

### Flags por questão

- `multi_mark` — mais de uma bolha com fill acima do limiar alto
- `no_mark` — nenhuma bolha acima do limiar baixo
- `ambiguous` — exatamente uma bolha, mas fill entre limiar baixo e alto

O app decide como apresentar cada flag.

---

## Schema de `template.json`

Versão mínima (subset compatível com OMRChecker + tolerância a futuro):

```json
{
  "version": 1,
  "id": "edu-30q-5alt-2col-med",
  "page_dimensions": [1654, 2339],
  "bubble_dimensions": [31, 31],
  "fiducials": {
    "type": "corner_squares",
    "size_px": 40,
    "positions": [
      [138, 138],
      [1516, 138],
      [138, 2201],
      [1516, 2201]
    ]
  },
  "blocks": [
    {
      "type": "mcq",
      "alternatives": ["A", "B", "C", "D", "E"],
      "origin": [260, 429],
      "bubble_gap": 51,
      "label_gap": 47,
      "questions": { "start": 1, "end": 15 }
    },
    {
      "type": "mcq",
      "alternatives": ["A", "B", "C", "D", "E"],
      "origin": [890, 429],
      "bubble_gap": 51,
      "label_gap": 47,
      "questions": { "start": 16, "end": 30 }
    }
  ],
  "thresholds": {
    "low": 0.25,
    "high": 0.60
  }
}
```

### Decisões de schema

| Decisão | Justificativa |
|---|---|
| `version` obrigatório | permite breaking changes sem quebrar apps antigos |
| `fiducials.positions` explícito (não computado) | motor não precisa saber geometria da folha; só template é fonte de verdade |
| `bubble_gap` / `label_gap` em vez de array de posições | folhas regulares são descritas em ~15 linhas; genéricas explicitam cada bolha |
| `thresholds` no template, não hardcode | diferentes canetas/impressoras exigem tuning — é atributo do template |
| Sem pré-processadores no template | motor sempre roda a mesma sequência; simplicidade > configurabilidade |

### Evoluções futuras (v2+)
- Blocos não-MCQ (integer fields para roll number, CPF)
- Layouts sem fiduciais (fallback a detecção por contorno da página)
- Múltiplas páginas por folha
- Templates paramétricos (gerador produz template a partir da config de geração)

---

## Pipeline interno (implementação)

Não faz parte do contrato — referência para quem for implementar:

```
1. imread(image_path)                                    # ~50 ms
2. resize_to(page_dimensions)                            # ~20 ms
3. detect_fiducials(fiducials.positions, size_px)        # ~50 ms
   - se <4 encontrados → OMR_ERR_MARKERS_NOT_FOUND
     (retorno de erro inclui `metadata.fiducials` parciais + `image_size` +
      `markers_detected` para app mostrar overlay de diagnostico)
4. warpPerspective para alinhar markers com positions    # ~30 ms
5. threshold global (Otsu ou fixo)                       # ~10 ms
6. for each block in blocks:
     for each question in block.questions:
       for each alternative:
         fill_ratio = mean_black_pixels(bubble_center, bubble_dims) / 255
       classify(fill_ratios, thresholds) → selected + flags
7. serializa JSON de saída
```

Alvo de tempo total: **< 500 ms em desktop**, **< 1500 ms em device mid-range**.

---

## Binding FFI — expectativas

### React Native (via JSI/FFI)
```ts
// Tipagem do lado JS
type OmrResult = {
  status: "ok" | "error";
  questions?: Record<string, { selected: string | null; confidence?: number; flags?: string[]; fill_ratios?: number[] }>;
  error_code?: string;
  error_message?: string;
  metadata: { processing_ms: number; template_id?: string; markers_detected?: number };
};

declare function detectOmr(imagePath: string, templateJson: string): Promise<OmrResult>;
```

- Retorno é `Promise` pois a chamada roda em thread nativa separada (evita block da JS thread).
- 1 chamada de bridge por folha. Sem loops JS↔nativo.

### Flutter (via FFI)
```dart
// Tipagem do lado Dart
class OmrResult {
  final String status;
  final Map<String, Question>? questions;
  final String? errorCode;
  final String? errorMessage;
  final Metadata metadata;
}

Future<OmrResult> detectOmr(String imagePath, String templateJson);
```

- Via `dart:ffi` e compute() para não bloquear UI thread.

---

## Contrato de testes

O motor deve passar a suite canônica em `benchmark/`:

1. **Sintéticos** (folhas geradas + bolhas simuladas): 100% acurácia em todas 7 variantes
2. **Perturbações**: ≥95% em ruído σ≤40, ≥90% em rotação ±3°, ≥95% em perspectiva ≤30px
3. **Reais**: ≥90% em fotos reais (conjunto a coletar)
4. **Performance**: <500ms/folha em laptop (x86_64)

Falha em qualquer desses critérios bloqueia merge.
