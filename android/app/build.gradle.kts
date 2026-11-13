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
        versionCode = 5
        // v1.2.0：移除手机端视角轴（用户买了头瞄，视角交给头瞄）。
        // v1.3.0：起降页新增减速板开/收、机轮刹车（按住=刹车）三个按钮。
        // v1.3.1：把减速板/机轮刹车从杆位区移到右侧「校零」与「解锁」之间。
        // v1.00 是最后一个保留视角的版本，详见 docs/HANDOFF.md。
        versionName = "1.3.1"
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
