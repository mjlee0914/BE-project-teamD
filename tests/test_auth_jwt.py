import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import jwt

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import UserCredentialVerifier, UserStatusChecker
from auth.infrastructure.security import JwtTokenProvider
from shared.core.exceptions import UnauthorizedException

KEY = "test-only-signing-key-" * 4


class JwtTokenProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = JwtTokenProvider(KEY)
        now = int(datetime.now(UTC).timestamp())
        self.claims = {
            "sub": "10",
            "jti": "test-jti",
            "iat": now,
            "exp": now + 3600,
            "iss": "be-project-teamd",
            "aud": "be-project-teamd-api",
            "token_use": "access",
        }

    def sign(self, claims=None, *, key=KEY, algorithm="HS512"):
        return jwt.encode(
            self.claims if claims is None else claims, key, algorithm=algorithm
        )

    def assert_rejected(self, token):
        with self.assertRaises(UnauthorizedException) as caught:
            self.provider.decode_token(token)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.message, "유효하지 않거나 만료된 토큰입니다.")
        self.assertNotIn(KEY, str(caught.exception))

    def test_issue_and_decode_preserve_existing_contract(self):
        token, jti, lifetime = self.provider.create_access_token(10)
        self.assertEqual(lifetime, 3600)
        self.assertEqual(self.provider.decode_token(token), TokenPayload(10, jti))
        claims = jwt.decode(
            token,
            KEY,
            algorithms=["HS512"],
            audience="be-project-teamd-api",
            issuer="be-project-teamd",
        )
        self.assertEqual(claims["sub"], "10")
        self.assertEqual(claims["exp"] - claims["iat"], lifetime)
        self.assertEqual(claims["token_use"], "access")

    def test_each_token_has_unique_identifier(self):
        self.assertNotEqual(
            self.provider.create_access_token(10)[1],
            self.provider.create_access_token(10)[1],
        )

    def test_invalid_user_ids_cannot_be_issued(self):
        for user_id in (0, -1, True, 1.5, "10", 2**63):
            with self.subTest(user_id=user_id), self.assertRaises(ValueError):
                self.provider.create_access_token(user_id)

    def test_expired_token_is_rejected(self):
        self.claims.update(iat=self.claims["iat"] - 20, exp=self.claims["iat"] - 1)
        self.assert_rejected(self.sign())

    def test_wrong_signature_is_rejected(self):
        self.assert_rejected(self.sign(key="another-test-only-key-" * 4))

    def test_other_algorithm_and_unsigned_token_are_rejected(self):
        self.assert_rejected(self.sign(algorithm="HS256"))
        self.assert_rejected(self.sign(key=None, algorithm="none"))

    def test_missing_required_claims_are_rejected(self):
        for name in self.claims:
            with self.subTest(name=name):
                claims = self.claims.copy()
                del claims[name]
                self.assert_rejected(self.sign(claims))

    def test_wrong_issuer_audience_and_token_use_are_rejected(self):
        for name, value in (
            ("iss", "another-issuer"),
            ("aud", "another-api"),
            ("aud", ["be-project-teamd-api"]),
            ("token_use", "refresh"),
        ):
            with self.subTest(name=name, value=value):
                self.assert_rejected(self.sign(self.claims | {name: value}))

    def test_invalid_subjects_are_rejected(self):
        for subject in (10, True, "0", "-1", "01", "1.5", "not-an-id", str(2**63)):
            with self.subTest(subject=subject):
                self.assert_rejected(self.sign(self.claims | {"sub": subject}))

    def test_invalid_jti_is_rejected(self):
        for jti in (None, "", "   ", 10):
            with self.subTest(jti=jti):
                self.assert_rejected(self.sign(self.claims | {"jti": jti}))

    def test_numeric_dates_must_be_integer_and_ordered(self):
        for name, value in (
            ("iat", True),
            ("iat", str(self.claims["iat"])),
            ("exp", str(self.claims["exp"])),
            ("exp", self.claims["exp"] + 0.5),
            ("iat", -1),
        ):
            with self.subTest(name=name, value=value):
                self.assert_rejected(self.sign(self.claims | {name: value}))

    def test_future_issued_at_is_rejected(self):
        self.assert_rejected(self.sign(self.claims | {"iat": self.claims["iat"] + 60}))

    def test_malformed_numeric_dates_do_not_escape_as_server_errors(self):
        for name, value in (
            ("iat", {}),
            ("exp", []),
            ("exp", float("inf")),
            ("iat", float("nan")),
        ):
            with self.subTest(name=name, value_type=type(value).__name__):
                self.assert_rejected(self.sign(self.claims | {name: value}))

    def test_malformed_and_oversized_tokens_are_rejected(self):
        for token in ("", "not-a-token", "a.b.c", "a" * 8193, None, b"bytes-token"):
            with self.subTest(token_type=type(token).__name__):
                self.assert_rejected(token)

    def test_configuration_requires_secret_and_positive_lifetime(self):
        for secret in ("", "short", " " * 64, None):
            with (
                self.subTest(secret_type=type(secret).__name__),
                self.assertRaises(ValueError),
            ):
                JwtTokenProvider(secret)
        for lifetime in (0, -1, True, 1.5):
            with self.subTest(lifetime=lifetime), self.assertRaises(ValueError):
                JwtTokenProvider(KEY, expires_in_seconds=lifetime)

    def test_environment_configuration(self):
        with (
            patch("auth.infrastructure.security.load_dotenv"),
            patch.dict(
                "os.environ",
                {
                    "JWT_SECRET_KEY": KEY,
                    "JWT_ACCESS_TOKEN_EXPIRE_SECONDS": "90",
                    "JWT_ISSUER": "test-issuer",
                    "JWT_AUDIENCE": "test-audience",
                },
            ),
        ):
            provider = JwtTokenProvider.from_env()
            token, jti, lifetime = provider.create_access_token(10)
            self.assertEqual(lifetime, 90)
            self.assertEqual(provider.decode_token(token), TokenPayload(10, jti))
        with (
            patch("auth.infrastructure.security.load_dotenv"),
            patch.dict("os.environ", {"JWT_SECRET_KEY": ""}),
            self.assertRaises(ValueError),
        ):
            JwtTokenProvider.from_env()


class AuthServiceWithJwtTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.blacklisted = set()
        self.repo = AsyncMock(spec=TokenBlacklistRepository)
        self.repo.is_blacklisted.side_effect = lambda jti: jti in self.blacklisted

        async def add(jti, user_id):
            self.blacklisted.add(jti)

        self.repo.add.side_effect = add
        self.credentials = AsyncMock(spec=UserCredentialVerifier)
        self.credentials.verify_credentials.return_value = 10
        self.status_checker = AsyncMock(spec=UserStatusChecker)
        self.service = AuthService(
            self.credentials, self.repo, JwtTokenProvider(KEY), self.status_checker
        )

    async def test_login_authenticate_logout_and_duplicate_logout(self):
        token, kind, lifetime = await self.service.login(
            "test@example.com", "test-password"
        )
        self.assertEqual(kind, "bearer")
        self.assertEqual(lifetime, 3600)
        self.assertEqual((await self.service.authenticate_token(token)).user_id, 10)
        await self.service.logout(token)
        await self.service.logout(token)
        self.repo.add.assert_awaited_once()
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token(token)

    async def test_logout_does_not_revoke_other_token(self):
        first = (await self.service.login("test@example.com", "test-password"))[0]
        second = (await self.service.login("test@example.com", "test-password"))[0]
        await self.service.logout(first)
        self.assertEqual((await self.service.authenticate_token(second)).user_id, 10)

    async def test_failed_credentials_do_not_issue_token(self):
        self.credentials.verify_credentials.return_value = None
        with self.assertRaises(UnauthorizedException):
            await self.service.login("test@example.com", "wrong-password")
