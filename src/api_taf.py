# src/api_taf.py
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta, date
import jwt

from sqlalchemy import or_, and_, func
from src import database as db
from src.models import (
    TafAvaliacao, User, Militar, PostoGrad, Quadro, Obm, MilitarObmFuncao
)
from src.authz_api import user_has_perm
from src import bcrypt
from src.auth_jwt import require_taf_auth

bp_api_taf = Blueprint("api_taf", __name__, url_prefix="/api/taf")

JWT_EXP_MINUTES = 60 * 12
JWT_ISSUER = "cbmam-drh"

# Permissões por atividade (mantive tua estrutura)
ATIV_PERMS = {
    # NORMAL
    "corrida_12min_m": "APP_TAF_CORRIDA",
    "flexao_rep": "APP_TAF_FLEXAO",
    "abdominal_rep": "APP_TAF_ABDOMINAL",
    "barra_dinamica_rep": "APP_TAF_BARRA_DINAMICA",
    "barra_estatica_s": "APP_TAF_BARRA_ESTATICA",
    "natacao_50m_s": "APP_TAF_NATACAO",

    # ESPECIAL (usei as mais próximas; se quiser granular, criamos novas perms)
    "caminhada_3000m_s": "APP_TAF_CORRIDA",
    "caminhada_12min_m": "APP_TAF_CORRIDA",
    "supino_40pct_rep": "APP_TAF_FLEXAO",
    "prancha_s": "APP_TAF_ABDOMINAL",
    "puxador_frontal_dinamico_rep": "APP_TAF_BARRA_DINAMICA",
    "puxador_frontal_estatico_s": "APP_TAF_BARRA_ESTATICA",
    "flutuacao_vertical_s": "APP_TAF_NATACAO",
    "natacao_12min_m": "APP_TAF_NATACAO",
}

# Campos permitidos no payload por modalidade
NORMAL_FIELDS = [
    "corrida_12min_m",
    "flexao_rep",
    "abdominal_rep",
    "barra_dinamica_rep",
    "barra_estatica_s",
    "natacao_50m_s",
]

ESPECIAL_FIELDS = [
    "caminhada_3000m_s",
    "caminhada_12min_m",
    "supino_40pct_rep",
    "prancha_s",
    "puxador_frontal_dinamico_rep",
    "puxador_frontal_estatico_s",
    "flutuacao_vertical_s",
    "natacao_12min_m",
]

ALL_FIELDS = set(NORMAL_FIELDS + ESPECIAL_FIELDS)


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


def norm_sexo(s):
    s = (s or "").strip().lower()
    if s.startswith("m"):
        return "M"
    if s.startswith("f"):
        return "F"
    return None


def _parse_int(v):
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except Exception:
        return None


def _now_utc():
    return datetime.utcnow()


def _validate_modalidade(modalidade: str):
    mod = (modalidade or "").strip().upper()
    if mod not in {"NORMAL", "ESPECIAL"}:
        return None
    return mod


def _validate_sexo(sexo: str):
    sx = (sexo or "").strip().upper()
    if sx not in {"M", "F"}:
        return None
    return sx


def _validate_required_perm(user_id: int):
    if not user_has_perm(user_id, "APP_TAF_LOGIN"):
        return False
    return True


def _validate_activity_perms(user_id: int, payload: dict):
    """
    Se o payload tiver um campo de atividade preenchido (não None),
    exige permissão correspondente (quando mapeada).
    """
    for field, perm in ATIV_PERMS.items():
        if field in payload and payload.get(field) is not None:
            if perm and not user_has_perm(user_id, perm):
                return False, field
    return True, None


def _militar_exists(militar_id: int) -> bool:
    return bool(
        db.session.query(Militar.id)
        .filter(Militar.id == militar_id, Militar.inativo.is_(False))
        .scalar()
    )


