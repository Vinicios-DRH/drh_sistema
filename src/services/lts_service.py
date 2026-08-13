"""Consultas usadas pela tela de Licença para Tratamento de Saúde (LTS)
(rota /licenca-para-tratamento-de-saude, em src/routes/militares_listagem.py).

A regra de negócio de status/ciclo de vida da LTS (quando vira "Vigente",
"Término" etc., e o retorno automático do militar a PRONTO) mora em
src.services.militar_situacao_service — este módulo é só sobre montar a
listagem para o template.
"""
from sqlalchemy.orm import joinedload

from src.models import LicencaParaTratamentoDeSaude


def listar_militares_lts(militar_id=None):
    """Sem `militar_id`, lista todas as LTS (tela /licenca-para-tratamento-de-saude).
    Com `militar_id`, filtra pra um único militar (módulo de Histórico).

    Relacionamentos usados pelo template já vêm carregados (evita N+1 query
    por linha da tabela)."""
    query = LicencaParaTratamentoDeSaude.query.options(
        joinedload(LicencaParaTratamentoDeSaude.militar),
        joinedload(LicencaParaTratamentoDeSaude.posto_grad),
        joinedload(LicencaParaTratamentoDeSaude.quadro),
        joinedload(LicencaParaTratamentoDeSaude.destino),
        joinedload(LicencaParaTratamentoDeSaude.modalidade),
        joinedload(LicencaParaTratamentoDeSaude.publicacao_bg),
    )
    if militar_id is not None:
        query = query.filter(LicencaParaTratamentoDeSaude.militar_id == militar_id)
    return query.order_by(LicencaParaTratamentoDeSaude.fim_periodo_lts.desc().nullslast()).all()
