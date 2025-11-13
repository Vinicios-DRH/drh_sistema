# utils_paf_auto.py
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func, and_

from src.models import Militar, NovoPaf, PafCapacidade, PafFeriasPlano

# ---- Ajuste aqui se quiser outro range de meses preferenciais para o pagamento
MESES_DEFAULT = list(range(1, 13))          # 1..12
MESES_PRIORITARIOS = list(range(8, 13))     # como no seu editar (Ago..Dez); troque se quiser

def _fim_inclusivo(inicio: date, dias: int) -> date:
    return inicio + timedelta(days=dias - 1)

def _primeiro_dia(ano: int, mes: int) -> date:
    return date(ano, mes, 1)

def _capacidade_por_mes(session, ano: int):
    """
    Retorna dict:
      { mes: {"limite": int, "usado": int, "restante": int} }
    'usado' considera NovoPaf.mes_definido (setado pela DRH).
    """
    caps = {m: {"limite": 0, "usado": 0, "restante": 0} for m in range(1, 13)}

    # limites cadastrados
    for row in session.query(PafCapacidade).filter(PafCapacidade.ano == ano):
        caps[row.mes]["limite"] = row.limite

    # usados (já definidos)
    usados = (
        session.query(NovoPaf.mes_definido, func.count(NovoPaf.id))
        .filter(
            NovoPaf.ano_referencia == ano,
            NovoPaf.mes_definido.isnot(None)
        )
        .group_by(NovoPaf.mes_definido)
        .all()
    )
    for mes, qtd in usados:
        if mes:
            caps[int(mes)]["usado"] = int(qtd)

    # restante
    for m in caps:
        caps[m]["restante"] = max(0, caps[m]["limite"] - caps[m]["usado"])

    return caps

def _tres_melhores_meses(capacidade_dict, preferencia=MESES_PRIORITARIOS):
    """
    Devolve 3 meses para opcao_1/2/3 priorizando:
    - meses com maior 'restante'
    - depois, meses na lista 'preferencia' primeiro
    - depois, mês crescente
    Se faltar capacidade cadastrada (restante==0 em todos), ainda assim devolve 3 meses distintos
    usando a ordem de preferência (para DRH definir depois).
    """
    rows = []
    for m in range(1, 13):
        pref_bonus = 1 if m in preferencia else 0
        rows.append((m, capacidade_dict[m]["restante"], pref_bonus))
    # ordena por: restante desc, pref_bonus desc, mes asc
    rows.sort(key=lambda t: (t[1], t[2], -t[0]), reverse=True)

    meses_cap = [m for (m, rest, _p) in rows if rest > 0]
    if len(meses_cap) < 3:
        # completa com preferidos/distintos
        faltando = 3 - len(meses_cap)
        candidatos = [m for m in preferencia if m not in meses_cap]
        # se ainda faltar, entra meses fora da preferência
        if len(candidatos) < faltando:
            candidatos += [m for m in range(1, 13) if m not in meses_cap and m not in candidatos]
        meses_cap += candidatos[:faltando]

    return meses_cap[:3]

def _propor_plano_30(ano: int, mes_usufruto: int):
    """
    Gera um plano de férias de 30 dias: P1=30, início no 1º dia do mês escolhido, fim calculado.
    """
    inicio = _primeiro_dia(ano, mes_usufruto)
    fim = _fim_inclusivo(inicio, 30)
    # Se quiser garantir que não passa de 31/12 do ano, force ajuste aqui (opcional)
    limite_ano = date(ano, 12, 31)
    if fim > limite_ano:
        # começa no dia para terminar em 31/12
        delta = (fim - limite_ano).days
        inicio = inicio - timedelta(days=delta)
        fim = _fim_inclusivo(inicio, 30)
    return {
        "direito_total_dias": 30,
        "qtd_dias_p1": 30,
        "inicio_p1": inicio,
        "fim_p1": fim,
        "mes_usufruto_p1": mes_usufruto,
        # zera p2/p3
        "qtd_dias_p2": None, "inicio_p2": None, "fim_p2": None, "mes_usufruto_p2": None,
        "qtd_dias_p3": None, "inicio_p3": None, "fim_p3": None, "mes_usufruto_p3": None,
    }