@bp_api_taf.post("/login")
def login():
    data = request.get_json(silent=True) or {}

    cpf = _cpf_norm(data.get("cpf") or data.get("login") or "")
    senha = (data.get("senha") or "").strip()

    if not cpf or not senha:
        return jsonify({"ok": False, "error": "CPF e senha são obrigatórios."}), 400

    user = db.session.query(User).filter(User.cpf_norm == cpf).first()
    if user is None:
        return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

    try:
        ok = bcrypt.check_password_hash(user.senha, senha)
    except Exception:
        ok = False

    if not ok:
        return jsonify({"ok": False, "error": "Credenciais inválidas."}), 401

    if not user_has_perm(user.id, "APP_TAF_LOGIN"):
        return jsonify({"ok": False, "error": "Usuário sem permissão para o App TAF."}), 403

    # "atividades liberadas" baseado nas permissões que já existem
    allowed = []
    for field, perm in ATIV_PERMS.items():
        if perm and user_has_perm(user.id, perm):
            allowed.append(field)

    secret = current_app.config.get(
        "JWT_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        return jsonify({"ok": False, "error": "JWT_SECRET não configurado no servidor."}), 500

    payload = {
        "sub": str(user.id),
        "name": user.nome,
        "iat": int(_now_utc().timestamp()),
        "exp": int((_now_utc() + timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
        "iss": JWT_ISSUER,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    return jsonify({
        "ok": True,
        "token": token,
        "user": {"id": user.id, "nome": user.nome, "cpf": user.cpf},
        "allowed_fields": allowed,
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
            "sexo": norm_sexo(m.sexo),
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
            "sexo": norm_sexo(m.sexo),
            "idade": calc_age(m.data_nascimento),
            "posto_grad": (pg.sigla if pg else None),
            "quadro": (qd.quadro if qd else None),
            "obm": (obm.sigla if obm else None),
        }
    }), 200


@bp_api_taf.post("/avaliacoes")
@require_taf_auth
def criar_sessao_taf():
    """
    NOVO: cria 1 sessão de TAF (1 linha na tabela).
    O payload pode conter várias atividades (colunas).
    """
    data = request.get_json(silent=True) or {}

    user_id = int(getattr(request, "taf_user_id", 0) or 0)
    if not user_id:
        return jsonify({"ok": False, "error": "Token inválido."}), 401

    if not _validate_required_perm(user_id):
        return jsonify({"ok": False, "error": "Sem permissão para o App TAF."}), 403

    militar_id = int(data.get("militar_id") or 0)
    modalidade = _validate_modalidade(data.get("modalidade"))
    sexo = _validate_sexo(data.get("sexo"))
    idade = data.get("idade")

    avaliador_label = (data.get("avaliador_label") or "").strip() or None
    substituto_nome = (data.get("substituto_nome") or "").strip() or None
    observacoes = (data.get("observacoes") or "").strip() or None

    if not militar_id or not modalidade or not sexo or idade is None:
        return jsonify({"ok": False, "error": "Campos obrigatórios: militar_id, modalidade(NORMAL/ESPECIAL), sexo(M/F), idade."}), 400

    if not _militar_exists(militar_id):
        return jsonify({"ok": False, "error": "Militar não encontrado/inativo."}), 404

    try:
        idade = int(idade)
    except Exception:
        return jsonify({"ok": False, "error": "Idade inválida."}), 400

    # monta payload só com colunas de atividades válidas
    atividades_payload = {}
    for k in ALL_FIELDS:
        if k in data:
            atividades_payload[k] = _parse_int(data.get(k))

    # valida se mandou ao menos 1 atividade
    if not any(v is not None for v in atividades_payload.values()):
        return jsonify({"ok": False, "error": "Envie pelo menos 1 atividade no payload."}), 400

    # valida permissão por atividade preenchida
    ok, field = _validate_activity_perms(user_id, atividades_payload)
    if not ok:
        return jsonify({"ok": False, "error": f"Sem permissão para lançar a atividade/campo: {field}."}), 403

    # (opcional) valida compatibilidade básica modalidade x campos
    if modalidade == "NORMAL":
        invalid = [k for k, v in atividades_payload.items(
        ) if v is not None and k not in NORMAL_FIELDS]
        if invalid:
            return jsonify({"ok": False, "error": f"Campos inválidos para NORMAL: {', '.join(invalid)}"}), 400

    if modalidade == "ESPECIAL":
        invalid = [k for k, v in atividades_payload.items(
        ) if v is not None and k not in ESPECIAL_FIELDS]
        if invalid:
            return jsonify({"ok": False, "error": f"Campos inválidos para ESPECIAL: {', '.join(invalid)}"}), 400

    row = TafAvaliacao(
        militar_id=militar_id,
        avaliador_user_id=user_id,
        modalidade=modalidade,
        sexo=sexo,
        idade=idade,
        avaliador_label=avaliador_label,
        substituto_nome=substituto_nome,
        observacoes=observacoes,
        **atividades_payload
    )

    db.session.add(row)
    db.session.commit()

    return jsonify({"ok": True, "id": row.id}), 201


@bp_api_taf.get("/avaliacoes")
@require_taf_auth
def listar_sessoes_taf():
    """
    NOVO: lista sessões (1 linha por sessão).
    Filtros:
      - data=YYYY-MM-DD (filtra por dia)
      - militar_id
      - modalidade (NORMAL/ESPECIAL)
    """
    user_id = int(getattr(request, "taf_user_id", 0) or 0)
    if not user_id:
        return jsonify({"ok": False, "error": "Token inválido."}), 401

    if not _validate_required_perm(user_id):
        return jsonify({"ok": False, "error": "Sem permissão para o App TAF."}), 403

    data_str = (request.args.get("data") or "").strip()
    militar_id = request.args.get("militar_id")
    modalidade = (request.args.get("modalidade") or "").strip().upper()

    q = db.session.query(TafAvaliacao)

    if data_str:
        try:
            d0 = datetime.strptime(data_str, "%Y-%m-%d")
            d1 = d0 + timedelta(days=1)
            q = q.filter(TafAvaliacao.criado_em >= d0,
                         TafAvaliacao.criado_em < d1)
        except Exception:
            return jsonify({"ok": False, "error": "Parâmetro data inválido. Use YYYY-MM-DD."}), 400

    if modalidade:
        if modalidade not in {"NORMAL", "ESPECIAL"}:
            return jsonify({"ok": False, "error": "modalidade inválida. Use NORMAL ou ESPECIAL."}), 400
        q = q.filter(TafAvaliacao.modalidade == modalidade)

    if militar_id:
        try:
            mid = int(militar_id)
            q = q.filter(TafAvaliacao.militar_id == mid)
        except Exception:
            return jsonify({"ok": False, "error": "militar_id inválido."}), 400

    q = q.order_by(TafAvaliacao.criado_em.desc()).limit(200)

    items = []
    for r in q.all():
        item = {
            "id": r.id,
            "militar_id": r.militar_id,
            "avaliador_user_id": r.avaliador_user_id,
            "modalidade": r.modalidade,
            "sexo": r.sexo,
            "idade": r.idade,
            "avaliador_label": r.avaliador_label,
            "substituto_nome": r.substituto_nome,
            "observacoes": r.observacoes,
            "criado_em": r.criado_em.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # inclui só campos de atividades que existirem
        for k in ALL_FIELDS:
            v = getattr(r, k, None)
            if v is not None:
                item[k] = int(v)

        items.append(item)

    return jsonify({"ok": True, "items": items}), 200
