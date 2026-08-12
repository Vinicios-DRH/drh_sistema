import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from src.models import (
    Destino,
    Especialidade,
    Funcao,
    Localidade,
    Militar,
    MilitarObmFuncao,
    Modalidade,
    Obm,
    PostoGrad,
    Quadro,
)

PER_PAGE = 50


def montar_choices_filtro_militar(form_filtro):
    """Popula os <select multiple> do FormFiltroMilitar a partir do banco."""
    form_filtro.obm_id_1.choices = [
        (obm.id, obm.sigla) for obm in Obm.query.order_by(Obm.sigla.asc()).all()
    ]
    form_filtro.funcao_id.choices = [
        (funcao.id, funcao.ocupacao)
        for funcao in Funcao.query.order_by(Funcao.ocupacao.asc()).all()
    ]
    form_filtro.posto_grad_id.choices = [
        (posto.id, posto.sigla)
        for posto in PostoGrad.query.order_by(PostoGrad.sigla.asc()).all()
    ]
    form_filtro.quadro_id.choices = [
        (quadro.id, quadro.quadro)
        for quadro in Quadro.query.order_by(Quadro.quadro.asc()).all()
    ]
    form_filtro.especialidade_id.choices = [
        (esp.id, esp.ocupacao)
        for esp in Especialidade.query.order_by(Especialidade.ocupacao.asc()).all()
    ]
    form_filtro.localidade_id.choices = [
        (loc.id, loc.sigla)
        for loc in Localidade.query.order_by(Localidade.sigla.asc()).all()
    ]
    form_filtro.modalidade_id.choices = [
        (mod.id, mod.descricao)
        for mod in Modalidade.query.order_by(Modalidade.descricao.asc()).all()
    ]
    form_filtro.destino_id.choices = [
        (dest.id, dest.local)
        for dest in Destino.query.order_by(Destino.local.asc()).all()
    ]


@dataclass
class FiltrosMilitares:
    """Filtros da listagem de militares, já normalizados a partir da querystring."""
    page: int = 1
    search: str = ""
    obm_ids: List[int] = field(default_factory=list)
    funcao_ids: List[int] = field(default_factory=list)
    posto_grad_ids: List[int] = field(default_factory=list)
    quadro_ids: List[int] = field(default_factory=list)
    especialidade_ids: List[int] = field(default_factory=list)
    localidade_ids: List[int] = field(default_factory=list)
    modalidade_ids: List[int] = field(default_factory=list)
    destino_ids: List[int] = field(default_factory=list)
    situacoes: List[str] = field(default_factory=list)
    sexo: str = ""


def extrair_filtros_militares(args) -> FiltrosMilitares:
    """Lê os parâmetros de filtro da querystring (`request.args`) da rota /militares."""
    return FiltrosMilitares(
        page=args.get("page", 1, type=int),
        search=(args.get("search") or "").strip(),
        obm_ids=args.getlist("obm_ids", type=int),
        funcao_ids=args.getlist("funcao_ids", type=int),
        posto_grad_ids=args.getlist("posto_grad_ids", type=int),
        quadro_ids=args.getlist("quadro_ids", type=int),
        especialidade_ids=args.getlist("especialidade_ids", type=int),
        localidade_ids=args.getlist("localidade_ids", type=int),
        modalidade_ids=args.getlist("modalidade_ids", type=int),
        destino_ids=args.getlist("destino_ids", type=int),
        situacoes=[
            situacao.strip().upper()
            for situacao in args.getlist("situacoes")
            if situacao and situacao.strip()
        ],
        sexo=(args.get("sexo") or "").strip().upper(),
    )


def _query_base_militares_ativos():
    return (
        Militar.query
        .options(
            selectinload(Militar.obm_funcoes).selectinload(MilitarObmFuncao.obm),
            selectinload(Militar.obm_funcoes).selectinload(MilitarObmFuncao.funcao),
            selectinload(Militar.posto_grad),
            selectinload(Militar.quadro),
            selectinload(Militar.destino),
        )
        .filter(Militar.inativo.is_(False))
    )


def _aplicar_busca_texto(query, search: str):
    """Busca por nome (sem acento), CPF, RG e matrícula (com ou sem pontuação)."""
    if not search:
        return query

    search_like = f"%{search}%"
    search_digits = re.sub(r"\D", "", search)
    digits_like = f"%{search_digits}%" if search_digits else None

    def norm_text(column):
        return func.lower(func.unaccent(func.coalesce(column, "")))

    filtros_busca = [
        norm_text(Militar.nome_completo).like(func.lower(func.unaccent(search_like))),
        norm_text(Militar.nome_guerra).like(func.lower(func.unaccent(search_like))),
        func.coalesce(Militar.cpf, "").ilike(search_like),
        func.coalesce(Militar.rg, "").ilike(search_like),
        func.coalesce(Militar.matricula, "").ilike(search_like),
    ]

    if digits_like:
        filtros_busca.extend([
            func.regexp_replace(func.coalesce(Militar.cpf, ""), r"[^0-9]", "", "g").like(digits_like),
            func.regexp_replace(func.coalesce(Militar.rg, ""), r"[^0-9]", "", "g").like(digits_like),
            func.regexp_replace(func.coalesce(Militar.matricula, ""), r"[^0-9]", "", "g").like(digits_like),
        ])

    return query.filter(or_(*filtros_busca))


