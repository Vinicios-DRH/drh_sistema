# src/api_taf.py
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import jwt

from src import database as db
from src.models import User
from src.authz_api import user_has_perm
from src import bcrypt  # <<< IMPORTANTE: usar o mesmo bcrypt do sistema

bp_api_taf = Blueprint("api_taf", __name__, url_prefix="/api/taf")

JWT_EXP_MINUTES = 60 * 12
JWT_ISSUER = "cbmam-drh"

ATIV_PERMS = {
    "corrida": "APP_TAF_CORRIDA",
    "flexao": "APP_TAF_FLEXAO",
    "abdominal": "APP_TAF_ABDOMINAL",
    "barra_dinamica": "APP_TAF_BARRA_DINAMICA",
    "natacao": "APP_TAF_NATACAO",
}


def _cpf_norm(txt: str) -> str:
    return "".join([c for c in (txt or "") if c.isdigit()])


@bp_api_taf.post("/login")
def login():
    data = request.get_json(silent=True) or {}

    cpf = _cpf_norm(data.get("cpf") or data.get("login") or "")
    senha = (data.get("senha") or "").strip()

    if not cpf or not senha:
        return jsonify({"ok": False, "error": "CPF e senha são obrigatórios."}), 400

    # Busca pelo cpf_norm (11 dígitos)
    user = db.session.query(User).filter(User.cpf_norm == cpf).first()
    if user is None:
        return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

    # Valida senha com o MESMO bcrypt do teu sistema
    try:
        ok = bcrypt.check_password_hash(user.senha, senha)
    except Exception:
        ok = False

    if not ok:
        return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

    # Permissão guarda-chuva
    if not user_has_perm(user.id, "APP_TAF_LOGIN"):
        return jsonify({"ok": False, "error": "Usuário sem permissão para o App TAF."}), 403

    # Atividades liberadas (opcional)
    allowed = []
    for ativ_id, perm in ATIV_PERMS.items():
        if user_has_perm(user.id, perm):
            allowed.append(ativ_id)

    # JWT secret vindo do ENV / config
    secret = current_app.config.get(
        "JWT_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        return jsonify({"ok": False, "error": "JWT_SECRET não configurado no servidor."}), 500

    payload = {
        "sub": str(user.id),
        "name": user.nome,
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
        "iss": JWT_ISSUER,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    return jsonify({
        "ok": True,
        "token": token,
        "user": {"id": user.id, "nome": user.nome, "cpf": user.cpf},
        "allowed_activities": allowed,
    }), 200
