from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from src.models import (
    JuntaFechamentoBg,
    JuntaRestricaoTipo,
    Licencas,
    LicencaRestricao,
    Militar,
    MilitarObmFuncao,
)
from sqlalchemy.orm import joinedload
from src import database


TIPO_LICENCA_LABELS = {
    "LTS": "INCAPAZ TEMPORARIAMENTE PARA SERVIÇO (LTS)",
    "LTSPF": "LICENÇA PARA TRATAMENTO DE SAÚDE PESSOA DA FAMÍLIA",
    "LM": "LICENÇA MATERNIDADE",
    "APTO_RECOM": "APTO COM RECOMENDAÇÕES PARA O SERVIÇO DO CBMAM",
    "APTO_RESTR": "APTO COM RESTRIÇÕES PARA O SERVIÇO DO CBMAM",
    "APTO": "APTO AO SERVIÇO DO CBMAM",
    "CURSO": "CURSO",
    "TAF": "TAF",
    "PROMOCAO": "PROMOÇÃO",
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
    "CURSO_REGIME_ESPECIAL": "REGIME ESPECIAL PARA FINS DE CURSO",
    "CURSO_INAPTO": "INAPTO PARA FINS DE CURSO",
    "TAF_APTO": "APTO PARA O TAF",
    "TAF_ALTERNATIVO": "TAF ALTERNATIVO",
    "TAF_INAPTO": "INAPTO PARA O TAF",
    "PROMOCAO_APTO": "APTO PARA FINS DE PROMOÇÃO",
    "PROMOCAO_INAPTO": "INAPTO PARA FINS DE PROMOÇÃO",
    "AGREGADO": "AGREGADO",
}

# Tipos de inspeção que não são licença/decisão médica de situação: o parecer
# vale só pro fim específico (curso, TAF, promoção) e por isso não mexe no
# status atual do militar. Cada um tem sua própria lista de resultados.
RESULTADOS_POR_TIPO = {
    "CURSO": [
        ("CURSO_REGIME_ESPECIAL", "REGIME ESPECIAL"),
        ("CURSO_APTO", "APTO"),
        ("CURSO_INAPTO", "INAPTO"),
    ],
    "TAF": [
        ("TAF_APTO", "APTO"),
        ("TAF_ALTERNATIVO", "ALTERNATIVO"),
        ("TAF_INAPTO", "INAPTO"),
    ],
    "PROMOCAO": [
        ("PROMOCAO_APTO", "APTO"),
        ("PROMOCAO_INAPTO", "INAPTO"),
    ],
}

TIPOS_COM_RESULTADO = set(RESULTADOS_POR_TIPO.keys())

# Tipos de inspeção pontuais: sem quantidade de dias e sem período. A data do
# registro é a própria data da sessão da Junta.
TIPOS_PONTUAIS = set(RESULTADOS_POR_TIPO.keys())

# Tipos em que a Junta pode marcar restrições (checkboxes).
TIPOS_COM_RESTRICAO = {"APTO_RESTR", "APTO_RECOM"}

LIMITES_AGREGACAO = {
    "LTS": 365,
    "LTSPF": 120,
    "LM": 180,
}

TIPOS_COM_LIMITE = set(LIMITES_AGREGACAO.keys())
TIPOS_DECISAO = {"APTO", "APTO_RECOM", "APTO_RESTR", "AGREGADO"}
TIPOS_IGNORADOS_STATUS_ATUAL = {"CURSO", "TAF", "PROMOCAO"}


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


def resultados_do_tipo(tipo: Optional[str]):
    """Lista (valor, label) de resultados válidos pro tipo de inspeção."""
    return RESULTADOS_POR_TIPO.get(tipo or "", [])


def resultado_valido(tipo: Optional[str], resultado: Optional[str]) -> bool:
    validos = {v for v, _ in resultados_do_tipo(tipo)}
    return bool(resultado) and resultado in validos


def label_resultado(tipo: Optional[str], resultado: Optional[str]) -> str:
    for valor, texto in resultados_do_tipo(tipo):
        if valor == resultado:
            return texto
    return label_status(resultado)


def listar_tipos_restricao(somente_ativos: bool = True):
    query = JuntaRestricaoTipo.query
    if somente_ativos:
        query = query.filter(JuntaRestricaoTipo.ativo.is_(True))
    return query.order_by(
        JuntaRestricaoTipo.ordem.asc(),
        JuntaRestricaoTipo.nome.asc()
    ).all()


