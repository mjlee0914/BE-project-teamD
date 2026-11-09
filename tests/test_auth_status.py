import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from auth.application.service import AuthService
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import UserCredentialVerifier
from auth.infrastructure.security import JwtTokenProvider
from auth.infrastructure.user_status_checker import RepositoryUserStatusChecker
from shared.core.exceptions import UnauthorizedException
from users.domain.enums import UserStatus
from users.domain.exceptions import InactiveUser
from users.domain.repository import UserRepository
from users.domain.user import User


class AuthCurrentStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = User(
            id=10,
            email="test@example.com",
            name="Test User",
            password_hash="test-only-hash",
        )
        self.users = AsyncMock(spec=UserRepository)
        self.users.find_by_id.return_value = self.user
        self.checker = RepositoryUserStatusChecker(self.users)
        self.credentials = AsyncMock(spec=UserCredentialVerifier)
        self.credentials.verify_credentials.return_value = 10
        self.blacklist = AsyncMock(spec=TokenBlacklistRepository)
        self.blacklist.is_blacklisted.return_value = False
        self.provider = JwtTokenProvider("test-only-status-key-" * 4)
        self.service = AuthService(
            self.credentials, self.blacklist, self.provider, self.checker
        )
        self.token = (await self.service.login("test@example.com", "test-password"))[0]

    async def test_active_user_is_loaded_by_token_subject(self):
        payload = await self.service.authenticate_token(self.token)
        self.assertEqual(payload.user_id, 10)
        self.users.find_by_id.assert_awaited_once_with(10)
        self.users.save.assert_not_awaited()

    async def test_withdrawal_after_issue_blocks_existing_token(self):
        await self.service.authenticate_token(self.token)
        self.user.status = UserStatus.WITHDRAWN
        with self.assertRaises(InactiveUser) as caught:
            await self.service.authenticate_token(self.token)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(self.users.find_by_id.await_count, 2)

    async def test_missing_user_blocks_existing_token(self):
        self.users.find_by_id.return_value = None
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token(self.token)

    async def test_deleted_timestamp_blocks_even_if_status_is_active(self):
        self.user.deleted_at = datetime.now(UTC)
        with self.assertRaises(InactiveUser):
            await self.service.authenticate_token(self.token)

    async def test_blacklist_rejection_precedes_user_lookup(self):
        self.blacklist.is_blacklisted.return_value = True
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token(self.token)
        self.users.find_by_id.assert_not_awaited()

    async def test_invalid_token_does_not_query_user_or_blacklist(self):
        with self.assertRaises(UnauthorizedException):
            await self.service.authenticate_token("invalid-token")
        self.users.find_by_id.assert_not_awaited()
        self.blacklist.is_blacklisted.assert_not_awaited()

    async def test_database_failure_is_not_ignored(self):
        self.users.find_by_id.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            await self.service.authenticate_token(self.token)

    async def test_withdrawn_user_can_still_revoke_valid_token(self):
        self.user.status = UserStatus.WITHDRAWN
        await self.service.logout(self.token)
        self.blacklist.add.assert_awaited_once()
        self.users.find_by_id.assert_not_awaited()

    async def test_invalid_user_id_is_rejected_without_query(self):
        for user_id in (0, -1, True, 2**63):
            with (
                self.subTest(user_id=user_id),
                self.assertRaises(UnauthorizedException),
            ):
                await self.checker.ensure_active(user_id)
        self.users.find_by_id.assert_not_awaited()
