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
        versionCode = 2
        // v1.00 只归档了 Android APK；v1.1.0 补上 iPad 端发布包，并把两端版本号对齐。
        // 仍是保留视角功能的版本（用户换头瞄后才会移除）。
        versionName = "1.1.0"
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
            // v1.00 自用发布：沿用 AGP 自带的 debug 签名（~/.android/debug.keystore）。
            // 好处是 release 包能直接覆盖安装到已有 debug 版，不用先卸载。
            // 将来要对外分发时换成正式 keystore，密码走环境变量，别写进这个文件。
            signingConfig = signingConfigs.getByName("debug")
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
        // assembleRelease 默认挂 lintVital，它会去联网拉
        // com.android.tools.lint:lint-gradle，本机 --offline 没有这个缓存 → 构建失败。
        // v1.00 是自用离线发布，行为由 85 项回归覆盖，lint 需要时单独跑即可。
        checkReleaseBuilds = false
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