def _militares_sem_envio(session, ano: int):
    """
    Retorna lista de Militar (ou ids) que NÃO possuem nem NovoPaf nem PafFeriasPlano para o ano.
    """
    # subqueries
    sub_paf = session.query(NovoPaf.militar_id).filter(NovoPaf.ano_referencia == ano)
    sub_plano = session.query(PafFeriasPlano.militar_id).filter(PafFeriasPlano.ano_referencia == ano)

    q = (
        session.query(Militar)
        .filter(~Militar.id.in_(sub_paf), ~Militar.id.in_(sub_plano))
        .order_by(Militar.id.asc())
    )
    return q.all()

def montar_propostas(session, ano: int, usuario_id: int):
    """
    Gera as propostas (sem gravar) para todos que não enviaram.
    Retorna lista de dicts por militar:
      {
        "militar": Militar,
        "meses_pagamento": [m1, m2, m3],
        "plano": {dict com campos do PafFeriasPlano},
      }
    """
    pendentes = _militares_sem_envio(session, ano)
    caps = _capacidade_por_mes(session, ano)

    propostas = []
    for mil in pendentes:
        m1, m2, m3 = _tres_melhores_meses(caps, MESES_PRIORITARIOS)
        plano = _propor_plano_30(ano, mes_usufruto=m1)
        propostas.append({
            "militar": mil,
            "meses_pagamento": [m1, m2, m3],
            "plano": plano,
        })
        # NÃO decremento capacidade aqui, pois só conta mes_definido.
        # (Se você quiser “reservar” para a próxima escolha, pode decrementar caps[m1]["restante"] -= 1 etc.)
    return propostas

def aplicar_propostas(session, ano: int, usuario_id: int, propostas):
    """
    Persiste as propostas. Ignora com segurança quem ganhou registro nesse meio tempo.
    """
    aplicados = 0
    for item in propostas:
        mil = item["militar"]
        # Skip se alguém criou no meio tempo
        existe_paf = session.query(NovoPaf.id).filter_by(militar_id=mil.id, ano_referencia=ano).first()
        existe_plano = session.query(PafFeriasPlano.id).filter_by(militar_id=mil.id, ano_referencia=ano).first()
        if existe_paf or existe_plano:
            continue

        m1, m2, m3 = item["meses_pagamento"]
        plano = item["plano"]

        novo = NovoPaf(
            militar_id=mil.id,
            ano_referencia=ano,
            opcao_1=m1, opcao_2=m2, opcao_3=m3,
            status="enviado",
            justificativa=None,
            mes_definido=None,  # DRH define depois
            recebido_por_user_id=None,
            recebido_em=None,
            aprovado_por_user_id=None,
            aprovado_em=None,
            validado_por_user_id=None,
            validado_em=None,
            observacoes=None,
        )
        session.add(novo)

        p = PafFeriasPlano(
            militar_id=mil.id,
            usuario_id=usuario_id,
            ano_referencia=ano,
            direito_total_dias=plano["direito_total_dias"],
            qtd_dias_p1=plano["qtd_dias_p1"],
            inicio_p1=plano["inicio_p1"],
            fim_p1=plano["fim_p1"],
            mes_usufruto_p1=plano["mes_usufruto_p1"],
            qtd_dias_p2=plano["qtd_dias_p2"],
            inicio_p2=plano["inicio_p2"],
            fim_p2=plano["fim_p2"],
            mes_usufruto_p2=plano["mes_usufruto_p2"],
            qtd_dias_p3=plano["qtd_dias_p3"],
            inicio_p3=plano["inicio_p3"],
            fim_p3=plano["fim_p3"],
            mes_usufruto_p3=plano["mes_usufruto_p3"],
            status="enviado",
        )
        session.add(p)
        aplicados += 1

    session.commit()
    return aplicados
