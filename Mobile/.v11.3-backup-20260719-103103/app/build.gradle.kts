import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use(::load)
}

fun quoted(value: String): String = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""
fun local(name: String, default: String = ""): String = localProperties.getProperty(name, default).trim().trim('"')

android {
    namespace = "com.oppw.monitor"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.oppw.monitor"
        minSdk = 26
        targetSdk = 37
        versionCode = 17
        versionName = "11.2.0"

        buildConfigField("String", "API_BASE_URL", quoted(local("OPPW_API_BASE_URL", "https://example.com/oppw-api/")))
        buildConfigField("long", "POLL_INTERVAL_MS", "5000L")
        buildConfigField("long", "API_STALE_SECONDS", "60L")
        buildConfigField("String", "FIREBASE_APPLICATION_ID", quoted(local("OPPW_FIREBASE_APPLICATION_ID")))
        buildConfigField("String", "FIREBASE_PROJECT_ID", quoted(local("OPPW_FIREBASE_PROJECT_ID")))
        buildConfigField("String", "FIREBASE_API_KEY", quoted(local("OPPW_FIREBASE_API_KEY")))
        buildConfigField("String", "FIREBASE_SENDER_ID", quoted(local("OPPW_FIREBASE_SENDER_ID")))
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}")
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.fragment:fragment-ktx:1.8.9")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-process:2.10.0")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    implementation("androidx.paging:paging-runtime:3.5.0")
    implementation("androidx.paging:paging-compose:3.5.0")
    implementation("androidx.work:work-runtime-ktx:2.11.2")

    implementation(platform("com.google.firebase:firebase-bom:34.16.0"))
    implementation("com.google.firebase:firebase-messaging")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
}

