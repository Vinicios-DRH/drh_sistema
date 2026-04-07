from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from src.models import JuntaFechamentoBg, Licencas, Militar
from sqlalchemy.orm import joinedload


TIPO_LICENCA_LABELS = {
    "LTS": "INCAPAZ TEMPORARIAMENTE PARA SERVIÇO (LTS)",
    "LTSPF": "LICENÇA PARA TRATAMENTO DE SAÚDE PESSOA DA FAMÍLIA",
    "LM": "LICENÇA MATERNIDADE",
    "APTO_RECOM": "APTO COM RECOMENDAÇÕES PARA O SERVIÇO DO CBMAM",
    "APTO_RESTR": "APTO COM RESTRIÇÕES PARA O SERVIÇO DO CBMAM",
    "APTO": "APTO AO SERVIÇO DO CBMAM",
    "CURSO": "CURSO",
    "AGREGADO": "AGREGADO",
}

STATUS_LABELS = {
    "LTS": "LTS - INCAPAZ TEMPORARIAMENTE",
    "LTSPF": "LTSPF",
    "LM": "LICENÇA MATERNIDADE",
    "APTO_RECOM": "APTO COM RECOMENDAÇÕES PARA O SERVIÇO DO CBMAM",
    "APTO_RESTR": "APTO AO SERVIÇO DO CBMAM COM RESTRIÇÕES",
    "APTO": "APTO AO SERVIÇO DO CBMAM",
    "CURSO_APTO": "APTO PARA FINS DE CURSO",
    "CURSO_INAPTO": "INAPTO PARA FINS DE CURSO",
    "AGREGADO": "AGREGADO",
}

LIMITES_AGREGACAO = {
    "LTS": 365,
    "LTSPF": 120,
    "LM": 180,
}

TIPOS_COM_LIMITE = set(LIMITES_AGREGACAO.keys())
TIPOS_DECISAO = {"APTO", "APTO_RECOM", "APTO_RESTR", "AGREGADO"}
TIPOS_IGNORADOS_STATUS_ATUAL = {"CURSO"}


def calcular_data_fim(data_inicio: date, qtd_dias: int) -> date:
    if not data_inicio:
        raise ValueError("Data de início não informada.")
    if not qtd_dias or qtd_dias < 1:
        raise ValueError("Quantidade de dias inválida.")
    return data_inicio + timedelta(days=qtd_dias - 1)


def calcular_status_registro(tipo_licenca: str) -> str:
    if tipo_licenca == "APTO_RECOM":
        return "APTO_RECOM"   # regra da Junta
    if tipo_licenca == "APTO_RESTR":
        return "APTO_RESTR"
    if tipo_licenca == "APTO":
        return "APTO"
    if tipo_licenca == "AGREGADO":
        return "AGREGADO"
    if tipo_licenca == "LTS":
        return "LTS"
    if tipo_licenca == "LTSPF":
        return "LTSPF"
    if tipo_licenca == "LM":
        return "LM"
    return "APTO"


def exige_inspecao_pos_lts(tipo_licenca: str, qtd_dias: int) -> bool:
    return tipo_licenca == "LTS" and qtd_dias >= 90


def label_tipo(tipo: Optional[str]) -> str:
    if not tipo:
        return "-"
    return TIPO_LICENCA_LABELS.get(tipo, tipo)


def label_status(status: Optional[str]) -> str:
    if not status:
        return "-"
    return STATUS_LABELS.get(status, status)


def _filtrar_registros_medicos(registros):
    return [r for r in registros if r.tipo_licenca not in TIPOS_IGNORADOS_STATUS_ATUAL]


def _merge_intervalos(intervalos):
    if not intervalos:
        return []

    ordenados = sorted(intervalos, key=lambda x: x[0])
    mesclados = [list(ordenados[0])]

    for inicio, fim in ordenados[1:]:
        ultimo_inicio, ultimo_fim = mesclados[-1]

        if inicio <= (ultimo_fim + timedelta(days=1)):
            if fim > ultimo_fim:
                mesclados[-1][1] = fim
        else:
            mesclados.append([inicio, fim])

    return [(i, f) for i, f in mesclados]


