import time
import unittest

import jwt

from .auth import _decode_supabase_token


class SupabaseTokenTests(unittest.TestCase):
    def test_legacy_token_requires_valid_audience_issuer_and_expiry(self):
        secret = 'test-secret-with-enough-entropy-for-hs256'
        url = 'https://example.supabase.co'
        payload = {
            'sub': '00000000-0000-0000-0000-000000000001',
            'aud': 'authenticated',
            'iss': f'{url}/auth/v1',
            'exp': int(time.time()) + 60,
        }
        token = jwt.encode(payload, secret, algorithm='HS256')
        self.assertEqual(_decode_supabase_token(token, url, secret)['sub'], payload['sub'])

    def test_rejects_unapproved_algorithm(self):
        token = jwt.encode({'sub': 'x'}, '', algorithm='none')
        with self.assertRaises(jwt.InvalidAlgorithmError):
            _decode_supabase_token(token, 'https://example.supabase.co', 'secret')


if __name__ == '__main__':
    unittest.main()
