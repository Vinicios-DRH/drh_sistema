"""Módulo de Histórico do Militar (rota /historico, em src/routes/historico.py):
reúne, numa página só, tudo que já aconteceu na vida funcional de um militar —
OBMs por onde passou, férias por ano, licenças (especial e LTS), agregações e
disposições, formação e o histórico de alterações de situação pela chefia.

Não inventa consulta nova onde já existe uma: reaproveita os services já
usados pelas telas de listagem correspondentes, só filtrando por um único
militar_id.
"""
from sqlalchemy.orm import joinedload

from src.models import (
    AuditoriaAtualizacaoCadastral,
    Militar,
    MilitarCurso,
    MilitarGraduacao,
    MilitarObmFuncao,
)
from src.services.lts_service import listar_militares_lts
from src.services.paf_service import listar_pafs_do_militar
from src.services.situacoes_militares_service import (
    listar_licencas_especiais,
    listar_militares_a_disposicao,
    listar_militares_agregados,
)


def buscar_militar_para_historico(militar_id: int):
    """Militar com os relacionamentos do cabeçalho já carregados, ou None
    se o id não existir."""
    return (
        Militar.query
        .options(
            joinedload(Militar.posto_grad),
            joinedload(Militar.quadro),
            joinedload(Militar.localidade),
            joinedload(Militar.especialidade),
            joinedload(Militar.destino),
            joinedload(Militar.modalidade),
            joinedload(Militar.motivo),
        )
        .filter(Militar.id == militar_id)
        .first()
    )


def listar_lotacoes(militar_id: int):
    """Todas as passagens de OBM/função do militar (vigentes e encerradas),
    mais recentes primeiro."""
    return (
        MilitarObmFuncao.query
        .options(
            joinedload(MilitarObmFuncao.obm),
            joinedload(MilitarObmFuncao.funcao),
        )
        .filter(MilitarObmFuncao.militar_id == militar_id)
        .order_by(MilitarObmFuncao.data_criacao.desc())
        .all()
    )


def listar_graduacoes(militar_id: int):
    return (
        MilitarGraduacao.query
        .filter(MilitarGraduacao.militar_id == militar_id)
        .order_by(
            MilitarGraduacao.ano_conclusao.desc().nullslast(),
            MilitarGraduacao.criado_em.desc(),
        )
        .all()
    )


def listar_cursos_especializacao(militar_id: int):
    return (
        MilitarCurso.query
        .options(joinedload(MilitarCurso.curso))
        .filter(MilitarCurso.militar_id == militar_id)
        .order_by(MilitarCurso.data_conclusao.desc().nullslast())
        .all()
    )


def listar_auditoria_situacao(militar_id: int):
    """Trilha de alterações de situação feitas pela chefia (Gestão de
    Chefia / Mapa da Força), com quem alterou."""
    return (
        AuditoriaAtualizacaoCadastral.query
        .options(joinedload(AuditoriaAtualizacaoCadastral.user))
        .filter(AuditoriaAtualizacaoCadastral.militar_id == militar_id)
        .order_by(AuditoriaAtualizacaoCadastral.criado_em.desc())
        .all()
    )


def montar_historico_militar(militar_id: int):
    """Monta todo o contexto da página de histórico para um militar, ou
    devolve None se o militar não existir."""
    militar = buscar_militar_para_historico(militar_id)
    if not militar:
        return None

    return {
        "militar": militar,
        "lotacoes": listar_lotacoes(militar_id),
        "ferias": listar_pafs_do_militar(militar_id),
        "licencas_especiais": listar_licencas_especiais(militar_id=militar_id),
        "lts": listar_militares_lts(militar_id=militar_id),
        "agregacoes": listar_militares_agregados(militar_id=militar_id),
        "disposicoes": listar_militares_a_disposicao(militar_id=militar_id),
        "graduacoes": listar_graduacoes(militar_id),
        "cursos": listar_cursos_especializacao(militar_id),
        "auditorias": listar_auditoria_situacao(militar_id),
    }


def buscar_militares_por_texto(termo: str, limite: int = 20):
    """Busca militares por nome, nome de guerra, matrícula ou CPF — usada no
    autocomplete de busca da página de histórico."""
    termo = (termo or "").strip()
    if len(termo) < 2:
        return []

    like = f"%{termo}%"
    return (
        Militar.query
        .options(joinedload(Militar.posto_grad))
        .filter(
            Militar.nome_completo.ilike(like)
            | Militar.nome_guerra.ilike(like)
            | Militar.matricula.ilike(like)
            | Militar.cpf.ilike(like)
        )
        .order_by(Militar.nome_completo.asc())
        .limit(limite)
        .all()
    )
