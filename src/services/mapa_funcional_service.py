from datetime import date, datetime
from collections import defaultdict, Counter

from src.models import (
    Militar,
    MilitaresAgregados,
    MilitaresADisposicao,
    LicencaEspecial,
    LicencaParaTratamentoDeSaude,
    Paf,
)


def _to_date(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def _parse_date_str(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except Exception:
        return None


def _registro_vigente(inicio, fim, hoje):
    inicio = _to_date(inicio)
    fim = _to_date(fim)

    if not inicio:
        return False
    if inicio > hoje:
        return False
    if fim is None:
        return True
    return fim >= hoje


def _status_periodo(inicio, fim, hoje):
    inicio = _to_date(inicio)
    fim = _to_date(fim)

    if not inicio:
        return "SEM DATA"

    if inicio > hoje:
        return "A INICIAR"

    if fim is None:
        return "VIGENTE"

    if inicio <= hoje <= fim:
        return "VIGENTE"

    if fim < hoje:
        return "VENCIDO"

    return "ENCERRADO"


def _dias_para_fim(fim, hoje):
    fim = _to_date(fim)
    if not fim:
        return None
    return (fim - hoje).days


def _escolher_vigente_ou_recente(registros, campo_inicio, campo_fim, hoje):
    if not registros:
        return None

    vigentes = [
        r for r in registros
        if _registro_vigente(getattr(r, campo_inicio), getattr(r, campo_fim), hoje)
    ]
    if vigentes:
        vigentes.sort(
            key=lambda r: getattr(r, campo_inicio) or date.min,
            reverse=True
        )
        return vigentes[0]

    registros.sort(
        key=lambda r: getattr(r, campo_inicio) or date.min,
        reverse=True
    )
    return registros[0]


def _tem_intersecao_periodo(inicio_1, fim_1, inicio_2, fim_2):
    inicio_1 = _to_date(inicio_1)
    fim_1 = _to_date(fim_1)
    inicio_2 = _to_date(inicio_2)
    fim_2 = _to_date(fim_2)

    if not inicio_1 or not fim_1 or not inicio_2 or not fim_2:
        return False

    return inicio_1 <= fim_2 and fim_1 >= inicio_2


def _militar_em_ferias(paf, data_inicio, data_fim):
    if not paf or not data_inicio or not data_fim:
        return False

    periodos = [
        (paf.primeiro_periodo_ferias, paf.fim_primeiro_periodo),
        (paf.segundo_periodo_ferias, paf.fim_segundo_periodo),
        (paf.terceiro_periodo_ferias, paf.fim_terceiro_periodo),
    ]

    for inicio, fim in periodos:
        if _tem_intersecao_periodo(inicio, fim, data_inicio, data_fim):
            return True

    return False


def _obter_destino_nome(militar, agregado=None, disposicao=None, le=None, lts=None):
    for registro in (disposicao, agregado, le, lts):
        if registro and getattr(registro, "destino", None):
            return registro.destino.local

    if militar.destino:
        return militar.destino.local

    return "NÃO INFORMADO"


def _registro_info(registro, campo_inicio, campo_fim, hoje):
    if not registro:
        return {
            "existe": False,
            "inicio": None,
            "fim": None,
            "status": "NÃO",
            "dias_para_fim": None,
        }

    inicio = _to_date(getattr(registro, campo_inicio, None))
    fim = _to_date(getattr(registro, campo_fim, None))

    return {
        "existe": True,
        "inicio": inicio,
        "fim": fim,
        "status": _status_periodo(inicio, fim, hoje),
        "dias_para_fim": _dias_para_fim(fim, hoje),
    }


def _gerar_status_resumido(agregado_info, disposicao_info, le_info, lts_info):
    partes = []

    if agregado_info["existe"]:
        partes.append(f"AGREGADO ({agregado_info['status']})")

    if disposicao_info["existe"]:
        partes.append(f"À DISPOSIÇÃO ({disposicao_info['status']})")

    if le_info["existe"]:
        partes.append(f"LE ({le_info['status']})")

    if lts_info["existe"]:
        partes.append(f"LTS ({lts_info['status']})")

    if partes:
        return " + ".join(partes)

    return "PRONTO"


def _status_macro(linha):
    if linha["na_intersecao"]:
        return "INTERSEÇÃO"

    if linha["esta_lts"]:
        return "LTS"

    if linha["esta_le"]:
        return "LE"

    if linha["esta_agregado"]:
        return "AGREGADO"

    if linha["esta_disposicao"]:
        return "À DISPOSIÇÃO"

    return "PRONTO"


def _filtro_texto_ok(linha, q):
    if not q:
        return True
    q = q.strip().upper()
    base = " ".join([
        linha.get("nome", "") or "",
        linha.get("matricula", "") or "",
        linha.get("posto_grad", "") or "",
        linha.get("quadro", "") or "",
        linha.get("destino", "") or "",
        linha.get("modalidade", "") or "",
    ]).upper()
    return q in base


def _aplicar_filtros(linhas, filtros):
    resultado = []

    destino = (filtros.get("destino") or "").strip().upper()
    status_macro = (filtros.get("status_macro") or "").strip().upper()
    modalidade = (filtros.get("modalidade") or "").strip().upper()
    situacao_principal = (filtros.get(
        "situacao_principal") or "").strip().upper()
    q = filtros.get("q")
    apenas_intersecao = filtros.get("apenas_intersecao") == "1"
    apenas_defesa_civil = filtros.get("apenas_defesa_civil") == "1"
    somente_ferias = filtros.get("somente_ferias") == "1"
    somente_vencidos = filtros.get("somente_vencidos") == "1"

    for linha in linhas:
        if not _filtro_texto_ok(linha, q):
            continue

        if destino and destino not in (linha.get("destino") or "").upper():
            continue

        if modalidade and modalidade != (linha.get("modalidade") or "").upper():
            continue

        if situacao_principal and situacao_principal != (linha.get("situacao_principal") or "").upper():
            continue

        if status_macro and status_macro != (linha.get("status_macro") or "").upper():
            continue

        if apenas_intersecao and not linha["na_intersecao"]:
            continue

        if apenas_defesa_civil and "DEFESA CIVIL" not in (linha.get("destino") or "").upper():
            continue

        if somente_ferias and not linha["em_ferias"]:
            continue

        if somente_vencidos:
            vencido = any([
                linha["agregado_info"]["status"] == "VENCIDO",
                linha["disposicao_info"]["status"] == "VENCIDO",
                linha["le_info"]["status"] == "VENCIDO",
                linha["lts_info"]["status"] == "VENCIDO",
            ])
            if not vencido:
                continue

        resultado.append(linha)

    return resultado


def montar_mapa_funcional(data_inicio=None, data_fim=None, filtros=None):
    hoje = date.today()

    militares = (
        Militar.query
        .filter(Militar.inativo.is_(False))
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    agregados = MilitaresAgregados.query.all()
    disposicoes = MilitaresADisposicao.query.all()
    les = LicencaEspecial.query.all()
    ltss = LicencaParaTratamentoDeSaude.query.all()
    pafs = Paf.query.all()

    agregados_por_militar = defaultdict(list)
    for reg in agregados:
        agregados_por_militar[reg.militar_id].append(reg)

    disposicoes_por_militar = defaultdict(list)
    for reg in disposicoes:
        disposicoes_por_militar[reg.militar_id].append(reg)

    les_por_militar = defaultdict(list)
    for reg in les:
        les_por_militar[reg.militar_id].append(reg)

    ltss_por_militar = defaultdict(list)
    for reg in ltss:
        ltss_por_militar[reg.militar_id].append(reg)

    paf_por_militar = {}
    for paf in pafs:
        paf_por_militar[paf.militar_id] = paf

    linhas = []

    for militar in militares:
        agregado = _escolher_vigente_ou_recente(
            agregados_por_militar.get(militar.id, []),
            "inicio_periodo",
            "fim_periodo_agregacao",
            hoje
        )

        disposicao = _escolher_vigente_ou_recente(
            disposicoes_por_militar.get(militar.id, []),
            "inicio_periodo",
            "fim_periodo_disposicao",
            hoje
        )

        le = _escolher_vigente_ou_recente(
            les_por_militar.get(militar.id, []),
            "inicio_periodo_le",
            "fim_periodo_le",
            hoje
        )

        lts = _escolher_vigente_ou_recente(
            ltss_por_militar.get(militar.id, []),
            "inicio_periodo_lts",
            "fim_periodo_lts",
            hoje
        )

        agregado_info = _registro_info(
            agregado, "inicio_periodo", "fim_periodo_agregacao", hoje)
        disposicao_info = _registro_info(
            disposicao, "inicio_periodo", "fim_periodo_disposicao", hoje)
        le_info = _registro_info(
            le, "inicio_periodo_le", "fim_periodo_le", hoje)
        lts_info = _registro_info(
            lts, "inicio_periodo_lts", "fim_periodo_lts", hoje)

        em_ferias = _militar_em_ferias(
            paf_por_militar.get(militar.id),
            data_inicio,
            data_fim
        )

        linha = {
            "militar_id": militar.id,
            "nome": militar.nome_completo,
            "matricula": militar.matricula,
            "posto_grad": militar.posto_grad.sigla if militar.posto_grad else "",
            "quadro": militar.quadro.quadro if militar.quadro else "",
            "situacao_principal": militar.pronto or "PRONTO",
            "modalidade": militar.situacao.condicao if militar.situacao else "",
            "destino": _obter_destino_nome(militar, agregado, disposicao, le, lts),

            "agregado": agregado,
            "disposicao": disposicao,
            "licenca_especial": le,
            "lts": lts,

            "agregado_info": agregado_info,
            "disposicao_info": disposicao_info,
            "le_info": le_info,
            "lts_info": lts_info,

            "esta_agregado": agregado is not None,
            "esta_disposicao": disposicao is not None,
            "esta_le": le is not None,
            "esta_lts": lts is not None,

            "na_intersecao": agregado is not None and disposicao is not None,
            "em_ferias": em_ferias,
        }

        linha["status_macro"] = _status_macro(linha)
        linha["status_resumido"] = _gerar_status_resumido(
            agregado_info,
            disposicao_info,
            le_info,
            lts_info
        )

        linhas.append(linha)

    if filtros:
        linhas = _aplicar_filtros(linhas, filtros)

    return linhas


def gerar_resumo_mapa(linhas):
    destinos_counter = Counter()
    status_counter = Counter()
    posto_counter = Counter()

    agregados_vigentes = 0
    agregados_vencidos = 0
    disposicoes_vigentes = 0
    disposicoes_vencidas = 0
    le_vigentes = 0
    le_vencidas = 0
    lts_vigentes = 0
    lts_vencidas = 0

    for x in linhas:
        destinos_counter[x["destino"] or "NÃO INFORMADO"] += 1
        status_counter[x["status_macro"]] += 1
        posto_counter[x["posto_grad"] or "N/I"] += 1

        if x["agregado_info"]["status"] == "VIGENTE":
            agregados_vigentes += 1
        if x["agregado_info"]["status"] == "VENCIDO":
            agregados_vencidos += 1

        if x["disposicao_info"]["status"] == "VIGENTE":
            disposicoes_vigentes += 1
        if x["disposicao_info"]["status"] == "VENCIDO":
            disposicoes_vencidas += 1

        if x["le_info"]["status"] == "VIGENTE":
            le_vigentes += 1
        if x["le_info"]["status"] == "VENCIDO":
            le_vencidas += 1

        if x["lts_info"]["status"] == "VIGENTE":
            lts_vigentes += 1
        if x["lts_info"]["status"] == "VENCIDO":
            lts_vencidas += 1

    top_destinos = destinos_counter.most_common(8)
    top_postos = posto_counter.most_common(8)

    return {
        "total": len(linhas),
        "agregados": sum(1 for x in linhas if x["esta_agregado"]),
        "disposicao": sum(1 for x in linhas if x["esta_disposicao"]),
        "intersecao": sum(1 for x in linhas if x["na_intersecao"]),
        "le": sum(1 for x in linhas if x["esta_le"]),
        "lts": sum(1 for x in linhas if x["esta_lts"]),
        "ferias": sum(1 for x in linhas if x["em_ferias"]),
        "defesa_civil": sum(
            1 for x in linhas
            if "DEFESA CIVIL" in (x["destino"] or "").upper()
        ),

        "agregados_vigentes": agregados_vigentes,
        "agregados_vencidos": agregados_vencidos,
        "disposicoes_vigentes": disposicoes_vigentes,
        "disposicoes_vencidas": disposicoes_vencidas,
        "le_vigentes": le_vigentes,
        "le_vencidas": le_vencidas,
        "lts_vigentes": lts_vigentes,
        "lts_vencidas": lts_vencidas,

        "destinos_labels": [x[0] for x in top_destinos],
        "destinos_values": [x[1] for x in top_destinos],

        "status_labels": list(status_counter.keys()),
        "status_values": list(status_counter.values()),

        "postos_labels": [x[0] for x in top_postos],
        "postos_values": [x[1] for x in top_postos],
    }
