from __future__ import annotations

from functools import lru_cache
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request, status
from .settings import get_settings


def _bearer_token(request: Request) -> str:
    auth = request.headers.get('Authorization', '')
    if not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing bearer token')
    return auth.split(' ', 1)[1].strip()


@lru_cache(maxsize=4)
def _jwks_client(supabase_url: str) -> PyJWKClient:
    return PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def _decode_supabase_token(token: str, supabase_url: str, legacy_secret: str) -> dict:
    algorithm = str(jwt.get_unverified_header(token).get('alg') or '')
    decode_kwargs = {
        'algorithms': [algorithm],
        'audience': 'authenticated',
        'options': {'require': ['exp', 'sub']},
    }
    if supabase_url:
        decode_kwargs['issuer'] = f"{supabase_url.rstrip('/')}/auth/v1"
    if algorithm == 'HS256':
        if not legacy_secret:
            raise jwt.InvalidTokenError('Legacy JWT secret is not configured')
        return jwt.decode(token, legacy_secret, **decode_kwargs)
    if algorithm in {'RS256', 'ES256'} and supabase_url:
        signing_key = _jwks_client(supabase_url).get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, **decode_kwargs)
    raise jwt.InvalidAlgorithmError('Unsupported Supabase token algorithm')


def get_current_user(request: Request) -> dict:
    settings = get_settings()
    token = _bearer_token(request)

    if settings.allow_demo_auth and token == 'demo':
        return {'sub': 'demo-user', 'email': 'demo@example.com', 'demo': True}

    if not settings.supabase_url and not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail='Supabase authentication is not configured')

    try:
        payload = _decode_supabase_token(token, settings.supabase_url, settings.supabase_jwt_secret)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc

    return {'sub': payload.get('sub'), 'email': payload.get('email'), 'raw': payload}


def require_active_subscription(user: dict = Depends(get_current_user)) -> dict:
    from .db import fetch_one

    if user.get('demo'):
        return user
    row = fetch_one(
        """
        SELECT status FROM subscriptions
        WHERE user_id = :user_id
        ORDER BY updated_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        {'user_id': user['sub']},
    )
    if not row or row['status'] not in ('active', 'trialing'):
        raise HTTPException(status_code=402, detail='Active subscription required')
    return user
