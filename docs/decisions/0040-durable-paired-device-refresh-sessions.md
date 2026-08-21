# ADR 0040: Durable paired-device refresh sessions

- Status: Accepted
- Date: 2026-08-21
- Extends: ADR 0003, ADR 0004, ADR 0018, and ADR 0023

## Context

The Mobile backend issued a new refresh token every time it issued a 15-minute access token. The database committed the new refresh-token hash before Android could durably store the response. If the response was lost, the process stopped, or the phone was suspended in that interval, the server retained only the successor hash while the phone retained only the rejected predecessor token. The next refresh returned `401` and Android correctly cleared a credential that the server could no longer authenticate, forcing a new pairing long before the intended 90-day inactivity expiry.

A short predecessor-token grace period does not make this protocol durable. The backend stores only token hashes and therefore cannot replay the already-issued successor secret, while a retry may occur long after a bounded grace period. Rotation would require a larger refresh-token-family and idempotent-response design to avoid the same ambiguity.

## Decision

One random refresh credential is stable for the lifetime of a paired-device session and remains stored only as an HMAC hash in MySQL and as Android-Keystore-encrypted application data on the device. A successful call to `auth/refresh.php` locks and validates the enabled device and its unexpired refresh credential, extends the configured inactivity expiry, updates `last_seen_at`, and issues a new short-lived access token. It returns the same refresh credential supplied by the device.

Ordinary refresh does not revoke other unexpired access tokens for that device. They retain their bounded lifetime so concurrent or interrupted requests cannot invalidate one another. Explicit mobile unpairing and administrator revocation still disable the device, destroy its refresh-token hash, expire the refresh session, and revoke every outstanding access token. The default access-token lifetime remains 15 minutes and the sliding refresh inactivity lifetime remains 90 days.

The JSON session shape and Android model do not change. Existing paired devices and existing Android builds adopt the behavior on their next successful refresh without a database migration or another pairing.

## Consequences

- Losing a successful refresh response is harmless: the same device credential can retry and receive another access token.
- Concurrent refreshes are serialized by the device-row lock and may each produce a valid, short-lived access token without locking out the device.
- A stolen refresh credential remains usable until inactivity expiry or explicit device revocation. The previous rotation protocol did not implement token-family reuse detection and allowed the same stolen credential to rotate first and lock out the legitimate device, so rotation did not provide a reliable compromise boundary.
- The executable PHP/MySQL contract must cover a discarded refresh response, repeated refresh, unchanged refresh-token identity, sliding expiry, still-valid access tokens, invalid/expired/revoked credentials, and explicit unpairing.
