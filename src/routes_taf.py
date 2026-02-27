# routes_taf.py
from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, abort, Response
from flask_login import login_required

from sqlalchemy import func, and_, cast, Numeric, literal_column, case
from sqlalchemy.orm import aliased

from src import database as db
from src.models import (
    TafAvaliacao, Militar, PostoGrad, Quadro, Obm, MilitarObmFuncao, User
)
from src.authz import can_see_taf_panel, has_perm

MANAUS_TZ = ZoneInfo("America/Manaus")

taf_admin_bp = Blueprint("taf_admin", __name__, url_prefix="/taf")

# =========================
# Catálogo de atividades (IDs novos da API)
# =========================
NORMAL_ATIVS = [
    ("corrida_12min_m", "Corrida 12 min (m)"),
    ("flexao_rep", "Flexão (rep)"),
    ("abdominal_rep", "Abdominal (rep)"),
    ("barra_dinamica_rep", "Barra dinâmica (rep)"),
    ("barra_estatica_s", "Barra estática (s)"),
    ("natacao_50m_s", "Natação 50m (s)"),
]

ESPECIAL_ATIVS = [
    ("caminhada_3000m_s", "Caminhada 3000m (tempo)"),
    ("caminhada_12min_m", "Caminhada 12 min (m)"),
    ("supino_40pct_rep", "Supino 40% (rep)"),
    ("prancha_s", "Prancha (s)"),
    ("puxador_frontal_dinamico_rep", "Puxador dinâmico (rep)"),
    ("puxador_frontal_estatico_s", "Puxador estático (s)"),
    ("flutuacao_vertical_s", "Flutuação vertical (s)"),
    ("natacao_12min_m", "Natação 12 min (m)"),
]

ALL_ATIVS = NORMAL_ATIVS + ESPECIAL_ATIVS
ATIV_LABEL = {k: label for k, label in ALL_ATIVS}


# ---------------------------
# helpers
# ---------------------------
def taf_panel_required():
    if not can_see_taf_panel():
        abort(403)


def _to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _obm_atual_subquery():
    mof = aliased(MilitarObmFuncao)

    sub_mof = (
        db.session.query(
            mof.militar_id.label("militar_id"),
            func.max(mof.data_criacao).label("max_dc")
        )
        .filter(mof.data_fim.is_(None))
        .group_by(mof.militar_id)
        .subquery()
    )

    mof_atual = (
        db.session.query(mof)
        .join(sub_mof, and_(
            mof.militar_id == sub_mof.c.militar_id,
            mof.data_criacao == sub_mof.c.max_dc
        ))
        .subquery()
    )
    return mof_atual


def agg_valores_sql(atividade: str):
    sql = f"""
    array_to_string(
        array_agg((taf_avaliacao.valor::text) ORDER BY taf_avaliacao.criado_em)
        FILTER (WHERE taf_avaliacao.atividade = '{atividade}'),
        ' | '
    )
    """
    return literal_column(sql)


def _status_from_any_fail(qtd: int, any_fail: bool) -> str:
    if qtd <= 0:
        return "SEM_NOTA"
    return "INAPTO" if any_fail else "APTO"


