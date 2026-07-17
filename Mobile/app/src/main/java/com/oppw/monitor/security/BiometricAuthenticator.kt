package com.oppw.monitor.security

import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

object BiometricAuthenticator {
    fun availability(activity: FragmentActivity): Int = BiometricManager.from(activity).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)

    fun authenticate(activity: FragmentActivity, accountName: String, onSuccess: () -> Unit, onError: (String) -> Unit) {
        if (availability(activity) != BiometricManager.BIOMETRIC_SUCCESS) {
            onError("Strong biometric authentication is unavailable or no fingerprint is enrolled.")
            return
        }
        val prompt = BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onSuccess()
            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) = onError(errString.toString())
        })
        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Unlock $accountName")
                .setSubtitle("Fingerprint required for Real-account data")
                .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                .setNegativeButtonText("Cancel")
                .build()
        )
    }
}
