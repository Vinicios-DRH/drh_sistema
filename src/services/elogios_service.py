"""Elogios do militar — reconhecimentos registrados na ficha (rota
/exibir-militar/<id>, em src/routes/militares_cadastro.py), com assunto e
publicação (BG). Um militar pode acumular quantos elogios forem lançados;
não há ciclo de vida/status como em LTS ou Agregação, é só uma lista que
só cresce.

Reaproveitado também pelo módulo de Histórico (src/services/historico_militar_service.py).
"""
from sqlalchemy.orm import joinedload

from src import database
from src.models import MilitarElogio


def listar_elogios(militar_id):
    """Elogios de um militar, mais recente primeiro."""
    return (
        MilitarElogio.query
        .options(joinedload(MilitarElogio.criado_por))
        .filter(MilitarElogio.militar_id == militar_id)
        .order_by(MilitarElogio.criado_em.desc())
        .all()
    )


def criar_elogio(militar_id, assunto, publicacao, observacao=None, criado_por_user_id=None):
    """Monta um novo elogio e o coloca na sessão (quem chama decide o commit).

    Levanta ValueError se assunto/publicação vierem vazios — são os dois
    campos que dão sentido ao registro."""
    assunto = (assunto or "").strip()
    publicacao = (publicacao or "").strip()
    observacao = (observacao or "").strip() or None

    if not assunto:
        raise ValueError("Informe o assunto do elogio.")
    if not publicacao:
        raise ValueError("Informe a publicação (BG) do elogio.")

    elogio = MilitarElogio(
        militar_id=militar_id,
        assunto=assunto,
        publicacao=publicacao,
        observacao=observacao,
        criado_por_user_id=criado_por_user_id,
    )
    database.session.add(elogio)
    return elogio


def remover_elogio(elogio_id):
    """Remove um elogio pelo id, ou devolve None se não existir."""
    elogio = MilitarElogio.query.get(elogio_id)
    if not elogio:
        return None
    database.session.delete(elogio)
    return elogio