def obter_ou_criar_tipo_restricao(nome: str) -> Optional[JuntaRestricaoTipo]:
    """
    Resolve uma restrição digitada em "Outros". Reaproveita o tipo existente
    (comparando sem diferenciar maiúsculas) em vez de duplicar o catálogo.
    Não faz commit — quem chama controla a transação.
    """
    nome = (nome or "").strip()
    if not nome:
        return None

    existente = (
        JuntaRestricaoTipo.query
        .filter(database.func.lower(JuntaRestricaoTipo.nome) == nome.lower())
        .first()
    )
    if existente:
        return existente

    novo = JuntaRestricaoTipo(nome=nome, ativo=True, ordem=999)
    database.session.add(novo)
    database.session.flush()
    return novo


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


def _militares_da_obm(obm_id):
    """
    Ids dos militares lotados na OBM (vínculo ainda sem data_fim).

    É subquery e não JOIN de propósito: 17 militares têm mais de um vínculo
    ativo, e um join duplicaria os registros deles na listagem. Assim o filtro
    também tem a semântica certa — casa se QUALQUER vínculo ativo for da OBM.
    """
    return (
        database.session.query(MilitarObmFuncao.militar_id)
        .filter(
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id == int(obm_id),
        )
    )


def _aplicar_filtros_efetivo(query, filtro_quadro_id="",
                             filtro_posto_grad_id="", filtro_obm_id=""):
    """Aplica quadro / posto-grad / OBM numa query que já tem Militar joinado."""
    if filtro_quadro_id:
        query = query.filter(Militar.quadro_id == int(filtro_quadro_id))

    if filtro_posto_grad_id:
        query = query.filter(Militar.posto_grad_id == int(filtro_posto_grad_id))

    if filtro_obm_id:
        query = query.filter(Militar.id.in_(_militares_da_obm(filtro_obm_id)))

    return query


def contar_efetivo_ativo(filtro_quadro_id="", filtro_posto_grad_id="",
                         filtro_obm_id="") -> int:
    """
    Efetivo ativo que serve de denominador dos percentuais: militares não
    inativos, recortados pelos mesmos filtros de quadro / posto-grad / OBM
    aplicados à listagem.
    """
    query = (
        database.session.query(
            database.func.count(database.distinct(Militar.id)))
        .select_from(Militar)
        .filter(Militar.inativo.isnot(True))
    )

    query = _aplicar_filtros_efetivo(
        query,
        filtro_quadro_id=filtro_quadro_id,
        filtro_posto_grad_id=filtro_posto_grad_id,
        filtro_obm_id=filtro_obm_id,
    )

    return int(query.scalar() or 0)


def _percentual(quantidade: int, total: int) -> float:
    if not total:
        return 0.0
    return round((quantidade * 100.0) / total, 2)


