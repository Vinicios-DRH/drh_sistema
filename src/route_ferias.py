from flask import Blueprint, render_template, send_file
from io import BytesIO
from openpyxl import Workbook
from sqlalchemy import func, case, and_
from collections import defaultdict

from src.models import MilitarObmFuncao, Paf, Militar, Obm
from src import database

bp_ferias = Blueprint("ferias", __name__)

MILITARES_40_IDS = {
    513, 768, 946, 1, 251, 506, 410, 1026,
    356, 798, 702, 463, 387, 888, 902, 948,
    749, 768, 612
}


def total_dias_expr():
    return (
        func.coalesce(Paf.qtd_dias_primeiro_periodo, 0) +
        func.coalesce(Paf.qtd_dias_segundo_periodo, 0) +
        func.coalesce(Paf.qtd_dias_terceiro_periodo, 0)
    )


def direito_expr():
    return case(
        (Militar.id.in_(MILITARES_40_IDS), 40),
        else_=30
    ).label("direito_total_dias")


def _build_periodos_from_pafs(pafs):
    """Monta lista de períodos detalhados a partir dos PAFs de um militar."""
    periodos = []

    for paf in pafs:
        # 1º período
        if paf.qtd_dias_primeiro_periodo and paf.primeiro_periodo_ferias:
            periodos.append({
                "label": "1º período",
                "qtd_dias": paf.qtd_dias_primeiro_periodo,
                "inicio": paf.primeiro_periodo_ferias,
                "fim": paf.fim_primeiro_periodo,
                "mes_usufruto": paf.mes_usufruto,
            })
        # 2º período
        if paf.qtd_dias_segundo_periodo and paf.segundo_periodo_ferias:
            periodos.append({
                "label": "2º período",
                "qtd_dias": paf.qtd_dias_segundo_periodo,
                "inicio": paf.segundo_periodo_ferias,
                "fim": paf.fim_segundo_periodo,
                "mes_usufruto": paf.mes_usufruto,
            })
        # 3º período
        if paf.qtd_dias_terceiro_periodo and paf.terceiro_periodo_ferias:
            periodos.append({
                "label": "3º período",
                "qtd_dias": paf.qtd_dias_terceiro_periodo,
                "inicio": paf.terceiro_periodo_ferias,
                "fim": paf.fim_terceiro_periodo,
                "mes_usufruto": paf.mes_usufruto,
            })

    return periodos


def _flag_tem_2026_e_cruza(periodos):
    """Retorna flags: tem_2026 (início em 2026), cruza_2025_2026 (início 2025, fim 2026)."""
    tem_2026 = False
    cruza_25_26 = False

    for p in periodos:
        ini = p["inicio"]
        fim = p["fim"]

        # Só conta como "tem_2026" se o período COMEÇA em 2026
        if ini and ini.year == 2026:
            tem_2026 = True

        # Cruzando 2025 -> 2026
        if ini and fim and ini.year == 2025 and fim.year == 2026:
            cruza_25_26 = True

    return tem_2026, cruza_25_26


