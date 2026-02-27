# routes_taf.py
from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, abort, Response
from flask_login import login_required

from sqlalchemy import func, and_, cast, Numeric, literal_column
from sqlalchemy.orm import aliased

from src import database as db
from src.models import (
    TafAvaliacao, Militar, PostoGrad, Quadro, Obm, MilitarObmFuncao, User
)
from src.authz import can_see_taf_panel, has_perm

MANAUS_TZ = ZoneInfo("America/Manaus")

taf_admin_bp = Blueprint("taf_admin", __name__, url_prefix="/taf")


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


def _parse_score(score_linha: str | None):
    """
    score_linha vem como string (ex: '6', '6.0', '6,0', 'APTO', etc.)
    Retorna float ou None
    """
    if not score_linha:
        return None
    t = (score_linha or "").strip().upper()
    t = t.replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def _status_from_scores(scores: list[float | None]) -> str:
    # INAPTO se qualquer score numérico < 6
    for s in scores:
        if s is not None and s < 6:
            return "INAPTO"
    # Se tem ao menos 1 nota numérica e nenhuma < 6, APTO
    if any(s is not None for s in scores):
        return "APTO"
    return "SEM_NOTA"


def agg_notas_sql(atividade: str):
    """
    Postgres: concatena todo o histórico de score_linha daquela atividade, ordenado por criado_em.
    Ex:
      array_to_string(
         array_agg(score_linha ORDER BY criado_em) FILTER (WHERE atividade='corrida'),
         ' | '
      )
    Observação: atividade é FIXA no código (não vem do usuário), então é seguro.
    """
    sql = f"""
    array_to_string(
        array_agg(taf_avaliacao.score_linha ORDER BY taf_avaliacao.criado_em)
        FILTER (WHERE taf_avaliacao.atividade = '{atividade}'),
        ' | '
    )
    """
    return literal_column(sql)


def _obm_atual_subquery():
    """
    Subquery que retorna o vínculo ativo mais recente (data_fim IS NULL) por militar.
    """
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


# ---------------------------
# routes
# ---------------------------

@taf_admin_bp.route("/painel")
@login_required
def painel():
    taf_panel_required()

    q_nome = (request.args.get("q") or "").strip()
    q_status = (request.args.get("status") or "").strip().upper()
    q_obm = (request.args.get("obm") or "").strip()
    dt_ini = _to_date(request.args.get("dt_ini"))
    dt_fim = _to_date(request.args.get("dt_fim"))

    page = int(request.args.get("page") or 1)
    per_page = min(int(request.args.get("per_page") or 25), 100)

    # OBM atual
    mof_atual = _obm_atual_subquery()
    obm = aliased(Obm)

    # extrai número de score_linha (pra min_score)
    score_txt = func.nullif(
        func.regexp_replace(TafAvaliacao.score_linha, r"[^0-9,\.]", "", "g"),
        ""
    )
    score_num = cast(func.replace(score_txt, ",", "."), Numeric)
    min_score_all = func.min(score_num)

    # 1 MILITAR = 1 LINHA (HISTÓRICO TODO)
    base = (
        db.session.query(
            TafAvaliacao.militar_id.label("militar_id"),

            Militar.nome_completo.label("nome"),
            PostoGrad.sigla.label("posto"),
            Quadro.quadro.label("quadro"),
            obm.sigla.label("obm_sigla"),

            func.min(func.date(TafAvaliacao.criado_em)).label("primeira_data"),
            func.max(func.date(TafAvaliacao.criado_em)).label("ultima_data"),

            agg_notas_sql("corrida").label("corrida"),
            agg_notas_sql("flexao").label("flexao"),
            agg_notas_sql("abdominal").label("abdominal"),
            agg_notas_sql("barra_dinamica").label("barra_dinamica"),
            agg_notas_sql("barra_estatica").label("barra_estatica"),
            agg_notas_sql("natacao").label("natacao"),

            func.count(TafAvaliacao.id).label("qtd_lancamentos"),
            min_score_all.label("min_score"),
        )
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

    # filtros (afetam o histórico agregado)
    if dt_ini:
        base = base.filter(func.date(TafAvaliacao.criado_em) >= dt_ini)
    if dt_fim:
        base = base.filter(func.date(TafAvaliacao.criado_em) <= dt_fim)

    if q_nome:
        like = f"%{q_nome.upper()}%"
        base = base.filter(func.upper(Militar.nome_completo).like(like))

    if q_obm.isdigit():
        base = base.filter(obm.id == int(q_obm))

    total = base.count()
    rows = base.limit(per_page).offset((page - 1) * per_page).all()

    out = []
    for r in rows:
        # status pelo menor score numérico encontrado no histórico filtrado
        if r.min_score is None:
            status = "SEM_NOTA"
        else:
            status = "INAPTO" if float(r.min_score) < 6 else "APTO"

        if q_status and status != q_status:
            continue

        out.append({
            "militar_id": r.militar_id,
            "nome": r.nome,
            "posto": r.posto,
            "quadro": r.quadro,
            "obm": r.obm_sigla or "-",

            "primeira_data": r.primeira_data,
            "ultima_data": r.ultima_data,

            "corrida": r.corrida,
            "flexao": r.flexao,
            "abdominal": r.abdominal,
            "barra_dinamica": r.barra_dinamica,
            "barra_estatica": r.barra_estatica,
            "natacao": r.natacao,

            "qtd_lancamentos": r.qtd_lancamentos,
            "status": status,
            "min_score": float(r.min_score) if r.min_score is not None else None,
        })

    return render_template(
        "taf/painel.html",
        rows=out,
        total=total,
        page=page,
        per_page=per_page,
        q=q_nome,
        status=q_status,
        obm=q_obm,
        dt_ini=dt_ini.isoformat() if dt_ini else "",
        dt_fim=dt_fim.isoformat() if dt_fim else "",
        can_export=has_perm("TAF_PAINEL_EXPORT") or has_perm("SYS_SUPER"),
    )


@taf_admin_bp.route("/painel/<int:militar_id>")
@login_required
def historico_militar(militar_id: int):
    """
    Auditoria detalhada (histórico completo linha a linha).
    """
    taf_panel_required()

    q = (
        db.session.query(TafAvaliacao, User.nome.label("avaliador_nome"))
        .join(User, User.id == TafAvaliacao.avaliador_user_id)
        .filter(TafAvaliacao.militar_id == militar_id)
        .order_by(TafAvaliacao.criado_em.desc())
    )

    itens = []
    scores = []
    for av, avaliador_nome in q.all():
        sc = _parse_score(av.score_linha)
        scores.append(sc)
        itens.append({
            "atividade": av.atividade,
            "idade": av.idade,
            "valor": str(av.valor),
            "score_linha": av.score_linha,
            "resultado_ok": av.resultado_ok,
            "referencia": av.referencia,
            "avaliador_label": av.avaliador_label,
            "avaliador_nome": avaliador_nome,
            "substituto_nome": av.substituto_nome,
            "observacoes": av.observacoes,
            "criado_em": av.criado_em,
        })

    status = _status_from_scores(scores)

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


@taf_admin_bp.route("/painel/<int:militar_id>/<string:dia>")
@login_required
def detalhe(militar_id: int, dia: str):
    """
    Detalhe por dia (opcional). Você pode manter ou remover.
    """
    taf_panel_required()

    dt = _to_date(dia)
    if not dt:
        abort(404)

    q = (
        db.session.query(TafAvaliacao, User.nome.label("avaliador_nome"))
        .join(User, User.id == TafAvaliacao.avaliador_user_id)
        .filter(
            TafAvaliacao.militar_id == militar_id,
            func.date(TafAvaliacao.criado_em) == dt
        )
        .order_by(TafAvaliacao.criado_em.asc())
    )

    itens = []
    scores = []
    for av, avaliador_nome in q.all():
        sc = _parse_score(av.score_linha)
        scores.append(sc)
        itens.append({
            "atividade": av.atividade,
            "idade": av.idade,
            "valor": str(av.valor),
            "score_linha": av.score_linha,
            "resultado_ok": av.resultado_ok,
            "referencia": av.referencia,
            "avaliador_label": av.avaliador_label,
            "avaliador_nome": avaliador_nome,
            "substituto_nome": av.substituto_nome,
            "observacoes": av.observacoes,
            "criado_em": av.criado_em,
        })

    status = _status_from_scores(scores)

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
        "taf/detalhe.html",
        militar=militar,
        posto=posto,
        quadro=quadro,
        dia=dt,
        itens=itens,
        status=status
    )


@taf_admin_bp.route("/painel/export.csv")
@login_required
def export_csv():
    """
    Export CSV linha a linha (todas as avaliações), com filtros.
    """
    taf_panel_required()

    if not (has_perm("TAF_PAINEL_EXPORT") or has_perm("SYS_SUPER")):
        abort(403)

    q_nome = (request.args.get("q") or "").strip()
    q_obm = (request.args.get("obm") or "").strip()
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
            TafAvaliacao.atividade,
            TafAvaliacao.score_linha,
            TafAvaliacao.valor,
            TafAvaliacao.idade,
            TafAvaliacao.referencia,
            TafAvaliacao.resultado_ok,
        )
        .join(Militar, Militar.id == TafAvaliacao.militar_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .outerjoin(mof_atual, mof_atual.c.militar_id == Militar.id)
        .outerjoin(obm, obm.id == mof_atual.c.obm_id)
        .order_by(func.date(TafAvaliacao.criado_em).desc(), Militar.nome_completo.asc())
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

    def gen():
        yield "dia,nome,posto,quadro,obm,atividade,nota,valor,idade,referencia,resultado_ok\n"
        for r in base.all():
            nota = (r.score_linha or "").replace("\n", " ").replace(",", ".")
            yield f"{r.dia},{r.nome},{r.posto or ''},{r.quadro or ''},{r.obm_sigla or ''},{r.atividade},{nota},{r.valor},{r.idade},{r.referencia or ''},{r.resultado_ok}\n"

    return Response(
        gen(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=taf_avaliacoes.csv"}
    )
