
from flask import current_app
from zoneinfo import ZoneInfo
from flask import request, current_app
from flask import request, session
from flask_login import current_user
from src import database
from src.models import (DocumentoMilitar, Militar, PostoGrad, Quadro, Obm, MilitarObmFuncao,
                        MilitaresAgregados, MilitaresADisposicao, LicencaEspecial, LicencaParaTratamentoDeSaude)
from src.decorators.control import checar_ocupacao
from datetime import datetime, date, timedelta
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import distinct, func, or_, and_
from decimal import Decimal, ROUND_HALF_UP
import re
from dateutil.relativedelta import relativedelta



MANAUS_TZ = ZoneInfo("America/Manaus")
OBMS_OPERACIONAIS_CAPITAL = [2, 5, 7, 15, 26, 35, 59, 60, 61, 62, 63, 65, 86]
LOCALIDADE_CAPITAL_ID = 1


# def now_manaus_naive() -> datetime:
#     # pega agora em Manaus e remove tzinfo pra armazenar em coluna DateTime (sem timezone)
#     return datetime.now(MANAUS_TZ).replace(tzinfo=None)


def _agora_manaus():
    return datetime.now(MANAUS_TZ)


def _pode_pegar_doc(doc: DocumentoMilitar) -> bool:
    # Só o dono (CPF) ou alguém com poder (se quiser permitir admins):
    if current_user.cpf == doc.destinatario_cpf:
        return True
    # Exemplo: permitir DRH baixar em nome do usuário (opcional)
    try:
        # gambizinha pra reutilizar
        return checar_ocupacao('DRH', 'SUPER USER')(lambda: True)() is True
    except Exception:
        return False


def _somente_numeros(valor):
    return "".join(filter(str.isdigit, str(valor or "")))


def _obms_do_militar_por_vinculos(militar):
    """
    Retorna até 2 OBMs do militar, priorizando:
    1) vínculos ativos (data_fim is None)
    2) mais recentes por data_criacao
    """
    if not militar or not getattr(militar, "obm_funcoes", None):
        return None, None

    vinculos = [v for v in militar.obm_funcoes if v.obm_id]

    if not vinculos:
        return None, None

    def sort_key(v):
        ativo = 1 if v.data_fim is None else 0
        data_ref = v.data_criacao or datetime.min
        return (ativo, data_ref, v.id or 0)

    vinculos.sort(key=sort_key, reverse=True)

    obm_ids = []
    for v in vinculos:
        if v.obm_id not in obm_ids:
            obm_ids.append(v.obm_id)
        if len(obm_ids) == 2:
            break

    obm_id_1 = obm_ids[0] if len(obm_ids) > 0 else None
    obm_id_2 = obm_ids[1] if len(obm_ids) > 1 else None
    return obm_id_1, obm_id_2


def _periodo_vigente_expr(inicio_col, fim_col):
    hoje = date.today()
    return and_(
        inicio_col.isnot(None),
        inicio_col <= hoje,
        or_(
            fim_col.is_(None),
            fim_col >= hoje
        )
    )


def _periodo_incompleto_expr(inicio_col, fim_col):
    return or_(
        inicio_col.is_(None),
        fim_col.is_(None)
    )


def _status_periodo(inicio, fim, termino_label):
    hoje = date.today()

    if not inicio or not fim:
        return 'Dados incompletos'
    if hoje < inicio:
        return 'A iniciar'
    if inicio <= hoje <= fim:
        return 'Vigente'
    return termino_label


def _dias_restantes(fim):
    if not fim:
        return None
    return (fim - date.today()).days


def _preview_licencas_especiais(limit=5):
    itens = (
        LicencaEspecial.query
        .join(Militar, Militar.id == LicencaEspecial.militar_id)
        .options(
            joinedload(LicencaEspecial.militar),
            joinedload(LicencaEspecial.posto_grad),
            joinedload(LicencaEspecial.destino),
        )
        .filter(Militar.inativo.is_(False))
        .filter(_periodo_vigente_expr(
            LicencaEspecial.inicio_periodo_le,
            LicencaEspecial.fim_periodo_le
        ))
        .order_by(LicencaEspecial.fim_periodo_le.asc(), LicencaEspecial.id.desc())
        .limit(limit)
        .all()
    )

    dados = []
    for item in itens:
        dados.append({
            "militar_id": item.militar_id,
            "nome": item.militar.nome_completo if item.militar else "N/A",
            "matricula": item.militar.matricula if item.militar else "N/A",
            "posto_grad": item.posto_grad.sigla if item.posto_grad else "N/A",
            "destino": item.destino.local if item.destino else "N/A",
            "inicio": item.inicio_periodo_le.strftime("%d/%m/%Y") if item.inicio_periodo_le else "N/A",
            "fim": item.fim_periodo_le.strftime("%d/%m/%Y") if item.fim_periodo_le else "N/A",
            "dias_restantes": _dias_restantes(item.fim_periodo_le),
            "status": _status_periodo(
                item.inicio_periodo_le,
                item.fim_periodo_le,
                "Término da Licença Especial"
            )
        })
    return dados