# ---------------------------
# routes
# ---------------------------
@taf_admin_bp.route("/painel")
@login_required
def painel():
    taf_panel_required()

    q_nome = (request.args.get("q") or "").strip()
    q_status = (request.args.get("status") or "").strip(
    ).upper()      # APTO/INAPTO/SEM_NOTA
    q_obm = (request.args.get("obm") or "").strip()                    # id obm
    q_modalidade = (request.args.get("modalidade")
                    or "").strip().upper()  # NORMAL/ESPECIAL
    q_sexo = (request.args.get("sexo") or "").strip().upper()          # M/F
    dt_ini = _to_date(request.args.get("dt_ini"))
    dt_fim = _to_date(request.args.get("dt_fim"))

    page = max(int(request.args.get("page") or 1), 1)
    per_page = min(int(request.args.get("per_page") or 25), 100)

    mof_atual = _obm_atual_subquery()
    obm = aliased(Obm)

    # any_fail = soma de resultado_ok false
    fails_count = func.sum(
        cast(case((TafAvaliacao.resultado_ok.is_(False), 1), else_=0), Numeric)
    ).label("fails_count")

    qtd_lanc = func.count(TafAvaliacao.id).label("qtd_lancamentos")

    base_cols = [
        TafAvaliacao.militar_id.label("militar_id"),

        Militar.nome_completo.label("nome"),
        PostoGrad.sigla.label("posto"),
        Quadro.quadro.label("quadro"),
        obm.sigla.label("obm_sigla"),

        func.min(func.date(TafAvaliacao.criado_em)).label("primeira_data"),
        func.max(func.date(TafAvaliacao.criado_em)).label("ultima_data"),

        func.max(TafAvaliacao.sexo).label("sexo"),
        func.max(TafAvaliacao.modalidade).label("modalidade"),

        qtd_lanc,
        fails_count,
    ]

    for ativ_id, _label in ALL_ATIVS:
        base_cols.append(agg_valores_sql(ativ_id).label(ativ_id))

    base = (
        db.session.query(*base_cols)
        .join(Militar, Militar.id == TafAvaliacao.militar_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .outerjoin(mof_atual, mof_atual.c.militar_id == Militar.id)
        .outerjoin(obm, obm.id == mof_atual.c.obm_id)
        .group_by(
            TafAvaliacao.militar_id,
            Militar.nome_completo,
            PostoGrad.sigla,
            Quadro.quadro,
            obm.sigla
        )
        .order_by(Militar.nome_completo.asc())
    )

    if dt_ini:
        base = base.filter(func.date(TafAvaliacao.criado_em) >= dt_ini)
    if dt_fim:
        base = base.filter(func.date(TafAvaliacao.criado_em) <= dt_fim)

    if q_nome:
        like = f"%{q_nome.upper()}%"
        base = base.filter(func.upper(Militar.nome_completo).like(like))

    if q_obm.isdigit():
        base = base.filter(obm.id == int(q_obm))

    if q_modalidade in {"NORMAL", "ESPECIAL"}:
        base = base.filter(TafAvaliacao.modalidade == q_modalidade)

    if q_sexo in {"M", "F"}:
        base = base.filter(TafAvaliacao.sexo == q_sexo)

    total = base.count()
    rows = base.limit(per_page).offset((page - 1) * per_page).all()

    out = []
    for r in rows:
        any_fail = (float(r.fails_count or 0) > 0)
        status = _status_from_any_fail(int(r.qtd_lancamentos or 0), any_fail)

        if q_status and status != q_status:
            continue

        item = {
            "militar_id": r.militar_id,
            "nome": r.nome,
            "posto": r.posto,
            "quadro": r.quadro,
            "obm": r.obm_sigla or "-",

            "sexo": getattr(r, "sexo", None) or "-",
            "modalidade": getattr(r, "modalidade", None) or "-",

            "primeira_data": r.primeira_data,
            "ultima_data": r.ultima_data,
            "qtd_lancamentos": int(r.qtd_lancamentos or 0),
            "status": status,
        }

        for ativ_id, _label in ALL_ATIVS:
            item[ativ_id] = getattr(r, ativ_id, None)

        out.append(item)

    return render_template(
        "taf/painel.html",
        rows=out,
        total=total,
        page=page,
        per_page=per_page,

        q=q_nome,
        status=q_status,
        obm=q_obm,
        modalidade=q_modalidade,
        sexo=q_sexo,
        dt_ini=dt_ini.isoformat() if dt_ini else "",
        dt_fim=dt_fim.isoformat() if dt_fim else "",

        can_export=has_perm("TAF_PAINEL_EXPORT") or has_perm("SYS_SUPER"),

        ativ_label=ATIV_LABEL,
        normal_ativs=[k for k, _ in NORMAL_ATIVS],
        especial_ativs=[k for k, _ in ESPECIAL_ATIVS],
    )


@taf_admin_bp.route("/painel/<int:militar_id>")
@login_required
def historico_militar(militar_id: int):
    taf_panel_required()

    q = (
        db.session.query(TafAvaliacao, User.nome.label("avaliador_nome"))
        .join(User, User.id == TafAvaliacao.avaliador_user_id)
        .filter(TafAvaliacao.militar_id == militar_id)
        .order_by(TafAvaliacao.criado_em.desc())
    )

    itens = []
    any_fail = False
    qtd = 0

    for av, avaliador_nome in q.all():
        qtd += 1
        if av.resultado_ok is False:
            any_fail = True

        itens.append({
            "atividade": av.atividade,
            "atividade_label": ATIV_LABEL.get(av.atividade, av.atividade),
            "modalidade": getattr(av, "modalidade", None),
            "sexo": getattr(av, "sexo", None),
            "idade": av.idade,
            "valor": str(av.valor),
            "resultado_ok": bool(av.resultado_ok),
            "referencia": getattr(av, "referencia", None),
            "score_linha": getattr(av, "score_linha", None),
            "avaliador_label": av.avaliador_label,
            "avaliador_nome": avaliador_nome,
            "substituto_nome": av.substituto_nome,
            "observacoes": av.observacoes,
            "criado_em": av.criado_em,
        })

    status = _status_from_any_fail(qtd, any_fail)

    mil = (
        db.session.query(Militar, PostoGrad.sigla, Quadro.quadro)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .filter(Militar.id == militar_id)
        .first()
    )
    if not mil:
        abort(404)

    militar, posto, quadro = mil

    return render_template(
        "taf/historico.html",
        militar=militar,
        posto=posto,
        quadro=quadro,
        itens=itens,
        status=status
    )


@taf_admin_bp.route("/painel/export.csv")
@login_required
def export_csv():
    taf_panel_required()

    if not (has_perm("TAF_PAINEL_EXPORT") or has_perm("SYS_SUPER")):
        abort(403)

    q_nome = (request.args.get("q") or "").strip()
    q_obm = (request.args.get("obm") or "").strip()
    q_modalidade = (request.args.get("modalidade") or "").strip().upper()
    q_sexo = (request.args.get("sexo") or "").strip().upper()
    dt_ini = _to_date(request.args.get("dt_ini"))
    dt_fim = _to_date(request.args.get("dt_fim"))

    mof_atual = _obm_atual_subquery()
    obm = aliased(Obm)

    base = (
        db.session.query(
            func.date(TafAvaliacao.criado_em).label("dia"),
            Militar.nome_completo.label("nome"),
            PostoGrad.sigla.label("posto"),
            Quadro.quadro.label("quadro"),
            obm.sigla.label("obm_sigla"),
            TafAvaliacao.sexo,
            TafAvaliacao.modalidade,
            TafAvaliacao.atividade,
            TafAvaliacao.valor,
            TafAvaliacao.idade,
            TafAvaliacao.resultado_ok,
            TafAvaliacao.avaliador_label,
            TafAvaliacao.substituto_nome,
        )
        .join(Militar, Militar.id == TafAvaliacao.militar_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .outerjoin(mof_atual, mof_atual.c.militar_id == Militar.id)
        .outerjoin(obm, obm.id == mof_atual.c.obm_id)
        .order_by(TafAvaliacao.criado_em.desc(), Militar.nome_completo.asc())
    )

    if dt_ini:
        base = base.filter(func.date(TafAvaliacao.criado_em) >= dt_ini)
    if dt_fim:
        base = base.filter(func.date(TafAvaliacao.criado_em) <= dt_fim)

    if q_nome:
        like = f"%{q_nome.upper()}%"
        base = base.filter(func.upper(Militar.nome_completo).like(like))

    if q_obm.isdigit():
        base = base.filter(obm.id == int(q_obm))

    if q_modalidade in {"NORMAL", "ESPECIAL"}:
        base = base.filter(TafAvaliacao.modalidade == q_modalidade)

    if q_sexo in {"M", "F"}:
        base = base.filter(TafAvaliacao.sexo == q_sexo)

    def gen():
        yield "dia,nome,posto,quadro,obm,sexo,modalidade,atividade,atividade_label,valor,idade,resultado_ok,avaliador_label,substituto_nome\n"
        for r in base.all():
            atividade_label = ATIV_LABEL.get(r.atividade, r.atividade)
            yield (
                f"{r.dia},{r.nome},{r.posto or ''},{r.quadro or ''},{r.obm_sigla or ''},"
                f"{r.sexo or ''},{r.modalidade or ''},{r.atividade},{atividade_label},"
                f"{r.valor},{r.idade},{bool(r.resultado_ok)},{(r.avaliador_label or '').replace(',', ' ')},{(r.substituto_nome or '').replace(',', ' ')}\n"
            )

    return Response(
        gen(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=taf_avaliacoes.csv"}
    )
