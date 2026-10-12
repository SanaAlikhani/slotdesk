from functools import wraps

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .db import get_db

TOKEN_MAX_AGE = 60 * 60 * 8  # 8 hours


def error(message: str, status: int):
    return jsonify({"error": message}), status


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="slotdesk-auth")


def make_token(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id})


def login_required(admin: bool = False):
    """Decorator: require a valid bearer token, optionally an admin role."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return error("Log in to continue.", 401)
            try:
                data = _serializer().loads(header[7:], max_age=TOKEN_MAX_AGE)
            except SignatureExpired:
                return error("Your session expired. Log in again.", 401)
            except BadSignature:
                return error("Invalid session. Log in again.", 401)

            user = get_db().execute(
                "SELECT id, email, name, role FROM users WHERE id = ?", (data["uid"],)
            ).fetchone()
            if user is None:
                return error("Account not found.", 401)
            if admin and user["role"] != "admin":
                return error("Only office staff can do this.", 403)
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator
