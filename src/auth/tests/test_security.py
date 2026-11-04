import unittest
from datetime import UTC, datetime

import jwt

from auth.domain.entities import UnauthorizedException
from auth.infrastructure.security import JwtTokenProvider


class JwtTokenProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = "test-only-key-0123456789-abcdefghijklmnopqrstuvwxyz-0123456789"
        self.provider = JwtTokenProvider(self.key)

    def payload(self) -> dict:
        now = int(datetime.now(UTC).timestamp())
        return {
            "sub": "1",
            "jti": "test-jti",
            "iat": now,
            "exp": now + 1800,
            "token_type": "access",
        }

    def test_round_trip_and_lifetimes(self) -> None:
        for kind, lifetime in [("access", 1800), ("refresh", 604800)]:
            with self.subTest(kind=kind):
                token = getattr(self.provider, f"create_{kind}_token")(1)
                claims = self.provider.decode_token(token, expected_type=kind)
                self.assertEqual(claims.user_id, 1)
                self.assertEqual(claims.token_type, kind)
                payload = jwt.decode(token, self.key, algorithms=["HS256"])
                self.assertEqual(payload["exp"] - payload["iat"], lifetime)
                self.assertEqual(int(claims.exp.timestamp()), payload["exp"])
                self.assertIsNotNone(claims.exp.utcoffset())

    def test_every_issued_token_has_a_distinct_jti(self) -> None:
        tokens = [self.provider.create_access_token(1) for _ in range(3)]
        tokens.append(self.provider.create_refresh_token(1))
        jtis = {
            jwt.decode(token, self.key, algorithms=["HS256"])["jti"] for token in tokens
        }
        self.assertEqual(len(jtis), 4)

    def test_access_and_refresh_are_not_interchangeable(self) -> None:
        with self.assertRaises(UnauthorizedException):
            self.provider.decode_token(self.provider.create_refresh_token(1))
        with self.assertRaises(UnauthorizedException):
            self.provider.decode_token(
                self.provider.create_access_token(1), expected_type="refresh"
            )

    def test_wrong_signature_is_rejected(self) -> None:
        token = JwtTokenProvider(
            "different-test-only-key-0123456789"
        ).create_access_token(1)
        with self.assertRaises(UnauthorizedException):
            self.provider.decode_token(token)

    def test_expired_token_is_rejected(self) -> None:
        payload = self.payload()
        payload["iat"] -= 60
        payload["exp"] = payload["iat"] + 1
        token = jwt.encode(payload, self.key, algorithm="HS256")
        with self.assertRaises(UnauthorizedException):
            self.provider.decode_token(token)

    def test_each_missing_required_claim_is_rejected(self) -> None:
        for name in self.payload():
            with self.subTest(name=name):
                payload = self.payload()
                del payload[name]
                token = jwt.encode(payload, self.key, algorithm="HS256")
                with self.assertRaises(UnauthorizedException):
                    self.provider.decode_token(token)

    def test_invalid_claim_values_are_rejected(self) -> None:
        for name, value in [
            ("sub", "0"),
            ("sub", "abc"),
            ("sub", "01"),
            ("jti", " "),
            ("token_type", "unknown"),
            ("exp", True),
            ("exp", 10**30),
        ]:
            with self.subTest(name=name, value=value):
                payload = self.payload()
                payload[name] = value
                token = jwt.encode(payload, self.key, algorithm="HS256")
                with self.assertRaises(UnauthorizedException):
                    self.provider.decode_token(token)

    def test_malformed_token_is_rejected(self) -> None:
        with self.assertRaises(UnauthorizedException):
            self.provider.decode_token("not-a-jwt")

    def test_unapproved_algorithm_is_rejected(self) -> None:
        token = jwt.encode(self.payload(), self.key, algorithm="HS384")
        with self.assertRaises(UnauthorizedException):
            self.provider.decode_token(token)

    def test_invalid_user_id_or_short_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            JwtTokenProvider("short-key")
        for user_id in (0, -1, True, "1"):
            with self.subTest(user_id=user_id), self.assertRaises(ValueError):
                self.provider.create_access_token(user_id)
