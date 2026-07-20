package com.oppw.monitor.auth

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureSessionStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    fun save(session: AuthSession) = synchronized(STORE_LOCK) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val plaintext = session.toJson().toString().toByteArray(Charsets.UTF_8)
        val encrypted = cipher.doFinal(plaintext)
        check(preferences.edit()
            .putString(KEY_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString(KEY_PAYLOAD, Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .commit()) { "Could not persist the device session" }
    }

    fun load(): AuthSession? = synchronized(STORE_LOCK) { loadUnlocked() }

    fun clear() = synchronized(STORE_LOCK) { clearUnlocked() }

    fun clearIfAccessToken(accessToken: String): Boolean = synchronized(STORE_LOCK) {
        val current = loadUnlocked() ?: return@synchronized false
        if (current.accessToken != accessToken) return@synchronized false
        clearUnlocked()
        true
    }

    fun clearIfRefreshToken(refreshToken: String): Boolean = synchronized(STORE_LOCK) {
        val current = loadUnlocked() ?: return@synchronized false
        if (current.refreshToken != refreshToken) return@synchronized false
        clearUnlocked()
        true
    }

    private fun loadUnlocked(): AuthSession? {
        val ivEncoded = preferences.getString(KEY_IV, null) ?: return null
        val payloadEncoded = preferences.getString(KEY_PAYLOAD, null) ?: return null
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            val iv = Base64.decode(ivEncoded, Base64.NO_WRAP)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
            val decrypted = cipher.doFinal(Base64.decode(payloadEncoded, Base64.NO_WRAP))
            JSONObject(String(decrypted, Charsets.UTF_8)).toAuthSession()
        }.getOrElse {
            clearUnlocked()
            null
        }
    }

    private fun clearUnlocked() {
        preferences.edit().clear().commit()
    }

    private fun getOrCreateKey(): SecretKey {
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private fun AuthSession.toJson() = JSONObject().apply {
        put("accessToken", accessToken)
        put("accessTokenExpiresAt", accessTokenExpiresAt)
        put("refreshToken", refreshToken)
        put("refreshTokenExpiresAt", refreshTokenExpiresAt)
        put("deviceId", deviceId)
        put("deviceName", deviceName)
        put("allowedAccountKeys", JSONArray(allowedAccountKeys))
    }

    private fun JSONObject.toAuthSession(): AuthSession {
        val accounts = optJSONArray("allowedAccountKeys") ?: JSONArray()
        return AuthSession(
            accessToken = getString("accessToken"),
            accessTokenExpiresAt = getString("accessTokenExpiresAt"),
            refreshToken = getString("refreshToken"),
            refreshTokenExpiresAt = getString("refreshTokenExpiresAt"),
            deviceId = getString("deviceId"),
            deviceName = optString("deviceName", "Android device"),
            allowedAccountKeys = buildList { for (index in 0 until accounts.length()) add(accounts.getString(index)) },
        )
    }

    companion object {
        private val STORE_LOCK = Any()
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "oppw_monitor_session_key_v1"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val PREFERENCES_NAME = "oppw_secure_session"
        private const val KEY_IV = "session_iv"
        private const val KEY_PAYLOAD = "session_payload"
    }
}