def _somar_dias_intervalos(intervalos):
    return sum((fim - inicio).days + 1 for inicio, fim in intervalos)


def analisar_agregacao(registros):
    """
    Analisa o bloco contínuo ATUAL do militar.
    Considera apenas o último encadeamento válido.
    Não grava nada no banco. Apenas calcula.
    """
    if not registros:
        return {
            "aplicavel": False,
            "tipo": None,
            "dias_continuos": 0,
            "limite": None,
            "faltam": None,
            "atingiu_limite": False,
            "alerta": False,
            "mensagem": None,
        }

    regs = sorted(registros, key=lambda r: (r.data_inicio, r.id), reverse=True)
    ultimo = regs[0]

    if ultimo.tipo_licenca == "AGREGADO":
        return {
            "aplicavel": True,
            "tipo": "AGREGADO",
            "dias_continuos": None,
            "limite": None,
            "faltam": 0,
            "atingiu_limite": True,
            "alerta": False,
            "mensagem": "Militar já se encontra agregado.",
        }

    if ultimo.tipo_licenca not in TIPOS_COM_LIMITE:
        return {
            "aplicavel": False,
            "tipo": None,
            "dias_continuos": 0,
            "limite": None,
            "faltam": None,
            "atingiu_limite": False,
            "alerta": False,
            "mensagem": None,
        }

    tipo = ultimo.tipo_licenca
    cadeia = [ultimo]
    inicio_cadeia = ultimo.data_inicio

    for reg in regs[1:]:
        if reg.tipo_licenca in TIPOS_DECISAO:
            break

        if reg.tipo_licenca != tipo:
            break

        if reg.data_fim < (inicio_cadeia - timedelta(days=1)):
            break

        cadeia.append(reg)
        if reg.data_inicio < inicio_cadeia:
            inicio_cadeia = reg.data_inicio

    intervalos = _merge_intervalos(
        [(r.data_inicio, r.data_fim) for r in cadeia])
    dias_continuos = _somar_dias_intervalos(intervalos)

    limite = LIMITES_AGREGACAO[tipo]
    faltam = max(0, limite - dias_continuos)

    # Pela tua descrição: "mais de 365 / 120 / 180"
    # Se quiser que agregue no exato limite, troca > por >=
    atingiu_limite = dias_continuos > limite

    alerta = (not atingiu_limite) and (faltam <= 30)

    mensagem = None
    if atingiu_limite:
        mensagem = (
            f"Militar ultrapassou o limite de {limite} dias contínuos de {label_tipo(tipo)} "
            f"({dias_continuos} dias) e entra em condição de agregação."
        )
    elif alerta:
        mensagem = (
            f"Militar está próximo da agregação por {label_tipo(tipo)}: "
            f"{dias_continuos}/{limite} dias contínuos."
        )

    return {
        "aplicavel": True,
        "tipo": tipo,
        "dias_continuos": dias_continuos,
        "limite": limite,
        "faltam": faltam,
        "atingiu_limite": atingiu_limite,
        "alerta": alerta,
        "mensagem": mensagem,
    }


def calcular_status_atual(registros, hoje: Optional[date] = None) -> Optional[str]:
    """
    Calcula a situação atual do militar olhando o histórico completo.
    """
    registros = _filtrar_registros_medicos(registros)
    
    if not registros:
        return None

    hoje = hoje or date.today()
    regs = sorted(registros, key=lambda r: (r.data_inicio, r.id), reverse=True)
    ultimo = regs[0]

    if ultimo.tipo_licenca == "AGREGADO":
        return "AGREGADO"

    agregacao = analisar_agregacao(regs)
    if agregacao["atingiu_limite"]:
        return "AGREGADO"

    if ultimo.tipo_licenca == "APTO_RECOM":
        return "APTO_RECOM"

    if ultimo.tipo_licenca == "APTO_RESTR":
        return "APTO_RESTR"

    if ultimo.tipo_licenca == "APTO":
        return "APTO"

    if hoje <= ultimo.data_fim:
        return ultimo.status

    if exige_inspecao_pos_lts(ultimo.tipo_licenca, ultimo.qtd_dias):
        return "AGUARDANDO_INSPECAO"

    return "APTO"


def calcular_situacao_atual(registros, hoje: Optional[date] = None):
    status = calcular_status_atual(registros, hoje=hoje)
    agregacao = analisar_agregacao(registros)

    return {
        "status_atual": status,
        "status_atual_label": label_status(status),
        "agregacao": agregacao,
    }


def montar_dados_licencas(
    filtro_q="",
    filtro_tipo="",
    filtro_status="",
    filtro_status_atual="",
    filtro_nota_bg=""
):
    query = (
        Licencas.query
        .join(Militar, Licencas.militar_id == Militar.id)
        .outerjoin(JuntaFechamentoBg, Licencas.fechamento_bg_id == JuntaFechamentoBg.id)
        .options(
            joinedload(Licencas.militar).joinedload(Militar.posto_grad),
            joinedload(Licencas.militar).joinedload(Militar.quadro),
            joinedload(Licencas.fechamento_bg),
        )
    )

    if filtro_q:
        query = query.filter(Militar.nome_completo.ilike(f"%{filtro_q}%"))

    if filtro_tipo:
        query = query.filter(Licencas.tipo_licenca == filtro_tipo)

    if filtro_status:
        query = query.filter(Licencas.status == filtro_status)

    if filtro_nota_bg:
        query = query.filter(
            JuntaFechamentoBg.nota_bg.ilike(f"%{filtro_nota_bg}%"))

    registros = query.order_by(
        Licencas.created_at.desc(), Licencas.id.desc()).all()

    militar_ids = list({r.militar_id for r in registros})
    historicos_por_militar = {}

    if militar_ids:
        historicos = (
            Licencas.query
            .filter(Licencas.militar_id.in_(militar_ids))
            .order_by(Licencas.militar_id.asc(), Licencas.data_inicio.desc(), Licencas.id.desc())
            .all()
        )
        for reg in historicos:
            historicos_por_militar.setdefault(reg.militar_id, []).append(reg)

    dados = []
    for reg in registros:
        historico = historicos_por_militar.get(reg.militar_id, [])
        situacao = calcular_situacao_atual(historico)

        if filtro_status_atual and situacao["status_atual"] != filtro_status_atual:
            continue

        dados.append({
            "registro": reg,
            "tipo_label": label_tipo(reg.tipo_licenca),
            "status_label": label_status(reg.status),
            "status_atual": situacao["status_atual"],
            "status_atual_label": situacao["status_atual_label"],
            "agregacao": situacao["agregacao"],
            "nota_bg": reg.fechamento_bg.nota_bg if reg.fechamento_bg else "PENDENTE BG",
        })

    resumo = {
        "total": len(dados),
        "em_licenca": sum(1 for d in dados if d["status_atual"] in {"LTS", "LTSPF", "LM"}),
        "aptos": sum(1 for d in dados if d["status_atual"] == "APTO"),
        "recomendacoes": sum(1 for d in dados if d["status_atual"] == "APTO_RECOM"),
        "restricoes": sum(1 for d in dados if d["status_atual"] == "APTO_RESTR"),
        "agregados": sum(1 for d in dados if d["status_atual"] == "AGREGADO"),
        "aguardando_inspecao": sum(1 for d in dados if d["status_atual"] == "AGUARDANDO_INSPECAO"),
        "alertas_agregacao": sum(1 for d in dados if d["agregacao"]["alerta"]),
        "pendentes_bg": sum(1 for d in dados if d["nota_bg"] == "PENDENTE BG"),
    }

    return dados, resumo