@bp_ferias.route("/ferias/pendentes")
def ferias_pendentes():
    total_expr = total_dias_expr()
    direito = direito_expr()

    # Query base com agregados – SEM HAVING (pega todo mundo)
    base_query = (
        database.session.query(
            Militar,
            func.coalesce(func.sum(total_expr), 0).label("dias_usufruidos"),
            direito,
            func.string_agg(
                func.distinct(Paf.mes_usufruto),
                ', '
            ).label("meses_usufruidos"),
            Obm.sigla.label("obm_sigla")
        )
        .outerjoin(Paf, Paf.militar_id == Militar.id)
        .outerjoin(
            MilitarObmFuncao,
            and_(
                MilitarObmFuncao.militar_id == Militar.id,
                MilitarObmFuncao.data_fim.is_(None)
            )
        )
        .outerjoin(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .group_by(Militar.id, direito, Obm.sigla)
    )

    raw_registros = base_query.all()  # agora é TODO MUNDO

    # Buscar todos os PAFs desses militares (pra detalhar períodos)
    militar_ids = [m.id for (m, _, _, _, _) in raw_registros]
    pafs = (
        database.session.query(Paf)
        .filter(Paf.militar_id.in_(militar_ids))
        .all()
    )
    pafs_by_militar = defaultdict(list)
    for paf in pafs:
        pafs_by_militar[paf.militar_id].append(paf)

    # Montar estrutura rica pra view
    pendentes = []
    for m, dias, direito_total, meses_agregados, obm_sigla in raw_registros:
        periodos = _build_periodos_from_pafs(pafs_by_militar[m.id])
        tem_2026, cruza_25_26 = _flag_tem_2026_e_cruza(periodos)

        pendentes.append({
            "militar": m,
            "obm_sigla": obm_sigla,
            "dias_usufruidos": dias,
            "direito_total": direito_total,
            "faltam": (direito_total - dias) if direito_total is not None else None,
            "meses_agregados": meses_agregados,
            "periodos": periodos,
            "tem_2026": tem_2026,
            "cruza_25_26": cruza_25_26,
        })

    # Categorias em cima de TODOS os registros
    nenhum_dia = [p for p in pendentes if p["dias_usufruidos"] == 0]
    parcial = [
        p for p in pendentes
        if 0 < p["dias_usufruidos"] < p["direito_total"]
    ]
    completos = [
        p for p in pendentes
        if p["dias_usufruidos"] >= p["direito_total"]
    ]
    com_2026 = [p for p in pendentes if p["tem_2026"]]
    cruzando_25_26 = [p for p in pendentes if p["cruza_25_26"]]

    grafico_data = {
        "sem_dias": len(nenhum_dia),
        "parcial": len(parcial),
        "completos": len(completos),
        "total": len(pendentes),
        "com_2026": len(com_2026),
        "cruza_25_26": len(cruzando_25_26),
    }

    return render_template(
        "ferias_pendentes.html",
        pendentes=pendentes,
        nenhum_dia=nenhum_dia,
        parcial=parcial,
        completos=completos,
        com_2026=com_2026,
        cruzando_25_26=cruzando_25_26,
        grafico=grafico_data
    )


@bp_ferias.route("/ferias/pendentes/excel")
def ferias_pendentes_excel():
    total_expr = total_dias_expr()
    direito = direito_expr()

    base_query = (
        database.session.query(
            Militar,
            func.coalesce(func.sum(total_expr), 0).label("dias_usufruidos"),
            direito,
            func.string_agg(
                func.distinct(Paf.mes_usufruto),
                ', '
            ).label("meses_usufruidos"),
            Obm.sigla.label("obm_sigla")
        )
        .outerjoin(Paf, Paf.militar_id == Militar.id)
        .outerjoin(
            MilitarObmFuncao,
            and_(
                MilitarObmFuncao.militar_id == Militar.id,
                MilitarObmFuncao.data_fim.is_(None)
            )
        )
        .outerjoin(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .group_by(Militar.id, direito, Obm.sigla)
    )

    raw_registros = base_query.all()  # TODO MUNDO

    militar_ids = [m.id for (m, _, _, _, _) in raw_registros]
    pafs = (
        database.session.query(Paf)
        .filter(Paf.militar_id.in_(militar_ids))
        .all()
    )
    pafs_by_militar = defaultdict(list)
    for paf in pafs:
        pafs_by_militar[paf.militar_id].append(paf)

    pendentes = []
    for m, dias, direito_total, meses_agregados, obm_sigla in raw_registros:
        periodos = _build_periodos_from_pafs(pafs_by_militar[m.id])
        tem_2026, cruza_25_26 = _flag_tem_2026_e_cruza(periodos)

        pendentes.append({
            "militar": m,
            "obm_sigla": obm_sigla,
            "dias_usufruidos": dias,
            "direito_total": direito_total,
            "faltam": (direito_total - dias) if direito_total is not None else None,
            "meses_agregados": meses_agregados,
            "periodos": periodos,
            "tem_2026": tem_2026,
            "cruza_25_26": cruza_25_26,
        })

    def fmt_data(d):
        return d.strftime("%d/%m/%Y") if d else ""

    wb = Workbook()
    ws = wb.active
    ws.title = "Férias — Situação Geral"

    ws.append([
        "Nome",
        "Matrícula",
        "OBM",
        "Posto/Grad",
        "Quadro",
        "Dias usufruídos",
        "Direito total",
        "Faltam",
        "Meses (campo mes_usufruto)",
        "Período começa em 2026?",
        "Cruza 2025-2026?",
        "Detalhe períodos (datas e meses)"
    ])

    for p in pendentes:
        m = p["militar"]
        periodos_str = "; ".join(
            f"{per['label']}: {fmt_data(per['inicio'])} a {fmt_data(per['fim'])} "
            f"({per['qtd_dias']} dias, mês: {per['mes_usufruto'] or ''})"
            for per in p["periodos"]
        )

        ws.append([
            m.nome_completo,
            m.matricula,
            p["obm_sigla"] or "",
            m.posto_grad.sigla if m.posto_grad else "",
            m.quadro.quadro if m.quadro else "",
            p["dias_usufruidos"],
            p["direito_total"],
            p["faltam"],
            p["meses_agregados"] or "",
            "Sim" if p["tem_2026"] else "Não",
            "Sim" if p["cruza_25_26"] else "Não",
            periodos_str
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="ferias_situacao_geral.xlsx"
    )
