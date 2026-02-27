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

# -------------------------
# Atividades suportadas (API/DB)
# -------------------------
NORMAL_FIELDS = [
    "corrida_12min_m",
    "flexao_rep",
    "abdominal_rep",
    "barra_dinamica_rep",   # masc normal
    "barra_estatica_s",     # masc normal
    "natacao_50m_s",
]

ESPECIAL_FIELDS = [
    "caminhada_3000m_s",
    "caminhada_12min_m",
    "supino_40pct_rep",
    "prancha_s",
    "puxador_frontal_dinamico_rep",   # masc especial
    "puxador_frontal_estatico_s",
    "flutuacao_vertical_s",
    "natacao_12min_m",
]

ALL_FIELDS = set(NORMAL_FIELDS + ESPECIAL_FIELDS)

# Regras por sexo
# Feminino não tem barras no normal, e não tem puxador dinâmico no especial
NORMAL_FIELDS_M = set(NORMAL_FIELDS)
NORMAL_FIELDS_F = set(["corrida_12min_m", "flexao_rep",
                      "abdominal_rep", "natacao_50m_s"])

ESPECIAL_FIELDS_M = set(ESPECIAL_FIELDS)
ESPECIAL_FIELDS_F = set([
    "caminhada_3000m_s",
    "caminhada_12min_m",
    "supino_40pct_rep",
    "prancha_s",
    "puxador_frontal_estatico_s",
    "flutuacao_vertical_s",
    "natacao_12min_m",
])

# -------------------------
# Permissões por atividade (mantém teu padrão)
# -------------------------
ATIV_PERMS = {
    # NORMAL
    "corrida_12min_m": "APP_TAF_CORRIDA",
    "flexao_rep": "APP_TAF_FLEXAO",
    "abdominal_rep": "APP_TAF_ABDOMINAL",
    "barra_dinamica_rep": "APP_TAF_BARRA_DINAMICA",
    "barra_estatica_s": "APP_TAF_BARRA_ESTATICA",
    "natacao_50m_s": "APP_TAF_NATACAO",

    # ESPECIAL (reaproveitando as permissões existentes)
    "caminhada_3000m_s": "APP_TAF_CORRIDA",
    "caminhada_12min_m": "APP_TAF_CORRIDA",
    "supino_40pct_rep": "APP_TAF_FLEXAO",
    "prancha_s": "APP_TAF_ABDOMINAL",
    "puxador_frontal_dinamico_rep": "APP_TAF_BARRA_DINAMICA",
    "puxador_frontal_estatico_s": "APP_TAF_BARRA_ESTATICA",
    "flutuacao_vertical_s": "APP_TAF_NATACAO",
    "natacao_12min_m": "APP_TAF_NATACAO",
}

# Se quiser evitar duplicar lançamentos do MESMO dia, liga isso:
UPSERT_SAME_DAY = False


# -------------------------
# Helpers
# -------------------------
def _cpf_norm(txt: str) -> str:
    return "".join([c for c in (txt or "") if c.isdigit()])


def _now_utc():
    return datetime.utcnow()


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


def _parse_int_required(v, field_name="valor"):
    if v is None or str(v).strip() == "":
        raise ValueError(f"{field_name} obrigatório")
    try:
        return int(round(float(str(v).strip().replace(",", "."))))
    except Exception:
        raise ValueError(f"{field_name} inválido")


def _validate_required_perm(user_id: int) -> bool:
    return bool(user_has_perm(user_id, "APP_TAF_LOGIN"))


def _militar_exists(militar_id: int) -> bool:
    return bool(
        db.session.query(Militar.id)
        .filter(Militar.id == militar_id, Militar.inativo.is_(False))
        .scalar()
    )


def _allowed_activities_for_user(user_id: int):
    allowed = []
    for ativ, perm in ATIV_PERMS.items():
        if perm and user_has_perm(user_id, perm):
            allowed.append(ativ)
    return allowed


def _validate_activity_allowed_by_table(sexo: str, modalidade: str, atividade: str) -> bool:
    """
    Valida se a atividade existe para aquele sexo/modalidade.
    """
    sexo = _validate_sexo(sexo)
    modalidade = _validate_modalidade(modalidade)
    atividade = (atividade or "").strip()

    if not sexo or not modalidade or not atividade:
        return False

    if modalidade == "NORMAL":
        allowed = NORMAL_FIELDS_M if sexo == "M" else NORMAL_FIELDS_F
        return atividade in allowed

    allowed = ESPECIAL_FIELDS_M if sexo == "M" else ESPECIAL_FIELDS_F
    return atividade in allowed


def _require_activity_perm(user_id: int, atividade: str):
    perm = ATIV_PERMS.get(atividade)
    if perm and not user_has_perm(user_id, perm):
        return False, perm
    return True, None


def _day_window(data_str: str):
    d0 = datetime.strptime(data_str, "%Y-%m-%d")
    d1 = d0 + timedelta(days=1)
    return d0, d1


# -------------------------
# Auth
# -------------------------
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

    # atividades liberadas (para UI)
    allowed = _allowed_activities_for_user(user.id)

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
        # Mantive o nome antigo pra não quebrar teu Flet
        "allowed_activities": allowed,
    }), 200


# -------------------------
# Militares
# -------------------------
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


