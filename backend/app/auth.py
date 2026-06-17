from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from .settings import get_settings
from .db import fetch_one


def _bearer_token(request: Request) -> str:
    auth = request.headers.get('Authorization', '')
    if not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing bearer token')
    return auth.split(' ', 1)[1].strip()


def get_current_user(request: Request) -> dict:
    settings = get_settings()
    token = _bearer_token(request)

    if settings.allow_demo_auth and token == 'demo':
        return {'sub': 'demo-user', 'email': 'demo@example.com', 'demo': True}

    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail='SUPABASE_JWT_SECRET not configured')

    try:
        payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=['HS256'], audience='authenticated')
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc

    return {'sub': payload.get('sub'), 'email': payload.get('email'), 'raw': payload}


def require_active_subscription(user: dict = Depends(get_current_user)) -> dict:
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
