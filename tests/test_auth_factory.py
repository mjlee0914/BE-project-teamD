import unittest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.service import AuthService
from auth.domain.service import TokenProvider
from auth.infrastructure.factory import create_auth_service
from users.domain.service import PasswordHasher


class AuthFactoryTests(unittest.TestCase):
    def test_factory_requires_explicit_password_implementation(self):
        with self.assertRaises(TypeError):
            create_auth_service(AsyncMock(spec=AsyncSession), Mock(spec=TokenProvider))

    def test_factory_builds_service_without_opening_session_or_committing(self):
        session = AsyncMock(spec=AsyncSession)
        hasher = Mock(spec=PasswordHasher)
        service = create_auth_service(
            session, Mock(spec=TokenProvider), password_hasher=hasher
        )
        self.assertIsInstance(service, AuthService)
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()
        hasher.hash.assert_not_called()
