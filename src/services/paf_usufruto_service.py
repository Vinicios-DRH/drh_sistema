"""Serviço de Solicitação e Validação das Datas de Usufruto do PAF.

Responsável por:
1. Garantir as colunas de auditoria/indeferimento em `paf_ferias_plano`.
2. Validar rigorosamente as regras de negócio de usufruto para o ano seguinte:
   - Militares de 30 dias: combinações 30, 15-15, 10-20, 20-10 ou 10-10-10.
   - Militares de 40 dias (raio-X): obrigatoriamente 20-20 com intervalo de 6 meses.
   - Datas estritamente entre 01/01/<ano> e 31/12/<ano> (sem ultrapassar 31/12).
   - Ordem cronológica estrita entre os períodos:
     1º período < 2º período < 3º período (sem sobreposição e sem inversão).
3. Fluxo de validação pela chefia:
   - Aprovação (sincronizando também na tabela `paf` da OBM) ou Indeferimento com motivo.
   - Reenvio pelo militar quando indeferido (ou enquanto pendente).
   - Estatísticas e dados de gráficos de meses de maior concentração de férias do efetivo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, case, func, inspect, or_, text

from src import database
from src.authz import is_super
from src.decorators.control import obms_permitidas_para_usuario
from src.models import (
    Militar,
    MilitarObmFuncao,
    NovoPaf,
    Obm,
    Paf,
    PafFeriasPlano,
    PostoGrad,
    User,
    now_manaus_naive,
)
from src.services.paf_service import (
    MILITARES_40_DIAS_IDS,
    calcular_direito_dias_ferias,
    pode_homologar_paf,
)

MANAUS_TZ = ZoneInfo("America/Manaus")

MESES_NOMES = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

MODALIDADES_30_DIAS = {
    "30": [30],
    "15-15": [15, 15],
    "10-20": [10, 20],
    "20-10": [20, 10],
    "10-10-10": [10, 10, 10],
}

MODALIDADE_40_DIAS = {
    "20-20": [20, 20],
}

STATUS_PENDENTES_CHEFIA = {"pendente", "enviado", "aguardando", "em_analise"}
STATUS_APROVADOS_CHEFIA = {"aprovado_chefe", "aprovado", "validado"}
STATUS_INDEFERIDOS_CHEFIA = {"indeferido", "indeferido_chefe", "reprovado_chefe"}

_colunas_verificadas = False


def ano_usufruto_padrao() -> int:
    return datetime.now(MANAUS_TZ).year + 1


def garantir_colunas_paf_ferias_plano() -> None:
    """Adiciona colunas de aprovação/indeferimento da chefia em `paf_ferias_plano`
    caso ainda não existam no banco MySQL."""
    global _colunas_verificadas
    if _colunas_verificadas:
        return

    try:
        insp = inspect(database.engine)
        if not insp.has_table("paf_ferias_plano"):
            PafFeriasPlano.__table__.create(bind=database.engine, checkfirst=True)
            _colunas_verificadas = True
            return

        cols_atuais = {c["name"].lower() for c in insp.get_columns("paf_ferias_plano")}
        alteracoes = []
        if "motivo_indeferimento" not in cols_atuais:
            alteracoes.append("ADD COLUMN motivo_indeferimento TEXT NULL")
        if "observacao_militar" not in cols_atuais:
            alteracoes.append("ADD COLUMN observacao_militar TEXT NULL")
        if "avaliado_por_user_id" not in cols_atuais:
            alteracoes.append("ADD COLUMN avaliado_por_user_id INT NULL")
        if "avaliado_em" not in cols_atuais:
            alteracoes.append("ADD COLUMN avaliado_em DATETIME NULL")

        for sql_add in alteracoes:
            database.session.execute(text(f"ALTER TABLE paf_ferias_plano {sql_add}"))
        if alteracoes:
            database.session.commit()
    except Exception:
        database.session.rollback()
    finally:
        _colunas_verificadas = True


def _parse_iso_date(val: str | date | None) -> date | None:
    if isinstance(val, date):
        return val
    s = (str(val or "")).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def detectar_modalidade_plano(plano: PafFeriasPlano | None, direito_dias: int) -> str:
    if direito_dias == 40:
        return "20-20"
    if not plano:
        return "30"
    partes = [
        int(q)
        for q in (plano.qtd_dias_p1, plano.qtd_dias_p2, plano.qtd_dias_p3)
        if q and int(q) > 0
    ]
    chave = "-".join(str(p) for p in partes)
    if chave in MODALIDADES_30_DIAS:
        return chave
    return "30"


def obter_paf_e_plano_do_militar(militar_id: int, ano: int | None = None):
    garantir_colunas_paf_ferias_plano()
    ano = ano or ano_usufruto_padrao()

    novo_paf = (
        NovoPaf.query.filter_by(militar_id=militar_id, ano_referencia=ano)
        .order_by(NovoPaf.id.desc())
        .first()
    )
    plano = (
        PafFeriasPlano.query.filter_by(militar_id=militar_id, ano_referencia=ano)
        .order_by(PafFeriasPlano.id.desc())
        .first()
    )
    return novo_paf, plano


def militar_pode_editar_plano(plano: PafFeriasPlano | None) -> bool:
    """O militar pode enviar se ainda não tiver plano, se estiver pendente de
    avaliação da chefia, ou se tiver sido indeferido pela chefia (para corrigir)."""
    if plano is None:
        return True
    st = (plano.status or "pendente").strip().lower()
    return st not in STATUS_APROVADOS_CHEFIA


def validar_e_salvar_plano_usufruto(
    *,
    militar: Militar,
    usuario_id: int,
    ano: int,
    modalidade: str,
    periodos_input: list[dict],
    observacao_militar: str | None = None,
) -> PafFeriasPlano:
    """Valida todas as regras de fracionamento, limites do ano e ordem
    cronológica estrita e cria/atualiza o registro em `PafFeriasPlano`."""
    garantir_colunas_paf_ferias_plano()

    direito = calcular_direito_dias_ferias(militar)
    _, plano_existente = obter_paf_e_plano_do_militar(militar.id, ano)

    if plano_existente and not militar_pode_editar_plano(plano_existente):
        raise ValueError(
            "Suas datas de usufruto já foram validadas pela chefia e não podem ser alteradas diretamente."
        )

    modalidade = (modalidade or "").strip()
    if direito == 40:
        modalidade = "20-20"
        esperado = [20, 20]
    else:
        if modalidade not in MODALIDADES_30_DIAS:
            # Tenta deduzir pelos dias enviados
            dias_enviados = [int(p.get("qtd_dias") or 0) for p in periodos_input if int(p.get("qtd_dias") or 0) > 0]
            chave_deduzida = "-".join(str(d) for d in dias_enviados)
            if chave_deduzida in MODALIDADES_30_DIAS:
                modalidade = chave_deduzida
            else:
                raise ValueError(
                    "Selecione uma forma válida de parcelamento para 30 dias: "
                    "30 dias, 15 + 15, 10 + 20, 20 + 10 ou 10 + 10 + 10."
                )
        esperado = MODALIDADES_30_DIAS[modalidade]

    qtd_periodos_ativos = len(esperado)
    if len(periodos_input) < qtd_periodos_ativos:
        raise ValueError(f"Preencha todos os {qtd_periodos_ativos} período(s) da modalidade {modalidade}.")

    limite_inicio_ano = date(ano, 1, 1)
    limite_fim_ano = date(ano, 12, 31)

    periodos_validados = []
    for idx in range(qtd_periodos_ativos):
        num = idx + 1
        qtd_esperada = esperado[idx]
        dados_p = periodos_input[idx] or {}

        qtd_informada = int(dados_p.get("qtd_dias") or qtd_esperada)
        if qtd_informada != qtd_esperada:
            raise ValueError(
                f"No {num}º período a quantidade de dias deve ser {qtd_esperada} dias (modalidade {modalidade})."
            )

        inicio = _parse_iso_date(dados_p.get("inicio"))
        if not inicio:
            raise ValueError(f"Informe uma data de início válida para o {num}º período.")

        mes_informado = int(dados_p.get("mes_usufruto") or inicio.month)
        if mes_informado < 1 or mes_informado > 12:
            raise ValueError(f"Selecione um mês de usufruto válido (Janeiro a Dezembro) no {num}º período.")

        if inicio.year != ano:
            raise ValueError(
                f"O {num}º período deve começar dentro do ano de {ano} (entre 01/01/{ano} e 31/12/{ano})."
            )

        if inicio.month != mes_informado:
            raise ValueError(
                f"No {num}º período, a data de início ({inicio.strftime('%d/%m/%Y')}) "
                f"deve pertencer ao mês de usufruto selecionado ({MESES_NOMES[mes_informado]})."
            )

        fim = inicio + timedelta(days=qtd_informada - 1)
        if inicio < limite_inicio_ano or fim > limite_fim_ano:
            raise ValueError(
                f"O {num}º período ({inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}) "
                f"ultrapassa o limite de 31/12/{ano}. Todas as férias devem ser usufruídas até 31/12/{ano}."
            )

        periodos_validados.append(
            {
                "numero": num,
                "qtd_dias": qtd_informada,
                "inicio": inicio,
                "fim": fim,
                "mes_usufruto": mes_informado,
            }
        )

    # Soma total de dias
    soma_dias = sum(p["qtd_dias"] for p in periodos_validados)
    if soma_dias != direito:
        raise ValueError(
            f"A soma dos períodos ({soma_dias} dias) deve ser exatamente igual ao seu direito de férias ({direito} dias)."
        )

    # Ordem cronológica estrita entre os períodos:
    # 1º período não pode ser depois do 2º; 2º não pode ser antes (ou durante) o 1º;
    # 2º não pode ser depois do 3º; 3º não pode ser antes (ou durante) o 1º ou 2º.
    if len(periodos_validados) >= 2:
        p1, p2 = periodos_validados[0], periodos_validados[1]
        if p2["inicio"] <= p1["inicio"]:
            raise ValueError(
                "O 2º período não pode começar antes ou no mesmo dia do 1º período."
            )
        if p2["inicio"] <= p1["fim"]:
            raise ValueError(
                f"O 2º período ({p2['inicio'].strftime('%d/%m/%Y')}) deve começar após o término do 1º período "
                f"({p1['fim'].strftime('%d/%m/%Y')})."
            )

    if len(periodos_validados) == 3:
        p1, p2, p3 = periodos_validados[0], periodos_validados[1], periodos_validados[2]
        if p3["inicio"] <= p2["inicio"] or p3["inicio"] <= p1["inicio"]:
            raise ValueError(
                "O 3º período não pode começar antes de nenhum dos períodos anteriores."
            )
        if p3["inicio"] <= p2["fim"]:
            raise ValueError(
                f"O 3º período ({p3['inicio'].strftime('%d/%m/%Y')}) deve começar após o término do 2º período "
                f"({p2['fim'].strftime('%d/%m/%Y')})."
            )

    # Regra específica de 40 dias: 2 períodos de 20 dias com espaço de 6 meses
    if direito == 40:
        p1, p2 = periodos_validados[0], periodos_validados[1]
        min_inicio_p2 = p1["inicio"] + relativedelta(months=6)
        if p2["inicio"] < min_inicio_p2:
            raise ValueError(
                f"Para militares com direito a 40 dias de férias (20 + 20 dias), é obrigatório "
                f"respeitar o intervalo de 6 meses entre os períodos (o 2º período deve iniciar a partir de "
                f"{min_inicio_p2.strftime('%d/%m/%Y')})."
            )

    agora = now_manaus_naive()
    if not plano_existente:
        plano = PafFeriasPlano(
            militar_id=militar.id,
            usuario_id=usuario_id,
            ano_referencia=ano,
            direito_total_dias=direito,
            created_at=agora,
        )
        database.session.add(plano)
    else:
        plano = plano_existente
        plano.usuario_id = usuario_id
        plano.direito_total_dias = direito

    p1 = periodos_validados[0]
    p2 = periodos_validados[1] if len(periodos_validados) >= 2 else None
    p3 = periodos_validados[2] if len(periodos_validados) == 3 else None

    plano.qtd_dias_p1 = p1["qtd_dias"]
    plano.inicio_p1 = p1["inicio"]
    plano.fim_p1 = p1["fim"]
    plano.mes_usufruto_p1 = p1["mes_usufruto"]

    plano.qtd_dias_p2 = p2["qtd_dias"] if p2 else None
    plano.inicio_p2 = p2["inicio"] if p2 else None
    plano.fim_p2 = p2["fim"] if p2 else None
    plano.mes_usufruto_p2 = p2["mes_usufruto"] if p2 else None

    plano.qtd_dias_p3 = p3["qtd_dias"] if p3 else None
    plano.inicio_p3 = p3["inicio"] if p3 else None
    plano.fim_p3 = p3["fim"] if p3 else None
    plano.mes_usufruto_p3 = p3["mes_usufruto"] if p3 else None

    plano.observacao_militar = (observacao_militar or "").strip() or None
    plano.status = "pendente"
    plano.motivo_indeferimento = None
    plano.avaliado_por_user_id = None
    plano.avaliado_em = None
    plano.updated_at = agora

    database.session.commit()
    return plano


# ---------------------------------------------------------------------------
# Permissão e Escopo da Chefia para Validação de Usufruto
# ---------------------------------------------------------------------------

def usuario_eh_chefe_ou_gestor_paf(user: User | None = None) -> bool:
    user = user or getattr(database, "_current_user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_super() or pode_homologar_paf(user):
        return True
    func_id = int(getattr(user, "funcao_user_id", 0) or 0)
    if func_id in {1, 2, 5, 6, 7, 13}:
        return True
    ocupacao = (getattr(getattr(user, "funcao_user", None), "ocupacao", "") or "").upper()
    if any(t in ocupacao for t in ("CHEFE", "DIRETOR", "COMANDANTE", "CMT", "DRH", "SUPER")):
        return True
    return len(obms_permitidas_para_usuario(user)) > 0 and func_id != 12


def listar_obms_chefia_usufruto(user: User) -> list[Obm]:
    if is_super() or pode_homologar_paf(user):
        return Obm.query.order_by(Obm.sigla.asc()).all()
    ids = set(obms_permitidas_para_usuario(user) or [])
    for attr in ("obm_id_1", "obm_id_2"):
        val = getattr(user, attr, None)
        if val:
            ids.add(int(val))
    if not ids:
        return []
    return Obm.query.filter(Obm.id.in_(sorted(ids))).order_by(Obm.sigla.asc()).all()


def chefe_tem_escopo_sobre_militar(user: User, militar_id: int) -> bool:
    if is_super() or pode_homologar_paf(user):
        return True
    obms = {o.id for o in listar_obms_chefia_usufruto(user)}
    if not obms:
        return False
    vinc = (
        database.session.query(MilitarObmFuncao.id)
        .filter(
            MilitarObmFuncao.militar_id == militar_id,
            MilitarObmFuncao.obm_id.in_(obms),
            MilitarObmFuncao.data_fim.is_(None),
        )
        .first()
    )
    return vinc is not None


def _sincronizar_plano_aprovado_em_paf(plano: PafFeriasPlano, avaliador_user_id: int) -> None:
    """Quando o chefe aprova o PafFeriasPlano do militar, sincroniza as datas
    aprovadas na tabela `paf` do mesmo ano de referência."""
    paf_row = Paf.query.filter_by(
        militar_id=plano.militar_id,
        ano_referencia=plano.ano_referencia,
    ).first()
    if not paf_row:
        paf_row = Paf(
            militar_id=plano.militar_id,
            ano_referencia=plano.ano_referencia,
        )
        database.session.add(paf_row)

    mes_num = plano.mes_usufruto_p1 or (plano.inicio_p1.month if plano.inicio_p1 else None)
    paf_row.mes_usufruto = MESES_NOMES[mes_num] if (mes_num and 1 <= mes_num <= 12) else None

    paf_row.qtd_dias_primeiro_periodo = plano.qtd_dias_p1
    paf_row.primeiro_periodo_ferias = plano.inicio_p1
    paf_row.fim_primeiro_periodo = plano.fim_p1

    paf_row.qtd_dias_segundo_periodo = plano.qtd_dias_p2
    paf_row.segundo_periodo_ferias = plano.inicio_p2
    paf_row.fim_segundo_periodo = plano.fim_p2

    paf_row.qtd_dias_terceiro_periodo = plano.qtd_dias_p3
    paf_row.terceiro_periodo_ferias = plano.inicio_p3
    paf_row.fim_terceiro_periodo = plano.fim_p3

    paf_row.usuario_id = avaliador_user_id
    paf_row.data_alteracao = now_manaus_naive()


def avaliar_plano_usufruto_chefia(
    *,
    plano_id: int,
    chefe_user: User,
    acao: str,
    motivo: str | None = None,
) -> PafFeriasPlano:
    """Valida (aprova) ou indefere a solicitação de datas de usufruto de um militar."""
    garantir_colunas_paf_ferias_plano()
    plano = database.session.get(PafFeriasPlano, plano_id)
    if not plano:
        raise ValueError("Solicitação de usufruto não encontrada.")

    if not chefe_tem_escopo_sobre_militar(chefe_user, plano.militar_id):
        raise PermissionError("Você não tem permissão para avaliar militares fora da sua OBM.")

    acao = (acao or "").strip().lower()
    agora = now_manaus_naive()

    if acao in ("aprovar", "validar"):
        plano.status = "aprovado_chefe"
        plano.motivo_indeferimento = None
        plano.avaliado_por_user_id = chefe_user.id
        plano.avaliado_em = agora
        plano.updated_at = agora
        _sincronizar_plano_aprovado_em_paf(plano, chefe_user.id)
    elif acao in ("indeferir", "reprovar"):
        motivo_limpo = (motivo or "").strip()
        if not motivo_limpo:
            raise ValueError("Informe o motivo do indeferimento para que o militar possa ajustar as datas.")
        plano.status = "indeferido"
        plano.motivo_indeferimento = motivo_limpo
        plano.avaliado_por_user_id = chefe_user.id
        plano.avaliado_em = agora
        plano.updated_at = agora
    else:
        raise ValueError("Ação de avaliação inválida.")

    database.session.commit()
    return plano


def consultar_painel_chefia_usufruto(
    *,
    user: User,
    ano: int,
    obm_id_filtro: int | None = None,
    status_filtro: str = "todos",
    busca: str = "",
) -> dict:
    """Retorna a lista de militares do efetivo da chefia, seus status de
    solicitação de usufruto, KPIs e dados para os gráficos mensais de férias."""
    garantir_colunas_paf_ferias_plano()

    obms_disponiveis = listar_obms_chefia_usufruto(user)
    obm_ids_escopo = {o.id for o in obms_disponiveis}

    if obm_id_filtro and obm_id_filtro in obm_ids_escopo:
        obm_ids_ativos = {obm_id_filtro}
    else:
        obm_ids_ativos = obm_ids_escopo

    if not obm_ids_ativos:
        return {
            "ano": ano,
            "obms_disponiveis": [],
            "itens": [],
            "kpi": {"total_efetivo": 0, "pendentes": 0, "aprovados": 0, "indeferidos": 0, "nao_enviaram": 0},
            "grafico_meses": [
                {"mes_num": m, "mes_nome": MESES_NOMES[m], "mes_curto": MESES_NOMES[m][:3],
                 "total_periodos": 0, "aprovados": 0, "pendentes": 0, "militares_distintos": 0, "nomes": []}
                for m in range(1, 13)
            ],
        }

    # Militares ativos lotados nas OBMs selecionadas
    vinculos = (
        database.session.query(Militar, PostoGrad.sigla.label("pg_sigla"), Obm.id.label("obm_id"), Obm.sigla.label("obm_sigla"))
        .join(MilitarObmFuncao, and_(MilitarObmFuncao.militar_id == Militar.id, MilitarObmFuncao.data_fim.is_(None)))
        .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .filter(
            Militar.inativo.is_(False),
            MilitarObmFuncao.obm_id.in_(obm_ids_ativos),
        )
        .order_by(PostoGrad.id.asc(), Militar.nome_completo.asc())
        .all()
    )

    militares_map: dict[int, dict] = {}
    for m, pg_sigla, oid, osigla in vinculos:
        if m.id not in militares_map:
            militares_map[m.id] = {
                "militar": m,
                "pg_sigla": pg_sigla or "—",
                "obm_id": oid,
                "obm_siglas": [osigla],
            }
        else:
            if osigla not in militares_map[m.id]["obm_siglas"]:
                militares_map[m.id]["obm_siglas"].append(osigla)

    militar_ids = list(militares_map.keys())

    # Busca NovoPaf (mês de pagamento) e PafFeriasPlano (datas de usufruto) do ano
    novos_pafs = (
        NovoPaf.query.filter(
            NovoPaf.ano_referencia == ano,
            NovoPaf.militar_id.in_(militar_ids),
        )
        .order_by(NovoPaf.id.asc())
        .all()
        if militar_ids
        else []
    )
    novo_paf_por_mil = {np.militar_id: np for np in novos_pafs}

    planos = (
        PafFeriasPlano.query.filter(
            PafFeriasPlano.ano_referencia == ano,
            PafFeriasPlano.militar_id.in_(militar_ids),
        )
        .order_by(PafFeriasPlano.id.asc())
        .all()
        if militar_ids
        else []
    )
    plano_por_mil = {pl.militar_id: pl for pl in planos}

    kpi = {
        "total_efetivo": len(militar_ids),
        "pendentes": 0,
        "aprovados": 0,
        "indeferidos": 0,
        "nao_enviaram": 0,
    }

    # Estatísticas mensais para o gráfico da chefia (1..12)
    meses_stats = {
        m: {
            "mes_num": m,
            "mes_nome": MESES_NOMES[m],
            "mes_curto": MESES_NOMES[m][:3],
            "total_periodos": 0,
            "aprovados": 0,
            "pendentes": 0,
            "militares_set": set(),
            "nomes": [],
        }
        for m in range(1, 13)
    }

    itens = []
    termo_busca = (busca or "").strip().lower()

    for mid, info in militares_map.items():
        m = info["militar"]
        np = novo_paf_por_mil.get(mid)
        pl = plano_por_mil.get(mid)

        if not pl:
            cat_status = "nao_enviou"
            kpi["nao_enviaram"] += 1
        else:
            st_raw = (pl.status or "pendente").strip().lower()
            if st_raw in STATUS_APROVADOS_CHEFIA:
                cat_status = "aprovado"
                kpi["aprovados"] += 1
            elif st_raw in STATUS_INDEFERIDOS_CHEFIA:
                cat_status = "indeferido"
                kpi["indeferidos"] += 1
            else:
                cat_status = "pendente"
                kpi["pendentes"] += 1

            # Contabiliza no gráfico mensal os períodos solicitados/aprovados (exceto indeferidos)
            if cat_status in ("aprovado", "pendente"):
                for p_num, ini, fim, qtd, mes_u in (
                    (1, pl.inicio_p1, pl.fim_p1, pl.qtd_dias_p1, pl.mes_usufruto_p1),
                    (2, pl.inicio_p2, pl.fim_p2, pl.qtd_dias_p2, pl.mes_usufruto_p2),
                    (3, pl.inicio_p3, pl.fim_p3, pl.qtd_dias_p3, pl.mes_usufruto_p3),
                ):
                    if not ini or not qtd:
                        continue
                    m_idx = int(mes_u or ini.month)
                    if 1 <= m_idx <= 12:
                        meses_stats[m_idx]["total_periodos"] += 1
                        if cat_status == "aprovado":
                            meses_stats[m_idx]["aprovados"] += 1
                        else:
                            meses_stats[m_idx]["pendentes"] += 1
                        meses_stats[m_idx]["militares_set"].add(mid)
                        resumo_militar = (
                            f"{info['pg_sigla']} {m.nome_guerra or m.nome_completo} "
                            f"({p_num}º Per.: {ini.strftime('%d/%m')} a {fim.strftime('%d/%m') if fim else ''} - {qtd}d)"
                        )
                        meses_stats[m_idx]["nomes"].append(resumo_militar)

        # Filtro de status e busca textual
        if status_filtro and status_filtro != "todos" and cat_status != status_filtro:
            continue

        if termo_busca:
            alvo = f"{info['pg_sigla']} {m.nome_completo or ''} {m.nome_guerra or ''} {m.matricula or ''} {' / '.join(info['obm_siglas'])}".lower()
            if termo_busca not in alvo:
                continue

        mes_pag_num = (np.mes_definido or np.opcao_1) if np else None
        mes_pag_nome = MESES_NOMES[mes_pag_num] if (mes_pag_num and 1 <= mes_pag_num <= 12) else "—"
        direito_militar = calcular_direito_dias_ferias(m)

        itens.append(
            {
                "militar": m,
                "pg_sigla": info["pg_sigla"],
                "obm_sigla": " / ".join(info["obm_siglas"]),
                "direito_dias": direito_militar,
                "novo_paf": np,
                "mes_pagamento_nome": mes_pag_nome,
                "mes_pagamento_homologado": bool(np and np.mes_definido),
                "plano": pl,
                "cat_status": cat_status,
                "modalidade": detectar_modalidade_plano(pl, direito_militar) if pl else "—",
            }
        )

    # Ordena: Pendentes de aprovação primeiro, depois Aprovados, Indeferidos e Não Enviaram
    ordem_status = {"pendente": 0, "aprovado": 1, "indeferido": 2, "nao_enviou": 3}
    itens.sort(key=lambda x: (ordem_status.get(x["cat_status"], 9), x["militar"].nome_completo or ""))

    grafico_meses = []
    for m in range(1, 13):
        st = meses_stats[m]
        grafico_meses.append(
            {
                "mes_num": m,
                "mes_nome": st["mes_nome"],
                "mes_curto": st["mes_curto"],
                "total_periodos": st["total_periodos"],
                "aprovados": st["aprovados"],
                "pendentes": st["pendentes"],
                "militares_distintos": len(st["militares_set"]),
                "nomes": st["nomes"],
            }
        )

    return {
        "ano": ano,
        "obms_disponiveis": obms_disponiveis,
        "itens": itens,
        "kpi": kpi,
        "grafico_meses": grafico_meses,
    }
