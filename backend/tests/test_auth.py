import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.services.auth import (
    create_access_token,
    get_current_email,
    hash_password,
    verify_password,
)


class AuthServiceTests(unittest.TestCase):
    def test_password_hash_verifies_only_matching_password(self):
        password_hash = hash_password("correct horse battery staple")

        self.assertTrue(
            verify_password("correct horse battery staple", password_hash)
        )
        self.assertFalse(verify_password("incorrect password", password_hash))

    @patch.dict(
        os.environ,
        {"JWT_SECRET": "test-secret-with-more-than-thirty-two-characters"},
    )
    def test_jwt_resolves_email_from_bearer_token(self):
        token = create_access_token("person@example.com")
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        )

        self.assertEqual(get_current_email(credentials), "person@example.com")

    def test_jwt_rejects_missing_bearer_token(self):
        with self.assertRaises(HTTPException) as error:
            get_current_email(None)

        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