def _preview_lts(limit=5):
    itens = (
        LicencaParaTratamentoDeSaude.query
        .join(Militar, Militar.id == LicencaParaTratamentoDeSaude.militar_id)
        .options(
            joinedload(LicencaParaTratamentoDeSaude.militar),
            joinedload(LicencaParaTratamentoDeSaude.posto_grad),
            joinedload(LicencaParaTratamentoDeSaude.destino),
        )
        .filter(Militar.inativo.is_(False))
        .filter(_periodo_vigente_expr(
            LicencaParaTratamentoDeSaude.inicio_periodo_lts,
            LicencaParaTratamentoDeSaude.fim_periodo_lts
        ))
        .order_by(
            LicencaParaTratamentoDeSaude.fim_periodo_lts.asc(),
            LicencaParaTratamentoDeSaude.id.desc()
        )
        .limit(limit)
        .all()
    )

    dados = []
    for item in itens:
        dados.append({
            "militar_id": item.militar_id,
            "nome": item.militar.nome_completo if item.militar else "N/A",
            "matricula": item.militar.matricula if item.militar else "N/A",
            "posto_grad": item.posto_grad.sigla if item.posto_grad else "N/A",
            "destino": item.destino.local if item.destino else "N/A",
            "inicio": item.inicio_periodo_lts.strftime("%d/%m/%Y") if item.inicio_periodo_lts else "N/A",
            "fim": item.fim_periodo_lts.strftime("%d/%m/%Y") if item.fim_periodo_lts else "N/A",
            "dias_restantes": _dias_restantes(item.fim_periodo_lts),
            "status": _status_periodo(
                item.inicio_periodo_lts,
                item.fim_periodo_lts,
                "Término da Licença para Tratamento de Saúde"
            )
        })
    return dados


def _parse_int(value):
    try:
        return int(value) if value not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _filtros_painel_cbmc():
    posto_grad_id = _parse_int(request.args.get("posto_grad_id"))
    quadro_id = _parse_int(request.args.get("quadro_id"))
    return {
        "posto_grad_id": posto_grad_id,
        "quadro_id": quadro_id,
    }


def _base_query_operacional_capital(filtros=None):
    filtros = filtros or {}

    query = (
        Militar.query
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
        )
    )

    if filtros.get("posto_grad_id"):
        query = query.filter(Militar.posto_grad_id == filtros["posto_grad_id"])

    if filtros.get("quadro_id"):
        query = query.filter(Militar.quadro_id == filtros["quadro_id"])

    return query


def _ids_militares_operacional_capital(filtros=None):
    rows = (
        _base_query_operacional_capital(filtros)
        .with_entities(distinct(Militar.id))
        .all()
    )
    return [r[0] for r in rows]


def _militares_afastados_ids(filtros=None):
    hoje = date.today()
    militares_ids = _ids_militares_operacional_capital(filtros)

    if not militares_ids:
        return set()

    ids_le = {
        row[0] for row in (
            database.session.query(LicencaEspecial.militar_id)
            .filter(
                LicencaEspecial.militar_id.in_(militares_ids),
                LicencaEspecial.inicio_periodo_le.isnot(None),
                LicencaEspecial.fim_periodo_le.isnot(None),
                LicencaEspecial.inicio_periodo_le <= hoje,
                LicencaEspecial.fim_periodo_le >= hoje,
            )
            .distinct()
            .all()
        )
    }

    ids_lts = {
        row[0] for row in (
            database.session.query(LicencaParaTratamentoDeSaude.militar_id)
            .filter(
                LicencaParaTratamentoDeSaude.militar_id.in_(militares_ids),
                LicencaParaTratamentoDeSaude.inicio_periodo_lts.isnot(None),
                LicencaParaTratamentoDeSaude.fim_periodo_lts.isnot(None),
                LicencaParaTratamentoDeSaude.inicio_periodo_lts <= hoje,
                LicencaParaTratamentoDeSaude.fim_periodo_lts >= hoje,
            )
            .distinct()
            .all()
        )
    }

    return ids_le.union(ids_lts)


def _estatisticas_operacional_capital(filtros=None):
    filtros = filtros or {}
    militares_ids = _ids_militares_operacional_capital(filtros)

    efetivo_total = len(militares_ids)

    oficiais = (
        database.session.query(func.count(distinct(Militar.id)))
        .select_from(Militar)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .join(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
            PostoGrad.sigla.in_(
                ["CEL", "TC", "MAJ", "CAP", "1º TEN", "2º TEN", "ASP", "AL CFO"]),
        )
    )

    if filtros.get("posto_grad_id"):
        oficiais = oficiais.filter(
            Militar.posto_grad_id == filtros["posto_grad_id"])
    if filtros.get("quadro_id"):
        oficiais = oficiais.filter(Militar.quadro_id == filtros["quadro_id"])

    oficiais = oficiais.scalar() or 0
    pracas = max(efetivo_total - oficiais, 0)

    combatentes_q = (
        database.session.query(func.count(distinct(Militar.id)))
        .select_from(Militar)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
            Militar.especialidade_id == 3
        )
    )

    saude_q = (
        database.session.query(func.count(distinct(Militar.id)))
        .select_from(Militar)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
            Militar.especialidade_id.in_([1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        )
    )

    if filtros.get("posto_grad_id"):
        combatentes_q = combatentes_q.filter(
            Militar.posto_grad_id == filtros["posto_grad_id"])
        saude_q = saude_q.filter(
            Militar.posto_grad_id == filtros["posto_grad_id"])

    if filtros.get("quadro_id"):
        combatentes_q = combatentes_q.filter(
            Militar.quadro_id == filtros["quadro_id"])
        saude_q = saude_q.filter(Militar.quadro_id == filtros["quadro_id"])

    combatentes = combatentes_q.scalar() or 0
    saude = saude_q.scalar() or 0

    afastados_ids = _militares_afastados_ids(filtros)
    disponivel_operacional = max(efetivo_total - len(afastados_ids), 0)

    hoje = date.today()

    le_vigente = 0
    lts_vigente = 0
    if militares_ids:
        le_vigente = (
            LicencaEspecial.query
            .filter(
                LicencaEspecial.militar_id.in_(militares_ids),
                LicencaEspecial.inicio_periodo_le.isnot(None),
                LicencaEspecial.fim_periodo_le.isnot(None),
                LicencaEspecial.inicio_periodo_le <= hoje,
                LicencaEspecial.fim_periodo_le >= hoje,
            )
            .count()
        )

        lts_vigente = (
            LicencaParaTratamentoDeSaude.query
            .filter(
                LicencaParaTratamentoDeSaude.militar_id.in_(militares_ids),
                LicencaParaTratamentoDeSaude.inicio_periodo_lts.isnot(None),
                LicencaParaTratamentoDeSaude.fim_periodo_lts.isnot(None),
                LicencaParaTratamentoDeSaude.inicio_periodo_lts <= hoje,
                LicencaParaTratamentoDeSaude.fim_periodo_lts >= hoje,
            )
            .count()
        )

    por_obm_q = (
        database.session.query(
            Obm.id.label("obm_id"),
            Obm.sigla.label("obm_sigla"),
            func.count(distinct(Militar.id)).label("total")
        )
        .select_from(Militar)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
        )
    )

    if filtros.get("posto_grad_id"):
        por_obm_q = por_obm_q.filter(
            Militar.posto_grad_id == filtros["posto_grad_id"])
    if filtros.get("quadro_id"):
        por_obm_q = por_obm_q.filter(Militar.quadro_id == filtros["quadro_id"])

    por_obm = (
        por_obm_q
        .group_by(Obm.id, Obm.sigla)
        .order_by(func.count(distinct(Militar.id)).desc(), Obm.sigla.asc())
        .all()
    )

    return {
        "efetivo_total": efetivo_total,
        "oficiais": oficiais,
        "pracas": pracas,
        "combatentes": combatentes,
        "saude": saude,
        "licenca_especial": le_vigente,
        "lts": lts_vigente,
        "disponivel_operacional": disponivel_operacional,
        "por_obm": por_obm,
    }


