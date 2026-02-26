# src/api_taf.py (ou src/auth_jwt.py)
from functools import wraps
from flask import request, jsonify, current_app
import jwt


def require_taf_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return jsonify({"ok": False, "error": "Token ausente."}), 401

        token = auth.split(" ", 1)[1].strip()
        secret = current_app.config.get(
            "JWT_SECRET") or current_app.config.get("SECRET_KEY")
        if not secret:
            return jsonify({"ok": False, "error": "JWT_SECRET não configurado."}), 500

        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except Exception:
            return jsonify({"ok": False, "error": "Token inválido/expirado."}), 401

        # disponibiliza o user_id para o endpoint
        request.taf_user_id = int(payload.get("sub"))
        return fn(*args, **kwargs)
    return wrapper
