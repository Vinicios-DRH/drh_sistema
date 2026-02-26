# src/api_taf.py
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import jwt
from sqlalchemy import or_, and_
from src import database as db
from src.models import TafAvaliacao, User, Militar, PostoGrad, Quadro, Obm, MilitarObmFuncao
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
    "barra_estatica": "APP_TAF_BARRA_ESTATICA",
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


@bp_api_taf.post("/avaliacoes")
@require_taf_auth
def criar_avaliacao():
    data = request.get_json(silent=True) or {}

    user_id = int(getattr(request, "taf_user_id", 0) or 0)
    if not user_id:
        return jsonify({"ok": False, "error": "Token inválido."}), 401

    # permissão guarda-chuva
    if not user_has_perm(user_id, "APP_TAF_LOGIN"):
        return jsonify({"ok": False, "error": "Sem permissão para o App TAF."}), 403

    militar_id = int(data.get("militar_id") or 0)
    atividade = (data.get("atividade") or "").strip().lower()
    idade = data.get("idade")
    valor = data.get("valor")

    avaliador_label = (data.get("avaliador_label") or "").strip()
    substituto_nome = (data.get("substituto_nome") or "").strip()
    observacoes = (data.get("observacoes") or "").strip()

    # campos calculados (por enquanto vem do app)
    resultado_ok = bool(data.get("resultado_ok"))
    referencia = (data.get("referencia") or None)
    score_linha = (data.get("score_linha") or None)

    if not militar_id or not atividade or idade is None or valor is None:
        return jsonify({"ok": False, "error": "Campos obrigatórios: militar_id, atividade, idade, valor."}), 400

    if atividade not in ATIV_PERMS:
        return jsonify({"ok": False, "error": "Atividade inválida."}), 400

    # permissão por atividade (opcional mas recomendado)
    perm_ativ = ATIV_PERMS.get(atividade)
    if perm_ativ and not user_has_perm(user_id, perm_ativ):
        return jsonify({"ok": False, "error": "Sem permissão para essa atividade."}), 403

    # valida militar existe e está ativo
    m = db.session.query(Militar.id).filter(
        Militar.id == militar_id, Militar.inativo.is_(False)).scalar()
    if not m:
        return jsonify({"ok": False, "error": "Militar não encontrado/inativo."}), 404

    # valida tipos
    try:
        idade = int(idade)
        valor = float(str(valor).replace(",", "."))
    except Exception:
        return jsonify({"ok": False, "error": "Idade/valor inválidos."}), 400

    row = TafAvaliacao(
        militar_id=militar_id,
        avaliador_user_id=user_id,
        atividade=atividade,
        idade=idade,
        valor=valor,
        avaliador_label=avaliador_label or None,
        substituto_nome=substituto_nome or None,
        observacoes=observacoes or None,
        resultado_ok=resultado_ok,
        referencia=str(referencia) if referencia is not None else None,
        score_linha=str(score_linha) if score_linha is not None else None,
    )

    db.session.add(row)
    db.session.commit()

    return jsonify({"ok": True, "id": row.id}), 201


@bp_api_taf.get("/avaliacoes")
@require_taf_auth
def listar_avaliacoes():
    user_id = int(getattr(request, "taf_user_id", 0) or 0)
    if not user_id:
        return jsonify({"ok": False, "error": "Token inválido."}), 401

    if not user_has_perm(user_id, "APP_TAF_LOGIN"):
        return jsonify({"ok": False, "error": "Sem permissão para o App TAF."}), 403

    data_str = (request.args.get("data") or "").strip()  # YYYY-MM-DD
    atividade = (request.args.get("atividade") or "").strip().lower()
    militar_id = request.args.get("militar_id")

    q = db.session.query(TafAvaliacao)

    if data_str:
        try:
            d0 = datetime.strptime(data_str, "%Y-%m-%d")
            d1 = d0 + timedelta(days=1)
            q = q.filter(TafAvaliacao.criado_em >= d0,
                         TafAvaliacao.criado_em < d1)
        except Exception:
            return jsonify({"ok": False, "error": "Parâmetro data inválido. Use YYYY-MM-DD."}), 400

    if atividade:
        q = q.filter(TafAvaliacao.atividade == atividade)

    if militar_id:
        try:
            mid = int(militar_id)
            q = q.filter(TafAvaliacao.militar_id == mid)
        except Exception:
            return jsonify({"ok": False, "error": "militar_id inválido."}), 400

    q = q.order_by(TafAvaliacao.criado_em.desc()).limit(200)

    items = []
    for r in q.all():
        items.append({
            "id": r.id,
            "militar_id": r.militar_id,
            "avaliador_user_id": r.avaliador_user_id,
            "atividade": r.atividade,
            "idade": r.idade,
            "valor": float(r.valor),
            "resultado_ok": bool(r.resultado_ok),
            "referencia": r.referencia,
            "score_linha": r.score_linha,
            "avaliador_label": r.avaliador_label,
            "substituto_nome": r.substituto_nome,
            "observacoes": r.observacoes,
            "criado_em": r.criado_em.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return jsonify({"ok": True, "items": items}), 200