def montar_dados_licencas(
    filtro_q="",
    filtro_tipo="",
    filtro_status="",
    filtro_status_atual="",
    filtro_nota_bg="",
    filtro_quadro_id="",
    filtro_posto_grad_id="",
    filtro_obm_id="",
    filtro_restricao_id="",
):
    query = (
        Licencas.query
        .join(Militar, Licencas.militar_id == Militar.id)
        .outerjoin(JuntaFechamentoBg, Licencas.fechamento_bg_id == JuntaFechamentoBg.id)
        .options(
            joinedload(Licencas.militar).joinedload(Militar.posto_grad),
            joinedload(Licencas.militar).joinedload(Militar.quadro),
            joinedload(Licencas.fechamento_bg),
            joinedload(Licencas.restricoes).joinedload(LicencaRestricao.tipo),
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

    query = _aplicar_filtros_efetivo(
        query,
        filtro_quadro_id=filtro_quadro_id,
        filtro_posto_grad_id=filtro_posto_grad_id,
        filtro_obm_id=filtro_obm_id,
    )

    if filtro_restricao_id:
        query = query.filter(
            Licencas.id.in_(
                database.session.query(LicencaRestricao.licenca_id)
                .filter(LicencaRestricao.restricao_tipo_id == int(filtro_restricao_id))
            )
        )

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

        restricoes = sorted(
            (r.tipo.nome for r in reg.restricoes if r.tipo),
            key=lambda x: x.lower()
        )

        dados.append({
            "registro": reg,
            "tipo_label": label_tipo(reg.tipo_licenca),
            "status_label": label_status(reg.status),
            "status_atual": situacao["status_atual"],
            "status_atual_label": situacao["status_atual_label"],
            "agregacao": situacao["agregacao"],
            "nota_bg": reg.fechamento_bg.nota_bg if reg.fechamento_bg else "PENDENTE BG",
            "restricoes": restricoes,
            "curso_nome": reg.curso_nome or (reg.curso.nome if reg.curso else None),
        })

    resumo = _montar_resumo(
        dados,
        filtro_quadro_id=filtro_quadro_id,
        filtro_posto_grad_id=filtro_posto_grad_id,
        filtro_obm_id=filtro_obm_id,
    )

    return dados, resumo


def _montar_resumo(dados, filtro_quadro_id="", filtro_posto_grad_id="",
                   filtro_obm_id=""):
    """
    Resumo da listagem. Os contadores continuam existindo (é o que a tela
    sempre mostrou), mas os percentuais são calculados por MILITAR DISTINTO
    sobre o efetivo ativo — senão um militar com 4 renovações de LTS contaria
    4 vezes e o percentual estouraria 100%.
    """
    efetivo_ativo = contar_efetivo_ativo(
        filtro_quadro_id=filtro_quadro_id,
        filtro_posto_grad_id=filtro_posto_grad_id,
        filtro_obm_id=filtro_obm_id,
    )

    militares_por_status = {}
    for item in dados:
        status = item["status_atual"] or "SEM_REGISTRO"
        militares_por_status.setdefault(status, set()).add(
            item["registro"].militar_id)

    def militares(*status_list):
        acumulado = set()
        for status in status_list:
            acumulado |= militares_por_status.get(status, set())
        return acumulado

    em_licenca = militares("LTS", "LTSPF", "LM")
    aptos = militares("APTO")
    recomendacoes = militares("APTO_RECOM")
    restricoes = militares("APTO_RESTR")
    agregados = militares("AGREGADO")
    aguardando = militares("AGUARDANDO_INSPECAO")

    # Percentual por tipo de restrição: militares distintos que carregam
    # aquela restrição dentro do recorte filtrado.
    militares_por_restricao = {}
    for item in dados:
        for nome in item["restricoes"]:
            militares_por_restricao.setdefault(nome, set()).add(
                item["registro"].militar_id)

    restricoes_detalhe = [
        {
            "nome": nome,
            "militares": len(ids),
            "percentual": _percentual(len(ids), efetivo_ativo),
        }
        for nome, ids in militares_por_restricao.items()
    ]
    restricoes_detalhe.sort(key=lambda x: (-x["militares"], x["nome"].lower()))

    # Percentual por tipo de licença/inspeção (pelo tipo do registro).
    militares_por_tipo = {}
    for item in dados:
        militares_por_tipo.setdefault(item["registro"].tipo_licenca, set()).add(
            item["registro"].militar_id)

    licencas_detalhe = [
        {
            "tipo": tipo,
            "label": label_tipo(tipo),
            "militares": len(ids),
            "percentual": _percentual(len(ids), efetivo_ativo),
        }
        for tipo, ids in militares_por_tipo.items()
    ]
    licencas_detalhe.sort(key=lambda x: (-x["militares"], x["label"]))

    return {
        "total": len(dados),
        "militares_distintos": len({d["registro"].militar_id for d in dados}),
        "efetivo_ativo": efetivo_ativo,

        "em_licenca": len(em_licenca),
        "aptos": len(aptos),
        "recomendacoes": len(recomendacoes),
        "restricoes": len(restricoes),
        "agregados": len(agregados),
        "aguardando_inspecao": len(aguardando),

        "pct_em_licenca": _percentual(len(em_licenca), efetivo_ativo),
        "pct_aptos": _percentual(len(aptos), efetivo_ativo),
        "pct_recomendacoes": _percentual(len(recomendacoes), efetivo_ativo),
        "pct_restricoes": _percentual(len(restricoes), efetivo_ativo),
        "pct_agregados": _percentual(len(agregados), efetivo_ativo),
        "pct_aguardando_inspecao": _percentual(len(aguardando), efetivo_ativo),

        "restricoes_detalhe": restricoes_detalhe,
        "licencas_detalhe": licencas_detalhe,

        "alertas_agregacao": sum(1 for d in dados if d["agregacao"]["alerta"]),
        "pendentes_bg": sum(1 for d in dados if d["nota_bg"] == "PENDENTE BG"),
    }
