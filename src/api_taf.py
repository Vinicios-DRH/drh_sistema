# src/api_taf.py
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import jwt
from sqlalchemy import or_, and_
from src import database as db
from src.models import User, Militar, PostoGrad, Quadro, Obm, MilitarObmFuncao
from src.authz_api import user_has_perm
from src import bcrypt  # <<< IMPORTANTE: usar o mesmo bcrypt do sistema
from src.auth_jwt import require_taf_auth
from datetime import date

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


def calc_age(birth_date):
    if not birth_date:
        return None
    today = date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


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


@bp_api_taf.get("/militares")
@require_taf_auth
def buscar_militares():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 20)
    offset = int(request.args.get("offset") or 0)

    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    if len(q) < 2:
        return jsonify({"ok": True, "items": [], "hint": "Digite pelo menos 2 caracteres."}), 200

    like = f"%{q}%"

    # JOINs:
    # - posto/grad
    # - quadro
    # - obm atual via MilitarObmFuncao com data_fim IS NULL
    query = (
        db.session.query(Militar, PostoGrad, Quadro, Obm)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .outerjoin(
            MilitarObmFuncao,
            (MilitarObmFuncao.militar_id == Militar.id) &
            (MilitarObmFuncao.data_fim.is_(None))
        )
        .outerjoin(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .filter(Militar.inativo.is_(False))
        .filter(
            or_(
                Militar.nome_completo.ilike(like),
                Militar.nome_guerra.ilike(like),
                Militar.matricula.ilike(like),
                Militar.cpf.ilike(like),
            )
        )
        .order_by(Militar.nome_completo.asc())
        .limit(limit)
        .offset(offset)
    )

    items = []
    for m, pg, qd, obm in query.all():
        items.append({
            "id": m.id,
            "nome_completo": m.nome_completo,
            "nome_guerra": m.nome_guerra,
            "matricula": m.matricula,
            "cpf": m.cpf,
            "idade": calc_age(m.data_nascimento),
            "posto_grad": (pg.sigla if pg else None),
            "quadro": (qd.quadro if qd else None),
            "obm": (obm.sigla if obm else None),
        })

    return jsonify({"ok": True, "items": items, "limit": limit, "offset": offset}), 200


@bp_api_taf.get("/militares/<int:militar_id>")
@require_taf_auth
def militar_detalhe(militar_id):
    row = (
        db.session.query(Militar, PostoGrad, Quadro, Obm)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .outerjoin(
            MilitarObmFuncao,
            (MilitarObmFuncao.militar_id == Militar.id) &
            (MilitarObmFuncao.data_fim.is_(None))
        )
        .outerjoin(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .filter(Militar.id == militar_id, Militar.inativo.is_(False))
        .first()
    )

    if not row:
        return jsonify({"ok": False, "error": "Militar não encontrado."}), 404

    m, pg, qd, obm = row

    return jsonify({
        "ok": True,
        "militar": {
            "id": m.id,
            "nome_completo": m.nome_completo,
            "nome_guerra": m.nome_guerra,
            "matricula": m.matricula,
            "cpf": m.cpf,
            "idade": calc_age(m.data_nascimento),
            "posto_grad": (pg.sigla if pg else None),
            "quadro": (qd.quadro if qd else None),
            "obm": (obm.sigla if obm else None),
        }
    }), 200