def _preview_le_operacional_capital(limit=5, filtros=None):
    hoje = date.today()
    militares_ids = _ids_militares_operacional_capital(filtros)

    if not militares_ids:
        return []

    itens = (
        LicencaEspecial.query
        .options(
            joinedload(LicencaEspecial.militar),
            joinedload(LicencaEspecial.posto_grad),
            joinedload(LicencaEspecial.destino),
        )
        .filter(
            LicencaEspecial.militar_id.in_(militares_ids),
            LicencaEspecial.inicio_periodo_le.isnot(None),
            LicencaEspecial.fim_periodo_le.isnot(None),
            LicencaEspecial.inicio_periodo_le <= hoje,
            LicencaEspecial.fim_periodo_le >= hoje,
        )
        .order_by(LicencaEspecial.fim_periodo_le.asc(), LicencaEspecial.id.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "militar_id": item.militar_id,
            "nome": item.militar.nome_completo if item.militar else "N/A",
            "matricula": item.militar.matricula if item.militar else "N/A",
            "posto_grad": item.posto_grad.sigla if item.posto_grad else "N/A",
            "destino": item.destino.local if item.destino else "N/A",
            "fim": item.fim_periodo_le.strftime("%d/%m/%Y") if item.fim_periodo_le else "N/A",
            "dias_restantes": (item.fim_periodo_le - hoje).days if item.fim_periodo_le else None,
        }
        for item in itens
    ]


def _preview_lts_operacional_capital(limit=5, filtros=None):
    hoje = date.today()
    militares_ids = _ids_militares_operacional_capital(filtros)

    if not militares_ids:
        return []

    itens = (
        LicencaParaTratamentoDeSaude.query
        .options(
            joinedload(LicencaParaTratamentoDeSaude.militar),
            joinedload(LicencaParaTratamentoDeSaude.posto_grad),
            joinedload(LicencaParaTratamentoDeSaude.destino),
        )
        .filter(
            LicencaParaTratamentoDeSaude.militar_id.in_(militares_ids),
            LicencaParaTratamentoDeSaude.inicio_periodo_lts.isnot(None),
            LicencaParaTratamentoDeSaude.fim_periodo_lts.isnot(None),
            LicencaParaTratamentoDeSaude.inicio_periodo_lts <= hoje,
            LicencaParaTratamentoDeSaude.fim_periodo_lts >= hoje,
        )
        .order_by(
            LicencaParaTratamentoDeSaude.fim_periodo_lts.asc(),
            LicencaParaTratamentoDeSaude.id.desc()
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "militar_id": item.militar_id,
            "nome": item.militar.nome_completo if item.militar else "N/A",
            "matricula": item.militar.matricula if item.militar else "N/A",
            "posto_grad": item.posto_grad.sigla if item.posto_grad else "N/A",
            "destino": item.destino.local if item.destino else "N/A",
            "fim": item.fim_periodo_lts.strftime("%d/%m/%Y") if item.fim_periodo_lts else "N/A",
            "dias_restantes": (item.fim_periodo_lts - hoje).days if item.fim_periodo_lts else None,
        }
        for item in itens
    ]


def _militares_disponiveis_operacional_capital(filtros=None, limit=300):
    filtros = filtros or {}
    afastados_ids = _militares_afastados_ids(filtros)

    query = (
        database.session.query(
            Militar.id.label("militar_id"),
            Militar.nome_completo,
            Militar.matricula,
            PostoGrad.sigla.label("posto_grad"),
            Quadro.quadro.label("quadro"),
            Obm.sigla.label("obm_sigla"),
        )
        .select_from(Militar)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
        )
    )

    if filtros.get("posto_grad_id"):
        query = query.filter(Militar.posto_grad_id == filtros["posto_grad_id"])
    if filtros.get("quadro_id"):
        query = query.filter(Militar.quadro_id == filtros["quadro_id"])

    if afastados_ids:
        query = query.filter(~Militar.id.in_(afastados_ids))

    itens = (
        query
        .order_by(Obm.sigla.asc(), PostoGrad.sigla.asc(), Militar.nome_completo.asc())
        .limit(limit)
        .all()
    )

    return itens


def _opcoes_filtros_cbmc():
    postos = (
        database.session.query(PostoGrad.id, PostoGrad.sigla)
        .join(Militar, Militar.posto_grad_id == PostoGrad.id)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
        )
        .distinct()
        .order_by(PostoGrad.sigla.asc())
        .all()
    )

    quadros = (
        database.session.query(Quadro.id, Quadro.quadro)
        .join(Militar, Militar.quadro_id == Quadro.id)
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .filter(
            Militar.inativo.is_(False),
            Militar.localidade_id == LOCALIDADE_CAPITAL_ID,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.obm_id.in_(OBMS_OPERACIONAIS_CAPITAL),
        )
        .distinct()
        .order_by(Quadro.quadro.asc())
        .all()
    )

    return postos, quadros


