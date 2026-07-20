package com.oppw.monitor.auth

data class AuthSession(
    val accessToken: String,
    val accessTokenExpiresAt: String,
    val refreshToken: String,
    val refreshTokenExpiresAt: String,
    val deviceId: String,
    val deviceName: String,
    val allowedAccountKeys: List<String>,
)

class AuthenticationRequiredException(message: String = "Device pairing is required") : Exception(message)

class ApiException(val statusCode: Int, message: String) : Exception(message)
