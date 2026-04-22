package br.com.testemobile.omr

import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var imagePath: EditText
    private lateinit var detectButton: Button
    private lateinit var resultView: TextView
    private lateinit var statusLabel: TextView
    private lateinit var versionLabel: TextView

    // Template v1 do motor, pre-convertido a partir do template OMRChecker do
    // conjunto `inputs/real/01-celular-lampada/` via regra de
    // `detectors/cpp_omr.py::_translate_template_if_needed`.
    // Carregado sob demanda; o JSON nao muda entre chamadas.
    private val templateJson: String by lazy {
        assets.open("template-01-celular-lampada.json")
            .bufferedReader()
            .use { it.readText() }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        imagePath = findViewById(R.id.imagePath)
        detectButton = findViewById(R.id.detectButton)
        resultView = findViewById(R.id.resultView)
        statusLabel = findViewById(R.id.statusLabel)
        versionLabel = findViewById(R.id.versionLabel)

        versionLabel.text = "libomr " + OmrNative.nativeVersion()
        statusLabel.text = getString(R.string.status_ready)

        detectButton.setOnClickListener {
            runDetection(imagePath.text.toString().trim())
        }
    }

    // Chamada bloqueia ~1-2s em device mid-range, entao roda em Thread separada
    // pra nao travar a UI (Android nega modificacoes em Views fora do main thread,
    // dai o `runOnUiThread` para atualizar os TextView no fim).
    // Throwable (nao Exception) porque UnsatisfiedLinkError — falha de carga da .so
    // ou mismatch de assinatura JNI — herda de Error.
    private fun runDetection(path: String) {
        detectButton.isEnabled = false
        statusLabel.text = getString(R.string.status_running)
        resultView.text = ""

        Thread {
            val start = System.currentTimeMillis()
            val result = try {
                OmrNative.nativeDetect(path, templateJson)
            } catch (t: Throwable) {
                Log.e(TAG, "nativeDetect falhou", t)
                """{"error":"${t.javaClass.simpleName}: ${t.message}"}"""
            }
            val elapsed = System.currentTimeMillis() - start
            Log.d(TAG, "nativeDetect(${path}) -> ${elapsed}ms\n$result")

            runOnUiThread {
                statusLabel.text = "Pronto — ${elapsed} ms (JNI + motor + I/O)"
                resultView.text = result
                detectButton.isEnabled = true
            }
        }.start()
    }

    companion object {
        private const val TAG = "omr-demo"
    }
}