def get_user_ip():
    # Verifica se o cabeçalho X-Forwarded-For está presente
    if request.headers.get('X-Forwarded-For'):
        # Pode conter múltiplos IPs, estou pegando o primeiro
        ip = request.headers.getlist('X-Forwarded-For')[0]
    else:
        # Fallback para o IP remoto
        ip = request.remote_addr
    return ip


def somente_numeros(valor):
    return re.sub(r"\D", "", valor or "")


def _to_manaus(dt):
    """Converte dt (naive/aware/None) para aware em America/Manaus."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # tratamos como horário local salvo sem tz
        return MANAUS_TZ.localize(dt)
    return dt.astimezone(MANAUS_TZ)            # converte para Manaus


def build_tabela_militares_query():
    """Monta a consulta da relação de militares aplicando todos os filtros GET/POST."""
    vals = request.values

    search = (vals.get("search", "", type=str) or "").strip()
    sexo_filtro = (vals.get("sexo", "", type=str) or "").strip().upper()

    obm_ids = vals.getlist("obm_ids", type=int)
    funcao_ids = vals.getlist("funcao_ids", type=int)
    posto_grad_ids = vals.getlist("posto_grad_ids", type=int)
    quadro_ids = vals.getlist("quadro_ids", type=int)
    especialidade_ids = vals.getlist("especialidade_ids", type=int)
    localidade_ids = vals.getlist("localidade_ids", type=int)
    modalidade_ids = vals.getlist("modalidade_ids", type=int)
    destino_ids = vals.getlist("destino_ids", type=int)

    # Compatibilidade com telas antigas que enviem o nome singular.
    if not destino_ids:
        destino_ids = vals.getlist("destino_id", type=int)

    # Situação é texto: PRONTO, AGREGADO ou À DISPOSIÇÃO.
    situacoes = [
        valor.strip().upper()
        for valor in vals.getlist("situacoes")
        if valor and valor.strip()
    ]

    # Compatibilidade com eventual campo singular.
    if not situacoes:
        situacao_unica = (vals.get("situacao", "", type=str) or "").strip()
        if situacao_unica:
            situacoes = [situacao_unica.upper()]

    query = (
        Militar.query
        .options(
            joinedload(Militar.posto_grad),
            joinedload(Militar.quadro),
            joinedload(Militar.especialidade),
            joinedload(Militar.localidade),
            joinedload(Militar.modalidade),
            joinedload(Militar.destino),
            selectinload(Militar.obm_funcoes).selectinload(
                MilitarObmFuncao.obm
            ),
            selectinload(Militar.obm_funcoes).selectinload(
                MilitarObmFuncao.funcao
            ),
        )
        .filter(Militar.inativo.is_(False))
    )

    # -----------------------------------------------------------------
    # Busca geral
    # -----------------------------------------------------------------
    if search:
        search_like = f"%{search}%"
        search_digits = re.sub(r"\D", "", search)

        filtros_busca = [
            func.coalesce(Militar.nome_completo, "").ilike(search_like),
            func.coalesce(Militar.nome_guerra, "").ilike(search_like),
            func.coalesce(Militar.cpf, "").ilike(search_like),
            func.coalesce(Militar.rg, "").ilike(search_like),
            func.coalesce(Militar.matricula, "").ilike(search_like),
        ]

        if search_digits:
            digits_like = f"%{search_digits}%"
            filtros_busca.extend([
                func.regexp_replace(
                    func.coalesce(Militar.cpf, ""),
                    r"[^0-9]",
                    "",
                    "g",
                ).like(digits_like),
                func.regexp_replace(
                    func.coalesce(Militar.rg, ""),
                    r"[^0-9]",
                    "",
                    "g",
                ).like(digits_like),
                func.regexp_replace(
                    func.coalesce(Militar.matricula, ""),
                    r"[^0-9]",
                    "",
                    "g",
                ).like(digits_like),
            ])

        query = query.filter(or_(*filtros_busca))

    # -----------------------------------------------------------------
    # Filtros diretos da tabela militar
    # -----------------------------------------------------------------
    if posto_grad_ids:
        query = query.filter(Militar.posto_grad_id.in_(posto_grad_ids))

    if quadro_ids:
        query = query.filter(Militar.quadro_id.in_(quadro_ids))

    if especialidade_ids:
        query = query.filter(
            Militar.especialidade_id.in_(especialidade_ids)
        )

    if localidade_ids:
        query = query.filter(Militar.localidade_id.in_(localidade_ids))

    if situacoes:
        query = query.filter(
            func.upper(
                func.trim(
                    func.coalesce(Militar.situacao, "")
                )
            ).in_(situacoes)
        )

    if modalidade_ids:
        query = query.filter(Militar.modalidade_id.in_(modalidade_ids))

    if destino_ids:
        query = query.filter(Militar.destino_id.in_(destino_ids))

    # -----------------------------------------------------------------
    # OBM e função: considera apenas vínculos ativos.
    # O mesmo vínculo precisa satisfazer OBM e função quando ambos forem usados.
    # -----------------------------------------------------------------
    if obm_ids or funcao_ids:
        vinculos_ativos = (
            database.session.query(MilitarObmFuncao.militar_id)
            .filter(MilitarObmFuncao.data_fim.is_(None))
        )

        if obm_ids:
            vinculos_ativos = vinculos_ativos.filter(
                MilitarObmFuncao.obm_id.in_(obm_ids)
            )

        if funcao_ids:
            vinculos_ativos = vinculos_ativos.filter(
                MilitarObmFuncao.funcao_id.in_(funcao_ids)
            )

        query = query.filter(
            Militar.id.in_(vinculos_ativos.distinct())
        )

    # -----------------------------------------------------------------
    # Sexo
    # -----------------------------------------------------------------
    sexo_normalizado = func.lower(
        func.trim(func.coalesce(Militar.sexo, ""))
    )

    if sexo_filtro == "M":
        query = query.filter(sexo_normalizado.like("m%"))
    elif sexo_filtro == "F":
        query = query.filter(sexo_normalizado.like("f%"))

    return query


def get_status_sets(base_query, today):
    filtrados_sq = (
        base_query
        .order_by(None)
        .with_entities(Militar.id)
        .distinct()
        .subquery()
    )

    agregados_ids = {
        x[0] for x in (
            database.session.query(MilitaresAgregados.militar_id)
            .join(filtrados_sq, MilitaresAgregados.militar_id == filtrados_sq.c.id)
            .filter(
                MilitaresAgregados.inicio_periodo <= today,
                or_(
                    MilitaresAgregados.fim_periodo_agregacao.is_(None),
                    MilitaresAgregados.fim_periodo_agregacao >= today,
                )
            )
            .distinct()
            .all()
        )
    }

    adisposicao_ids = {
        x[0] for x in (
            database.session.query(MilitaresADisposicao.militar_id)
            .join(filtrados_sq, MilitaresADisposicao.militar_id == filtrados_sq.c.id)
            .filter(
                MilitaresADisposicao.inicio_periodo <= today,
                or_(
                    MilitaresADisposicao.fim_periodo_disposicao.is_(None),
                    MilitaresADisposicao.fim_periodo_disposicao >= today,
                )
            )
            .distinct()
            .all()
        )
    }

    return agregados_ids, adisposicao_ids


def arred(valor):
    return Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# Função para cálculo de dias no padrão 30/360 Europeu


def dias360_europeu(inicio: datetime, fim: datetime) -> int:
    d1, m1, a1 = inicio.day, inicio.month, inicio.year
    d2, m2, a2 = fim.day, fim.month, fim.year

    if d1 == 31:
        d1 = 30
    if d2 == 31:
        if d1 < 30:
            d2 = 1
            m2 += 1
            if m2 > 12:
                m2 = 1
                a2 += 1
        else:
            d2 = 30

    return (a2 - a1) * 360 + (m2 - m1) * 30 + (d2 - d1)


def calcular_semana(data_convocacao, data_base=None):
    if not data_base:
        # data base inicial da primeira semana
        data_base = datetime(2025, 5, 5)
    dias_passados = (data_convocacao - data_base).days
    numero_semana = dias_passados // 7 + 1
    return f"Semana {numero_semana}"


def calcular_comportamento(nota):
    if nota < 4:
        return "Mau"
    elif nota < 5:
        return "Insuficiente"
    elif nota < 8:
        return "Bom"
    elif nota < 9:
        return "Ótimo"
    else:
        return "Excepcional"


def _limpa_sessao_validacao():
    for k in ['matricula_validada', 'cpf_em_validacao', 'militar_id_validado', 'email_atualizacao']:
        session.pop(k, None)


def _norm_cpf(cpf: str) -> str:
    return re.sub(r'\D', '', cpf or '')