def _aplicar_filtros_diretos(query, filtros: FiltrosMilitares):
    """Filtros que batem direto em colunas de Militar (sem join)."""
    if filtros.posto_grad_ids:
        query = query.filter(Militar.posto_grad_id.in_(filtros.posto_grad_ids))

    if filtros.quadro_ids:
        query = query.filter(Militar.quadro_id.in_(filtros.quadro_ids))

    if filtros.especialidade_ids:
        query = query.filter(Militar.especialidade_id.in_(filtros.especialidade_ids))

    if filtros.localidade_ids:
        query = query.filter(Militar.localidade_id.in_(filtros.localidade_ids))

    if filtros.situacoes:
        query = query.filter(
            func.upper(func.trim(func.coalesce(Militar.situacao, ""))).in_(filtros.situacoes)
        )

    if filtros.modalidade_ids:
        query = query.filter(Militar.modalidade_id.in_(filtros.modalidade_ids))

    if filtros.destino_ids:
        query = query.filter(Militar.destino_id.in_(filtros.destino_ids))

    return query


def _aplicar_filtro_obm_funcao(query, filtros: FiltrosMilitares):
    """Filtra por OBM/função do vínculo ATIVO (data_fim nula) do militar."""
    if not (filtros.obm_ids or filtros.funcao_ids):
        return query

    query = (
        query
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .filter(MilitarObmFuncao.data_fim.is_(None))
    )

    if filtros.obm_ids:
        query = query.filter(MilitarObmFuncao.obm_id.in_(filtros.obm_ids))

    if filtros.funcao_ids:
        query = query.filter(MilitarObmFuncao.funcao_id.in_(filtros.funcao_ids))

    return query.distinct()


def _aplicar_filtro_sexo(query, sexo: str):
    if sexo not in ("M", "F"):
        return query

    sexo_normalizado = func.lower(func.trim(func.coalesce(Militar.sexo, "")))
    return query.filter(sexo_normalizado.like(f"{sexo.lower()}%"))


def construir_query_militares(filtros: FiltrosMilitares):
    """Monta a query de militares ativos aplicando busca textual e todos os filtros."""
    query = _query_base_militares_ativos()
    query = _aplicar_busca_texto(query, filtros.search)
    query = _aplicar_filtros_diretos(query, filtros)
    query = _aplicar_filtro_obm_funcao(query, filtros)
    query = _aplicar_filtro_sexo(query, filtros.sexo)
    return query


def formatar_cpf_exibicao(cpf):
    """Formata um CPF de 11 dígitos como 123.456.789-00; devolve o valor original
    (ou vazio) quando não há exatamente 11 dígitos, para não quebrar em dados
    incompletos/legados."""
    digitos = re.sub(r"\D", "", cpf or "")

    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:11]}"

    return cpf or ""


def serializar_militar_linha(militar: Militar) -> dict:
    """Converte um Militar (com obm_funcoes já carregado) numa linha pronta pro template,
    trazendo a OBM/função mais recente entre os vínculos ativos."""
    obm_funcoes_ativas = sorted(
        (v for v in militar.obm_funcoes if v.data_fim is None),
        key=lambda v: v.data_criacao or datetime.min,
        reverse=True,
    )

    obms_recentes = [
        v.obm.sigla if v.obm else "OBM não encontrada"
        for v in obm_funcoes_ativas
    ]
    funcoes_recentes = [
        v.funcao.ocupacao if v.funcao else "Função não encontrada"
        for v in obm_funcoes_ativas
    ]

    return {
        "id": militar.id,
        "nome_completo": militar.nome_completo,
        "nome_guerra": militar.nome_guerra,
        "cpf": militar.cpf,
        "cpf_fmt": formatar_cpf_exibicao(militar.cpf),
        "rg": militar.rg,
        "matricula": militar.matricula,
        "obms": obms_recentes,
        "funcoes": funcoes_recentes,
        "posto_grad": militar.posto_grad.sigla if militar.posto_grad else "",
        "quadro": militar.quadro.quadro if militar.quadro else "",
        "situacao": militar.situacao or "",
        "destino": militar.destino.local if militar.destino else "",
    }
