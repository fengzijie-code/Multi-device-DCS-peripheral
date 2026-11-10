// AGP 9.0 起内置 Kotlin 支持，因此不应用 org.jetbrains.kotlin.android。
// 但 AGP 9.5.1 自带的 KGP 是 2.2.10，而 Compose BOM 2026.09 的产物是用更新的
// Kotlin 元数据编译的，2.2 的编译器读不了（会报 incompatible version of Kotlin）。
// 所以这里显式把 KGP 抬到 2.4.21，并让 Compose 编译器插件用同一版本。
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.4.21")
    }
}

plugins {
    id("com.android.application") version "9.5.1" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21" apply false
}
