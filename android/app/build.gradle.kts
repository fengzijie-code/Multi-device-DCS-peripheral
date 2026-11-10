plugins {
    id("com.android.application")
    // 不要加 org.jetbrains.kotlin.android —— AGP 9 内置 Kotlin，加了会直接失败。
    // 但 Compose 编译器插件仍然是必需的（Kotlin 2.0 起强制要求）。
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.fengzijie.dcsperipheral"

    // 本机装的是带 minor 版本的 SDK（android-37.0，对应 Android 17）。
    compileSdk = 37

    defaultConfig {
        applicationId = "com.fengzijie.dcsperipheral"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0-p0"
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
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

    buildFeatures {
        compose = true
    }

    lint {
        // P0 阶段先不因为缺无障碍描述之类的问题中断构建
        abortOnError = false
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
