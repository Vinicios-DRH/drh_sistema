# src/api_taf.py
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta
import jwt

from src import database as db
from src.models import User
from src.authz_api import user_has_perm

bp_api_taf = Blueprint("api_taf", __name__, url_prefix="/api/taf")

JWT_SECRET = "COLOQUE_NO_ENV"          # pega de env
JWT_EXP_MINUTES = 60 * 12              # 12h (ajusta)
JWT_ISSUER = "cbmam-drh"

ATIV_PERMS = {
    "corrida": "APP_TAF_CORRIDA",
    "flexao": "APP_TAF_FLEXAO",
    "abdominal": "APP_TAF_ABDOMINAL",
    "barra_dinamica": "APP_TAF_BARRA_DINAMICA",
    "natacao": "APP_TAF_NATACAO",
}

def verify_password(stored: str, provided: str) -> bool:
        if not stored:
            return False

        # 1) tenta werkzeug
        try:
            return check_password_hash(stored, provided)
        except ValueError:
            # 2) fallback: texto puro (MVP)
            return stored == provided

@bp_api_taf.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    login_txt = (data.get("login") or "").strip()  # cpf ou email
    senha = (data.get("senha") or "").strip()

    if not login_txt or not senha:
        return jsonify({"ok": False, "error": "Informe login e senha."}), 400

    # tenta achar por cpf_norm (só números) ou email
    cpf_norm = "".join([c for c in login_txt if c.isdigit()])
    q = db.session.query(User)

    user = None
    if cpf_norm:
        user = q.filter(User.cpf_norm == cpf_norm).first()
    if user is None:
        user = q.filter(User.email.ilike(login_txt)).first()

    if user is None:
        return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

    # valida senha hash (ajusta pro teu padrão real)

    if not verify_password(user.senha, senha):
        return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

    # precisa permissão guarda-chuva
    if not user_has_perm(user.id, "APP_TAF_LOGIN"):
        return jsonify({"ok": False, "error": "Usuário sem permissão para o App TAF."}), 403

    # atividades liberadas (se você quiser travar por atividade)
    allowed = []
    for ativ_id, perm in ATIV_PERMS.items():
        if user_has_perm(user.id, perm):
            allowed.append(ativ_id)

    payload = {
        "sub": str(user.id),
        "name": user.nome,
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
        "iss": JWT_ISSUER,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return jsonify({
        "ok": True,
        "token": token,
        "user": {"id": user.id, "nome": user.nome},
        "allowed_activities": allowed,  # pode vir vazio se você não usar por-atividade
    })
