"""
Consolidação mensal da Junta Médica.

Duas leituras convivem aqui de propósito, porque "quantas licenças teve no
mês" tem dois sentidos e a Junta usa os dois:

  * LANÇADAS no mês  -> o parecer foi emitido naquele mês (produção da Junta).
                        Usa a data da sessão (ou a data de início, nos
                        registros antigos que não têm data de sessão).
  * VIGENTES no mês  -> a licença atravessava aquele mês, mesmo tendo sido
                        lançada antes. Uma LTS de 15/01 a 20/03 conta em
                        janeiro, fevereiro e março.

Os DIAS seguem a segunda leitura, contando só a fatia do período que cai
dentro de cada mês — é o número que responde "quanto de afastamento esse mês
teve de fato".
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from src import database
from src.models import Licencas, LicencaRestricao, Militar
from src.services.junta_medica import (
    _aplicar_filtros_efetivo,
    label_tipo,
)

MESES_PT_CURTO = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Afastamento de fato — é o que entra em "licenças" e o que gera dias.
TIPOS_LICENCA = {"LTS", "LTSPF", "LM"}


def primeiro_dia(ano: int, mes: int) -> date:
    return date(ano, mes, 1)


def ultimo_dia(ano: int, mes: int) -> date:
    return date(ano, mes, monthrange(ano, mes)[1])


def normalizar_competencia(valor: str, padrao: date) -> date:
    """Lê um <input type="month"> ("2026-09") e devolve o 1º dia do mês."""
    valor = (valor or "").strip()

    if valor:
        try:
            ano, mes = valor.split("-")[:2]
            return primeiro_dia(int(ano), int(mes))
        except (ValueError, TypeError):
            pass

    return primeiro_dia(padrao.year, padrao.month)


def listar_competencias(inicio: date, fim: date):
    """Sequência de (ano, mes) de `inicio` até `fim`, inclusive."""
    if fim < inicio:
        inicio, fim = fim, inicio

    meses = []
    ano, mes = inicio.year, inicio.month

    # Trava de sanidade: 10 anos de competências já é muito mais do que a
    # tela consegue mostrar, e evita um período absurdo virar loop eterno.
    while (ano, mes) <= (fim.year, fim.month) and len(meses) < 120:
        meses.append((ano, mes))
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1

    return meses


def _data_referencia(reg) -> Optional[date]:
    """Mês em que o parecer foi lançado."""
    return reg.data_sessao or reg.data_inicio


def _dias_no_mes(reg, ini_mes: date, fim_mes: date) -> int:
    """Dias do registro que caem dentro do mês (0 se não encosta no mês)."""
    if not reg.data_inicio or not reg.data_fim:
        return 0

    inicio = max(reg.data_inicio, ini_mes)
    fim = min(reg.data_fim, fim_mes)

    if fim < inicio:
        return 0

    return (fim - inicio).days + 1


def _buscar_registros(inicio: date, fim: date, filtro_quadro_id="",
                      filtro_posto_grad_id="", filtro_obm_id="",
                      militar_id=None, filtro_tipo=""):
    """
    Traz tudo que pode aparecer no período: o que foi lançado dentro dele e
    o que, tendo sido lançado antes, ainda estava vigente durante ele.
    """
    query = (
        Licencas.query
        .join(Militar, Licencas.militar_id == Militar.id)
        .options(
            joinedload(Licencas.militar).joinedload(Militar.posto_grad),
            joinedload(Licencas.militar).joinedload(Militar.quadro),
            joinedload(Licencas.restricoes).joinedload(LicencaRestricao.tipo),
        )
        .filter(
            or_(
                # vigência encosta no período
                database.and_(
                    Licencas.data_inicio <= fim,
                    Licencas.data_fim >= inicio,
                ),
                # ou foi lançado dentro do período
                database.func.coalesce(
                    Licencas.data_sessao, Licencas.data_inicio
                ).between(inicio, fim),
            )
        )
    )

    if militar_id:
        query = query.filter(Licencas.militar_id == int(militar_id))

    if filtro_tipo:
        query = query.filter(Licencas.tipo_licenca == filtro_tipo)

    query = _aplicar_filtros_efetivo(
        query,
        filtro_quadro_id=filtro_quadro_id,
        filtro_posto_grad_id=filtro_posto_grad_id,
        filtro_obm_id=filtro_obm_id,
    )

    return query.order_by(Licencas.data_inicio.asc(), Licencas.id.asc()).all()


def _linha_vazia(ano: int, mes: int):
    return {
        "ano": ano,
        "mes": mes,
        "competencia": f"{mes:02d}/{ano}",
        "rotulo": f"{MESES_PT_CURTO[mes - 1]}/{ano}",
        "rotulo_longo": f"{MESES_PT[mes - 1]} de {ano}",

        "licencas_lancadas": 0,
        "restricoes_lancadas": 0,
        "inspecoes_lancadas": 0,

        "licencas_vigentes": 0,
        "dias_licenca": 0,

        "online": 0,
        "presencial": 0,

        "militares": set(),
        "por_tipo": {},
        "por_restricao": {},
    }


def montar_estatisticas_mensais(inicio: date, fim: date, filtro_quadro_id="",
                                filtro_posto_grad_id="", filtro_obm_id="",
                                militar_id=None, filtro_tipo=""):
    """
    Monta a série mensal do período. `inicio` e `fim` são o 1º dia do mês
    inicial e do mês final.
    """
    competencias = listar_competencias(inicio, fim)

    if not competencias:
        return {"linhas": [], "totais": _totais_vazios(), "tipos": [],
                "restricoes": [], "registros": [],
                "grafico": _montar_dados_grafico([], [], [])}

    ini_periodo = primeiro_dia(*competencias[0])
    fim_periodo = ultimo_dia(*competencias[-1])

    registros = _buscar_registros(
        ini_periodo, fim_periodo,
        filtro_quadro_id=filtro_quadro_id,
        filtro_posto_grad_id=filtro_posto_grad_id,
        filtro_obm_id=filtro_obm_id,
        militar_id=militar_id,
        filtro_tipo=filtro_tipo,
    )

    linhas = {(a, m): _linha_vazia(a, m) for a, m in competencias}

    tipos_vistos = set()
    restricoes_vistas = set()

    for reg in registros:
        ref = _data_referencia(reg)

        # --- o que foi LANÇADO neste mês ---
        if ref and (ref.year, ref.month) in linhas:
            linha = linhas[(ref.year, ref.month)]
            linha["inspecoes_lancadas"] += 1
            linha["militares"].add(reg.militar_id)
            linha["por_tipo"][reg.tipo_licenca] = linha["por_tipo"].get(
                reg.tipo_licenca, 0) + 1
            tipos_vistos.add(reg.tipo_licenca)

            if reg.online:
                linha["online"] += 1
            else:
                linha["presencial"] += 1

            if reg.tipo_licenca in TIPOS_LICENCA:
                linha["licencas_lancadas"] += 1

            for vinculo in reg.restricoes:
                if not vinculo.tipo:
                    continue
                linha["restricoes_lancadas"] += 1
                nome = vinculo.tipo.nome
                linha["por_restricao"][nome] = linha["por_restricao"].get(
                    nome, 0) + 1
                restricoes_vistas.add(nome)

        # --- o que estava VIGENTE em cada mês ---
        if reg.tipo_licenca not in TIPOS_LICENCA:
            continue

        for ano, mes in competencias:
            dias = _dias_no_mes(reg, primeiro_dia(ano, mes),
                                ultimo_dia(ano, mes))
            if dias:
                linhas[(ano, mes)]["licencas_vigentes"] += 1
                linhas[(ano, mes)]["dias_licenca"] += dias

    linhas_ordenadas = [linhas[c] for c in competencias]

    for linha in linhas_ordenadas:
        linha["militares_distintos"] = len(linha["militares"])
        del linha["militares"]

    totais = _consolidar_totais(linhas_ordenadas, registros)

    tipos = sorted(tipos_vistos, key=lambda t: label_tipo(t))
    tipos_com_label = [(t, label_tipo(t)) for t in tipos]
    restricoes = sorted(restricoes_vistas, key=str.lower)

    return {
        "linhas": linhas_ordenadas,
        "totais": totais,
        "tipos": tipos_com_label,
        "restricoes": restricoes,
        "registros": registros,
        "grafico": _montar_dados_grafico(linhas_ordenadas, tipos_com_label, restricoes),
    }


def _totais_vazios():
    return {
        "licencas_lancadas": 0,
        "restricoes_lancadas": 0,
        "inspecoes_lancadas": 0,
        "dias_licenca": 0,
        "militares_distintos": 0,
        "meses_com_licenca": 0,
        "online": 0,
        "presencial": 0,
        "pct_online": 0.0,
        "por_tipo": {},
        "por_restricao": {},
        "media_dias_mes": 0,
    }


def _montar_dados_grafico(linhas, tipos, restricoes):
    """
    Séries já no formato que o Chart.js consome (rótulos + arrays paralelos),
    pra não montar objeto nenhum no template — só `{{ grafico | tojson }}`.
    """
    return {
        "rotulos": [l["rotulo"] for l in linhas],
        "licencas": [l["licencas_lancadas"] for l in linhas],
        "restricoes": [l["restricoes_lancadas"] for l in linhas],
        "inspecoes": [l["inspecoes_lancadas"] for l in linhas],
        "dias": [l["dias_licenca"] for l in linhas],
        "vigentes": [l["licencas_vigentes"] for l in linhas],
        "online": [l["online"] for l in linhas],
        "presencial": [l["presencial"] for l in linhas],
        "por_tipo": {
            label: [l["por_tipo"].get(tipo, 0) for l in linhas]
            for tipo, label in tipos
        },
        "por_restricao_totais": {
            nome: sum(l["por_restricao"].get(nome, 0) for l in linhas)
            for nome in restricoes
        },
    }


def _consolidar_totais(linhas, registros):
    """
    Totais do período. Atenção: `militares_distintos` é contado sobre os
    registros, não somando as linhas — o mesmo militar aparecendo em três
    meses é UM militar no total, não três.
    """
    totais = _totais_vazios()

    for linha in linhas:
        totais["licencas_lancadas"] += linha["licencas_lancadas"]
        totais["restricoes_lancadas"] += linha["restricoes_lancadas"]
        totais["inspecoes_lancadas"] += linha["inspecoes_lancadas"]
        totais["dias_licenca"] += linha["dias_licenca"]
        totais["online"] += linha["online"]
        totais["presencial"] += linha["presencial"]

        if linha["licencas_vigentes"]:
            totais["meses_com_licenca"] += 1

        for tipo, qtd in linha["por_tipo"].items():
            totais["por_tipo"][tipo] = totais["por_tipo"].get(tipo, 0) + qtd

        for nome, qtd in linha["por_restricao"].items():
            totais["por_restricao"][nome] = totais["por_restricao"].get(
                nome, 0) + qtd

    totais["militares_distintos"] = len({r.militar_id for r in registros})

    if linhas:
        totais["media_dias_mes"] = round(
            totais["dias_licenca"] / len(linhas), 1)

    total_inspecoes = totais["online"] + totais["presencial"]
    if total_inspecoes:
        totais["pct_online"] = round(
            (totais["online"] * 100.0) / total_inspecoes, 1)

    return totais


def montar_ranking_militares(resultado, limite=25):
    """
    Quem mais apareceu na Junta no período. É o atalho pra sair do panorama
    do mês e cair no militar — cada linha leva pro detalhamento individual.
    """
    por_militar = {}

    for reg in resultado["registros"]:
        ref = _data_referencia(reg)
        dados = por_militar.setdefault(reg.militar_id, {
            "militar": reg.militar,
            "licencas": 0,
            "restricoes": 0,
            "inspecoes": 0,
            "dias": 0,
            "meses": set(),
        })

        dados["inspecoes"] += 1
        dados["restricoes"] += sum(1 for v in reg.restricoes if v.tipo)

        if reg.tipo_licenca in TIPOS_LICENCA:
            dados["licencas"] += 1
            if reg.data_inicio and reg.data_fim:
                dados["dias"] += (reg.data_fim - reg.data_inicio).days + 1

        if ref:
            dados["meses"].add((ref.year, ref.month))

    linhas = []
    for militar_id, dados in por_militar.items():
        dados["militar_id"] = militar_id
        dados["meses_distintos"] = len(dados.pop("meses"))
        linhas.append(dados)

    linhas.sort(key=lambda x: (-x["licencas"], -
                x["restricoes"], -x["dias"]))

    return linhas[:limite]
