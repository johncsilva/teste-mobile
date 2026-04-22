plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "br.com.testemobile.omr"
    compileSdk = 35

    defaultConfig {
        applicationId = "br.com.testemobile.omr"
        minSdk = 21
        targetSdk = 35
        versionCode = 1
        versionName = "0.1-spike"
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        jniLibs {
            useLegacyPackaging = false
        }
    }
}

// Copia libomr.so do build cross-compile para jniLibs/ antes do preBuild.
// Fonte canonica: build-android-<abi>/libomr.so (gerada por android/build.sh).
// Falha explicitamente se a .so nao existir — evita APK silenciosamente sem motor.
val copyNativeLibs by tasks.registering(Copy::class) {
    val abis = listOf("arm64-v8a")
    abis.forEach { abi ->
        from(rootProject.file("../../build-android-$abi/libomr.so"))
        into(layout.projectDirectory.dir("src/main/jniLibs/$abi"))
    }
    doFirst {
        abis.forEach { abi ->
            val so = rootProject.file("../../build-android-$abi/libomr.so")
            check(so.exists()) {
                "libomr.so nao encontrada em $so.\n" +
                "Rode antes: cd android && ANDROID_NDK_ROOT=... ./build.sh $abi"
            }
        }
    }
}
tasks.named("preBuild") { dependsOn(copyNativeLibs) }

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}
