"""Consultas usadas pelas telas de listagem de situação funcional irmãs da
LTS: militares agregados, à disposição e em licença especial.

A regra de status de cada uma já existe em src.decorators.business_logic
(processar_militares_agregados/a_disposicao/le) — este módulo é só sobre
montar a listagem (com eager loading) para o template.
"""
from sqlalchemy.orm import joinedload

from src.models import LicencaEspecial, MilitaresADisposicao, MilitaresAgregados

_RELACIONAMENTOS_COMUNS = ("militar", "posto_grad", "quadro", "destino", "modalidade", "publicacao_bg")


def listar_militares_agregados(militar_id=None):
    """Sem `militar_id`, lista todos (tela /militares-agregados). Com
    `militar_id`, filtra pra um único militar (módulo de Histórico)."""
    query = MilitaresAgregados.query.options(
        *[joinedload(getattr(MilitaresAgregados, rel)) for rel in _RELACIONAMENTOS_COMUNS]
    )
    if militar_id is not None:
        query = query.filter(MilitaresAgregados.militar_id == militar_id)
    return query.order_by(MilitaresAgregados.fim_periodo_agregacao.desc().nullslast()).all()


def listar_militares_a_disposicao(militar_id=None):
    """Sem `militar_id`, lista todos (tela /militares-a-disposicao). Com
    `militar_id`, filtra pra um único militar (módulo de Histórico)."""
    query = MilitaresADisposicao.query.options(
        *[joinedload(getattr(MilitaresADisposicao, rel)) for rel in _RELACIONAMENTOS_COMUNS]
    )
    if militar_id is not None:
        query = query.filter(MilitaresADisposicao.militar_id == militar_id)
    return query.order_by(MilitaresADisposicao.fim_periodo_disposicao.desc().nullslast()).all()


def listar_licencas_especiais(militar_id=None):
    """Sem `militar_id`, lista todas (tela /licenca-especial). Com
    `militar_id`, filtra pra um único militar (módulo de Histórico)."""
    query = LicencaEspecial.query.options(
        *[joinedload(getattr(LicencaEspecial, rel)) for rel in _RELACIONAMENTOS_COMUNS]
    )
    if militar_id is not None:
        query = query.filter(LicencaEspecial.militar_id == militar_id)
    return query.order_by(LicencaEspecial.fim_periodo_le.desc().nullslast()).all()
