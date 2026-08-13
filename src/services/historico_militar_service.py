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
    PublicacaoBg,
)
from src.services.elogios_service import listar_elogios
from src.services.lts_service import listar_militares_lts
from src.services.paf_service import listar_pafs_do_militar, status_periodo_ferias
from src.services.situacoes_militares_service import (
    listar_licencas_especiais,
    listar_militares_a_disposicao,
    listar_militares_agregados,
)

# Escada de posto/graduação (do soldado ao coronel) na ordem em que a
# progressão de carreira realmente acontece. `campo_militar` é a coluna em
# Militar que guarda a publicação (BG) daquela promoção; `campo_publicidade`
# é o tipo_bg correspondente em PublicacaoBg — só oficiais têm uma
# "publicidade" complementar, e ela nunca virou coluna direta em Militar.
PROGRESSAO_CARREIRA = [
    ("soldado_tres", "Soldado 3ª Classe", None),
    ("soldado_dois", "Soldado 2ª Classe", None),
    ("soldado_um", "Soldado 1ª Classe", None),
    ("cabo", "Cabo", None),
    ("terceiro_sgt", "3º Sargento", None),
    ("segundo_sgt", "2º Sargento", None),
    ("primeiro_sgt", "1º Sargento", None),
    ("subtenente", "Subtenente", None),
    ("segundo_tenente", "2º Tenente", "publicidade_segundo_tenente"),
    ("primeiro_tenente", "1º Tenente", "publicidade_primeiro_tenente"),
    ("cap", "Capitão", "pub_cap"),
    ("maj", "Major", "pub_maj"),
    ("tc", "Tenente-Coronel", "pub_tc"),
    ("cel", "Coronel", "pub_cel"),
]


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


def listar_ferias_com_status(militar_id: int):
    """PAFs do militar (um por ano) com cada período (1º/2º/3º) já marcado
    como "A iniciar", "Vigente" ou "Usufruída" — pra tela de histórico
    distinguir o que já passou do que ainda vem."""
    pafs = listar_pafs_do_militar(militar_id)

    resultado = []
    for paf in pafs:
        periodos = [
            {
                "numero": 1,
                "qtd_dias": paf.qtd_dias_primeiro_periodo,
                "inicio": paf.primeiro_periodo_ferias,
                "fim": paf.fim_primeiro_periodo,
                "status": status_periodo_ferias(paf.primeiro_periodo_ferias, paf.fim_primeiro_periodo),
            },
            {
                "numero": 2,
                "qtd_dias": paf.qtd_dias_segundo_periodo,
                "inicio": paf.segundo_periodo_ferias,
                "fim": paf.fim_segundo_periodo,
                "status": status_periodo_ferias(paf.segundo_periodo_ferias, paf.fim_segundo_periodo),
            },
            {
                "numero": 3,
                "qtd_dias": paf.qtd_dias_terceiro_periodo,
                "inicio": paf.terceiro_periodo_ferias,
                "fim": paf.fim_terceiro_periodo,
                "status": status_periodo_ferias(paf.terceiro_periodo_ferias, paf.fim_terceiro_periodo),
            },
        ]
        resultado.append({"paf": paf, "periodos": periodos})

    return resultado


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


def listar_progressao_carreira(militar: Militar):
    """Monta a escada de progressão de posto/graduação do militar (Soldado 3ª
    Classe até Coronel), com a publicação (BG) de cada promoção. Os postos de
    oficial ganham também a "publicidade" complementar, que só existe em
    PublicacaoBg (nunca foi coluna direta em Militar)."""
    campos_publicidade = [c for _, _, c in PROGRESSAO_CARREIRA if c]
    publicidades = {
        pb.tipo_bg: pb.boletim_geral
        for pb in PublicacaoBg.query.filter(
            PublicacaoBg.militar_id == militar.id,
            PublicacaoBg.tipo_bg.in_(campos_publicidade),
        ).all()
    }

    degraus = []
    for campo_militar, rotulo, campo_publicidade in PROGRESSAO_CARREIRA:
        publicacao = getattr(militar, campo_militar, None)
        publicidade = publicidades.get(campo_publicidade) if campo_publicidade else None
        degraus.append({
            "rotulo": rotulo,
            "publicacao": publicacao,
            "publicidade": publicidade,
            "alcancado": bool(publicacao or publicidade),
        })
    return degraus


def obter_publicacao_situacao_atual(militar_id: int):
    """Publicação (BG) da situação funcional atual — o mesmo campo
    "Publicação" da aba Situação Funcional em Exibir Militar.

    Existem modalidades (Agregação, À Disposição, Licença Especial, LTS) com
    tabela própria de histórico, cada registro já com sua publicação. Mas
    outras — Licença Maternidade é o principal exemplo — não têm tabela
    dedicada: a única publicação registrada é essa, presa à situação atual
    do militar. É por isso que ela precisa aparecer aqui à parte."""
    pb = PublicacaoBg.query.filter_by(
        militar_id=militar_id, tipo_bg="situacao_militar"
    ).first()
    return pb.boletim_geral if pb else None


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
        "publicacao_situacao_atual": obter_publicacao_situacao_atual(militar_id),
        "lotacoes": listar_lotacoes(militar_id),
        "elogios": listar_elogios(militar_id),
        "ferias": listar_ferias_com_status(militar_id),
        "licencas_especiais": listar_licencas_especiais(militar_id=militar_id),
        "lts": listar_militares_lts(militar_id=militar_id),
        "agregacoes": listar_militares_agregados(militar_id=militar_id),
        "disposicoes": listar_militares_a_disposicao(militar_id=militar_id),
        "graduacoes": listar_graduacoes(militar_id),
        "cursos": listar_cursos_especializacao(militar_id),
        "progressao_carreira": listar_progressao_carreira(militar),
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
