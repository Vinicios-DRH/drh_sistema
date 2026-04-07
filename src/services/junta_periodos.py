from collections import defaultdict
from datetime import timedelta

TIPOS_MONITORADOS = {
    "LTS",
    "LTSPF",
    "LM",
    "APTO_RECOM",
    "APTO_RESTR",
}

TIPOS_LABELS = {
    "LTS": "LTS",
    "LTSPF": "LTSPF",
    "LM": "Licença Maternidade",
    "APTO_RECOM": "Apto com Recomendações",
    "APTO_RESTR": "Apto com Restrições",
}

# critério de alerta por duração contínua
LIMITES_ALERTA_DIAS = {
    "LTS": 60,
    "LTSPF": 45,
    "LM": 90,
    "APTO_RECOM": 60,
    "APTO_RESTR": 60,
}


def _meses_abrangidos(data_inicio, data_fim):
    meses = []
    ano = data_inicio.year
    mes = data_inicio.month

    while (ano, mes) <= (data_fim.year, data_fim.month):
        meses.append(f"{mes:02d}/{ano}")
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1

    return meses


def _gerar_motivo_suspeita(tipo_licenca, renovacoes, dias_continuos, meses_abrangidos):
    motivos = []

    if renovacoes >= 2:
        motivos.append(f"{renovacoes} renovações")

    limite = LIMITES_ALERTA_DIAS.get(tipo_licenca)
    if limite and dias_continuos >= limite:
        motivos.append(f"{dias_continuos} dias contínuos")

    if len(meses_abrangidos) >= 3:
        motivos.append(f"{len(meses_abrangidos)} meses abrangidos")

    return ", ".join(motivos)


def montar_blocos_renovacao(registros):
    """
    Recebe registros já ordenados por data_inicio ASC e devolve blocos contínuos.
    Um bloco contínuo = mesmo militar, mesmo tipo, sem quebra relevante.
    """
    if not registros:
        return []

    blocos = []
    bloco_atual = None

    for reg in registros:
        if reg.tipo_licenca not in TIPOS_MONITORADOS:
            continue

        if bloco_atual is None:
            bloco_atual = {
                "militar_id": reg.militar_id,
                "tipo_licenca": reg.tipo_licenca,
                "inicio_bloco": reg.data_inicio,
                "fim_bloco": reg.data_fim,
                "registros": [reg],
            }
            continue

        mesmo_tipo = bloco_atual["tipo_licenca"] == reg.tipo_licenca
        continuidade = reg.data_inicio <= (
            bloco_atual["fim_bloco"] + timedelta(days=1))

        if mesmo_tipo and continuidade:
            bloco_atual["registros"].append(reg)
            if reg.data_fim > bloco_atual["fim_bloco"]:
                bloco_atual["fim_bloco"] = reg.data_fim
        else:
            blocos.append(_finalizar_bloco(bloco_atual))
            bloco_atual = {
                "militar_id": reg.militar_id,
                "tipo_licenca": reg.tipo_licenca,
                "inicio_bloco": reg.data_inicio,
                "fim_bloco": reg.data_fim,
                "registros": [reg],
            }

    if bloco_atual:
        blocos.append(_finalizar_bloco(bloco_atual))

    return blocos


def _finalizar_bloco(bloco):
    registros = bloco["registros"]
    inicio = bloco["inicio_bloco"]
    fim = bloco["fim_bloco"]
    quantidade_registros = len(registros)
    renovacoes = max(0, quantidade_registros - 1)
    dias_continuos = (fim - inicio).days + 1

    datas_renovacao = [r.data_inicio for r in registros[1:]]
    ultima_renovacao = datas_renovacao[-1] if datas_renovacao else None
    meses = _meses_abrangidos(inicio, fim)

    motivo_suspeita = _gerar_motivo_suspeita(
        bloco["tipo_licenca"],
        renovacoes,
        dias_continuos,
        meses
    )

    suspeito = bool(motivo_suspeita)

    return {
        "militar_id": bloco["militar_id"],
        "tipo_licenca": bloco["tipo_licenca"],
        "tipo_label": TIPOS_LABELS.get(bloco["tipo_licenca"], bloco["tipo_licenca"]),
        "inicio_bloco": inicio,
        "fim_bloco": fim,
        "dias_continuos": dias_continuos,
        "quantidade_registros": quantidade_registros,
        "renovacoes": renovacoes,
        "datas_renovacao": datas_renovacao,
        "ultima_renovacao": ultima_renovacao,
        "meses_abrangidos": meses,
        "registros": registros,
        "suspeito": suspeito,
        "motivo_suspeita": motivo_suspeita,
    }


def montar_blocos_por_militar(registros):
    agrupado = defaultdict(list)

    for reg in registros:
        if reg.tipo_licenca in TIPOS_MONITORADOS:
            agrupado[reg.militar_id].append(reg)

    resultado = {}

    for militar_id, regs in agrupado.items():
        regs_ordenados = sorted(regs, key=lambda x: (x.data_inicio, x.id))
        resultado[militar_id] = montar_blocos_renovacao(regs_ordenados)

    return resultado
