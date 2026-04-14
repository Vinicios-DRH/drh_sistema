from datetime import date
from collections import defaultdict

from src.models import (
    Militar,
    MilitaresAgregados,
    MilitaresADisposicao,
    LicencaEspecial,
    LicencaParaTratamentoDeSaude,
    Paf,
)


def _registro_vigente(inicio, fim, hoje):
    if not inicio:
        return False
    if inicio > hoje:
        return False
    if fim is None:
        return True
    return fim >= hoje


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


def _gerar_status_resumido(agregado, disposicao, le, lts):
    partes = []

    if agregado:
        partes.append("AGREGADO")
    if disposicao:
        partes.append("À DISPOSIÇÃO")
    if le:
        partes.append("LE")
    if lts:
        partes.append("LTS")

    if partes:
        return " + ".join(partes)

    return "PRONTO"


def montar_mapa_funcional(data_inicio=None, data_fim=None):
    hoje = date.today()

    militares = (
        Militar.query
        .filter(Militar.inativo.is_(False))
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    agregados = (
        MilitaresAgregados.query
        .all()
    )

    disposicoes = (
        MilitaresADisposicao.query
        .all()
    )

    les = (
        LicencaEspecial.query
        .all()
    )

    ltss = (
        LicencaParaTratamentoDeSaude.query
        .all()
    )

    pafs = (
        Paf.query
        .all()
    )

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

            "esta_agregado": agregado is not None,
            "esta_disposicao": disposicao is not None,
            "esta_le": le is not None,
            "esta_lts": lts is not None,

            "na_intersecao": agregado is not None and disposicao is not None,
            "em_ferias": em_ferias,

            "status_resumido": _gerar_status_resumido(agregado, disposicao, le, lts),
        }

        linhas.append(linha)

    return linhas


def gerar_resumo_mapa(linhas):
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
        )
    }
