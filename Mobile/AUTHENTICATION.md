# Authentication design

## Pairing

1. The server administrator creates a one-use pairing code assigned to one or more accounts.
2. The Android app sends the code and a device name to `auth/pair.php` over HTTPS.
3. The server consumes the code and creates a device record.
4. The server returns:
   - a 15-minute opaque access token;
   - a 90-day opaque refresh token;
   - the device ID;
   - the accounts authorized for the device.
5. Android encrypts the complete session with AES-GCM. The AES key is generated and retained by Android Keystore.

## Normal reads

The app sends:

```http
Authorization: Bearer ACCESS_TOKEN
```

`accounts.php` returns only accounts assigned to that device. `status.php` additionally checks that the requested account is assigned to the device.

## Refresh rotation

Before access-token expiry, or after one HTTP 401 response, the app calls `auth/refresh.php`. The server:

1. locks the device record;
2. verifies the stored HMAC of the refresh token;
3. replaces the refresh token;
4. revokes existing access tokens for the device;
5. issues a new access token;
6. returns the complete replacement session.

The failed API call is retried once. There is no infinite retry loop.

## Revocation

The phone can call `auth/unpair.php`, or an administrator can run:

```bash
php admin/revoke_device.php --device=DEVICE_ID
```

Revocation disables refresh and invalidates all active access tokens.

## Token storage

Only token HMACs are stored in MySQL. Raw refresh and access tokens are returned to the phone and are never logged by the backend.

## Android account access

After device pairing, both Real and Demo accounts are accessed using the same short-lived access-token and rotating refresh-token flow. There is no local biometric requirement. Account authorization remains enforced by the backend for every request.

