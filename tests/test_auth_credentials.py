import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from auth.application.service import AuthService
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import TokenProvider, UserStatusChecker
from auth.infrastructure.credentials_verifier import RepositoryUserCredentialVerifier
from shared.core.exceptions import UnauthorizedException
from users.domain.enums import UserStatus
from users.domain.exceptions import InactiveUser
from users.domain.repository import UserRepository
from users.domain.service import PasswordHasher
from users.domain.user import User


class CredentialVerifierTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = User(
            id=10,
            email="user@example.com",
            name="Test User",
            password_hash="stored-test-hash",
        )
        self.users = AsyncMock(spec=UserRepository)
        self.users.find_by_email.return_value = self.user
        self.hasher = Mock(spec=PasswordHasher)
        self.hasher.verify.return_value = True
        self.verifier = RepositoryUserCredentialVerifier(self.users, self.hasher)

    async def test_active_user_returns_persisted_id(self):
        result = await self.verifier.verify_credentials(
            "user@example.com", "PlainPassword1!"
        )
        self.assertEqual(result, 10)
        self.hasher.verify.assert_called_once_with(
            "PlainPassword1!", "stored-test-hash"
        )
        self.hasher.hash.assert_not_called()
        self.users.save.assert_not_awaited()

    async def test_email_is_normalized_but_password_is_not(self):
        await self.verifier.verify_credentials(
            " USER@Example.com ", " password with spaces "
        )
        self.users.find_by_email.assert_awaited_once_with("user@example.com")
        self.hasher.verify.assert_called_once_with(
            " password with spaces ", "stored-test-hash"
        )

    async def test_unknown_user_returns_none(self):
        self.users.find_by_email.return_value = None
        self.assertIsNone(
            await self.verifier.verify_credentials("missing@example.com", "wrong")
        )
        self.hasher.verify.assert_not_called()

    async def test_wrong_password_returns_none(self):
        self.hasher.verify.return_value = False
        self.assertIsNone(
            await self.verifier.verify_credentials("user@example.com", "wrong")
        )

    async def test_withdrawn_user_is_rejected_after_password_check(self):
        self.user.status = UserStatus.WITHDRAWN
        with self.assertRaises(InactiveUser) as caught:
            await self.verifier.verify_credentials("user@example.com", "correct")
        self.assertEqual(caught.exception.status_code, 403)

    async def test_wrong_password_does_not_disclose_withdrawn_status(self):
        self.user.status = UserStatus.WITHDRAWN
        self.hasher.verify.return_value = False
        self.assertIsNone(
            await self.verifier.verify_credentials("user@example.com", "wrong")
        )

    async def test_deleted_timestamp_also_prevents_login(self):
        self.user.deleted_at = datetime.now(UTC)
        with self.assertRaises(InactiveUser):
            await self.verifier.verify_credentials("user@example.com", "correct")

    async def test_invalid_or_unsaved_user_id_does_not_issue_token(self):
        for user_id in (None, 0, True, 2**63):
            with self.subTest(user_id=user_id):
                self.user.id = user_id
                self.assertIsNone(
                    await self.verifier.verify_credentials(
                        "user@example.com", "correct"
                    )
                )

    async def test_database_error_is_not_hidden_as_wrong_password(self):
        self.users.find_by_email.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            await self.verifier.verify_credentials("user@example.com", "correct")

    async def test_password_backend_error_is_not_swallowed(self):
        self.hasher.verify.side_effect = RuntimeError("password backend failure")
        with self.assertRaises(RuntimeError):
            await self.verifier.verify_credentials("user@example.com", "correct")

    async def test_auth_service_issues_token_only_after_success(self):
        provider = Mock(spec=TokenProvider)
        provider.create_access_token.return_value = ("test-token", "test-jti", 3600)
        service = AuthService(
            self.verifier,
            AsyncMock(spec=TokenBlacklistRepository),
            provider,
            AsyncMock(spec=UserStatusChecker),
        )
        self.assertEqual(
            await service.login("user@example.com", "correct"),
            ("test-token", "bearer", 3600),
        )
        provider.create_access_token.assert_called_once_with(10)
        provider.reset_mock()
        self.hasher.verify.return_value = False
        with self.assertRaises(UnauthorizedException):
            await service.login("user@example.com", "wrong")
        provider.create_access_token.assert_not_called()