# -------------------------
# Avaliações (1 POST = 1 atividade)
# -------------------------
@bp_api_taf.post("/avaliacoes")
@require_taf_auth
def criar_avaliacao():
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
    atividade = (data.get("atividade") or "").strip()
    valor = data.get("valor")

    avaliador_label = (data.get("avaliador_label") or "").strip() or None
    substituto_nome = (data.get("substituto_nome") or "").strip() or None
    observacoes = (data.get("observacoes") or "").strip() or None

    if not militar_id or not modalidade or not sexo or idade is None or not atividade or valor is None:
        return jsonify({"ok": False, "error": "Campos obrigatórios: militar_id, modalidade, sexo, idade, atividade, valor."}), 400

    if not _militar_exists(militar_id):
        return jsonify({"ok": False, "error": "Militar não encontrado/inativo."}), 404

    try:
        idade = int(idade)
    except Exception:
        return jsonify({"ok": False, "error": "Idade inválida."}), 400

    try:
        valor_int = _parse_int_required(valor, "valor")
    except ValueError as ex:
        return jsonify({"ok": False, "error": str(ex)}), 400

    # valida atividade existe (e para aquele sexo/modalidade)
    if atividade not in ALL_FIELDS:
        return jsonify({"ok": False, "error": "Atividade inválida."}), 400

    if not _validate_activity_allowed_by_table(sexo, modalidade, atividade):
        return jsonify({"ok": False, "error": f"Atividade '{atividade}' não disponível para sexo={sexo} modalidade={modalidade}."}), 400

    # permissão por atividade
    ok_perm, perm_needed = _require_activity_perm(user_id, atividade)
    if not ok_perm:
        return jsonify({"ok": False, "error": f"Sem permissão para esta atividade. Necessário: {perm_needed}"}), 403

    # opcional: evitar duplicar por dia (mesmo militar + atividade + modalidade no mesmo dia)
    if UPSERT_SAME_DAY:
        d0 = datetime.now().date().isoformat()
        dt0, dt1 = _day_window(d0)
        existing = (
            db.session.query(TafAvaliacao)
            .filter(
                TafAvaliacao.militar_id == militar_id,
                TafAvaliacao.atividade == atividade,
                TafAvaliacao.modalidade == modalidade,
                TafAvaliacao.criado_em >= dt0,
                TafAvaliacao.criado_em < dt1,
            )
            .order_by(TafAvaliacao.criado_em.desc())
            .first()
        )
        if existing:
            existing.valor = valor_int
            existing.idade = idade
            existing.sexo = sexo
            existing.avaliador_user_id = user_id
            existing.avaliador_label = avaliador_label
            existing.substituto_nome = substituto_nome
            existing.observacoes = observacoes
            db.session.commit()
            return jsonify({"ok": True, "id": existing.id, "updated": True}), 200

    row = TafAvaliacao(
        militar_id=militar_id,
        avaliador_user_id=user_id,
        modalidade=modalidade,
        sexo=sexo,
        idade=idade,
        atividade=atividade,
        valor=valor_int,
        avaliador_label=avaliador_label,
        substituto_nome=substituto_nome,
        observacoes=observacoes,
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

    if not _validate_required_perm(user_id):
        return jsonify({"ok": False, "error": "Sem permissão para o App TAF."}), 403

    # filtros
    data_str = (request.args.get("data") or "").strip()  # YYYY-MM-DD
    atividade = (request.args.get("atividade") or "").strip()
    militar_id = request.args.get("militar_id")
    modalidade = (request.args.get("modalidade") or "").strip().upper()
    sexo = (request.args.get("sexo") or "").strip().upper()

    q = db.session.query(TafAvaliacao)

    if data_str:
        try:
            d0, d1 = _day_window(data_str)
            q = q.filter(TafAvaliacao.criado_em >= d0,
                         TafAvaliacao.criado_em < d1)
        except Exception:
            return jsonify({"ok": False, "error": "Parâmetro data inválido. Use YYYY-MM-DD."}), 400

    if modalidade:
        if modalidade not in {"NORMAL", "ESPECIAL"}:
            return jsonify({"ok": False, "error": "modalidade inválida. Use NORMAL ou ESPECIAL."}), 400
        q = q.filter(TafAvaliacao.modalidade == modalidade)

    if sexo:
        if sexo not in {"M", "F"}:
            return jsonify({"ok": False, "error": "sexo inválido. Use M ou F."}), 400
        q = q.filter(TafAvaliacao.sexo == sexo)

    if atividade:
        if atividade not in ALL_FIELDS:
            return jsonify({"ok": False, "error": "atividade inválida."}), 400
        q = q.filter(TafAvaliacao.atividade == atividade)

    if militar_id:
        try:
            mid = int(militar_id)
            q = q.filter(TafAvaliacao.militar_id == mid)
        except Exception:
            return jsonify({"ok": False, "error": "militar_id inválido."}), 400

    q = q.order_by(TafAvaliacao.criado_em.desc()).limit(300)

    items = []
    for r in q.all():
        items.append({
            "id": r.id,
            "militar_id": r.militar_id,
            "avaliador_user_id": r.avaliador_user_id,
            "modalidade": r.modalidade,
            "sexo": r.sexo,
            "idade": r.idade,
            "atividade": r.atividade,
            "valor": int(r.valor),
            "avaliador_label": r.avaliador_label,
            "substituto_nome": r.substituto_nome,
            "observacoes": r.observacoes,
            "criado_em": r.criado_em.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return jsonify({"ok": True, "items": items}), 200
