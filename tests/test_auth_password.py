import unittest
from unittest.mock import patch

from auth.infrastructure.password_hasher import BcryptPasswordHasher
from users.domain.exceptions import InvalidPassword
from users.domain.user import User


class PasswordInputTests(unittest.TestCase):
    def test_missing_backend_is_not_silently_treated_as_success(self):
        with (
            patch.dict("sys.modules", {"bcrypt": None}),
            self.assertRaises(RuntimeError),
        ):
            BcryptPasswordHasher().hash("Password1!")

    def test_invalid_work_factors_are_rejected(self):
        for rounds in (0, 3, 32, True, 12.5):
            with self.subTest(rounds=rounds), self.assertRaises(ValueError):
                BcryptPasswordHasher(rounds)

    def test_invalid_or_oversized_passwords_are_not_silently_truncated(self):
        hasher = BcryptPasswordHasher()
        for password in (None, "", "a" * 73, "가" * 25, "\ud800"):
            with (
                self.subTest(kind=type(password).__name__),
                self.assertRaises(InvalidPassword),
            ):
                hasher.hash(password)
            self.assertFalse(hasher.verify(password, "not-a-hash"))

    def test_malformed_hashes_fail_closed(self):
        hasher = BcryptPasswordHasher()
        for hashed in (None, "", "plaintext", "가" * 60, "$2b$99$" + "a" * 53):
            with self.subTest(kind=type(hashed).__name__):
                self.assertFalse(hasher.verify("Password1!", hashed))


class RealBcryptTests(unittest.TestCase):
    def setUp(self):
        # 테스트만 낮은 비용을 사용한다. 실제 기본값은 12다.
        self.hasher = BcryptPasswordHasher(rounds=4)

    def test_hash_and_verify_with_random_salt(self):
        first = self.hasher.hash("Password1!")
        second = self.hasher.hash("Password1!")
        self.assertNotEqual(first, second)
        self.assertNotIn("Password1!", first)
        self.assertTrue(self.hasher.verify("Password1!", first))
        self.assertFalse(self.hasher.verify("WrongPassword1!", first))

    def test_default_work_factor_is_12(self):
        hashed = BcryptPasswordHasher().hash("Password1!")
        self.assertTrue(hashed.startswith("$2b$12$"))

    def test_password_is_not_normalized(self):
        hashed = self.hasher.hash(" Password1! ")
        self.assertTrue(self.hasher.verify(" Password1! ", hashed))
        self.assertFalse(self.hasher.verify("Password1!", hashed))

    def test_exact_72_byte_boundary_is_supported(self):
        password = "a" * 72
        hashed = self.hasher.hash(password)
        self.assertTrue(self.hasher.verify(password, hashed))
        self.assertFalse(self.hasher.verify(password + "x", hashed))

    def test_existing_users_factory_and_password_change_use_same_hasher(self):
        user = User.create("user@example.com", "Test User", "Password1!", self.hasher)
        self.assertTrue(self.hasher.verify("Password1!", user.password_hash))
        user.change_password("Password1!", "NewPassword2!", self.hasher)
        self.assertTrue(self.hasher.verify("NewPassword2!", user.password_hash))
        self.assertFalse(self.hasher.verify("Password1!", user.password_hash))
