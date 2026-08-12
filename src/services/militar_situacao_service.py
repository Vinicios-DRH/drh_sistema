from datetime import date, datetime, timedelta
from sqlalchemy import or_

from src import database
from src.models import (
    Modalidade,
    Motivo,
    PublicacaoBg,
    MilitaresAgregados,
    MilitaresADisposicao,
    LicencaEspecial,
    LicencaParaTratamentoDeSaude,
)


def normalizar_str(valor):
    return (valor or "").strip().upper()


def parse_date_flex(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if hasattr(valor, "strftime"):
        return valor
    s = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def obter_modalidade_por_id(modalidade_id):
    if not modalidade_id:
        return None
    return Modalidade.query.get(modalidade_id)


def obter_motivo_por_id(motivo_id):
    if not motivo_id:
        return None
    return Motivo.query.get(motivo_id)


def obter_publicacao_bg_id(militar_id, tipo_bg="situacao_militar"):
    bg = PublicacaoBg.query.filter_by(
        militar_id=militar_id,
        tipo_bg=tipo_bg
    ).first()
    return bg.id if bg else None


def encerrar_agregacao_vigente(militar_id):
    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    registros = MilitaresAgregados.query.filter(
        MilitaresAgregados.militar_id == militar_id,
        or_(
            MilitaresAgregados.fim_periodo_agregacao.is_(None),
            MilitaresAgregados.fim_periodo_agregacao >= hoje
        )
    ).all()

    for reg in registros:
        if not reg.fim_periodo_agregacao or reg.fim_periodo_agregacao >= hoje:
            reg.fim_periodo_agregacao = ontem
            reg.atualizar_status()


def encerrar_disposicao_vigente(militar_id):
    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    registros = MilitaresADisposicao.query.filter(
        MilitaresADisposicao.militar_id == militar_id,
        or_(
            MilitaresADisposicao.fim_periodo_disposicao.is_(None),
            MilitaresADisposicao.fim_periodo_disposicao >= hoje
        )
    ).all()

    for reg in registros:
        if not reg.fim_periodo_disposicao or reg.fim_periodo_disposicao >= hoje:
            reg.fim_periodo_disposicao = ontem
            reg.atualizar_status()


def encerrar_le_vigente(militar_id):
    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    registros = LicencaEspecial.query.filter(
        LicencaEspecial.militar_id == militar_id,
        LicencaEspecial.inicio_periodo_le <= hoje,
        or_(
            LicencaEspecial.fim_periodo_le.is_(None),
            LicencaEspecial.fim_periodo_le >= hoje
        )
    ).all()

    for reg in registros:
        reg.fim_periodo_le = ontem
        reg.atualizar_status()


def encerrar_lts_vigente(militar_id):
    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    registros = LicencaParaTratamentoDeSaude.query.filter(
        LicencaParaTratamentoDeSaude.militar_id == militar_id,
        or_(
            LicencaParaTratamentoDeSaude.fim_periodo_lts.is_(None),
            LicencaParaTratamentoDeSaude.fim_periodo_lts >= hoje
        )
    ).all()

    for reg in registros:
        if not reg.fim_periodo_lts or reg.fim_periodo_lts >= hoje:
            reg.fim_periodo_lts = ontem
            reg.atualizar_status()


# Modalidade "PRONTO" e motivo "SEM AGREGAÇÕES" — para onde o militar volta
# automaticamente quando a LTS dele termina.
MODALIDADE_PRONTO_ID = 8
MOTIVO_SEM_AGREGACOES_ID = 1


def processar_fim_de_lts():
    """Atualiza o status de todas as LTS (recalculado a partir de hoje) e,
    para as que acabaram de virar "Término" nesta chamada, devolve o militar
    para PRONTO — mas só se ele ainda estiver com a modalidade de LTS, ou
    seja, só se ninguém já tiver alterado a situação dele manualmente nesse
    meio-tempo (evita sobrescrever uma mudança de situação mais recente).

    Não comita a sessão — quem chama decide o commit.
    Retorna a lista de militares que foram promovidos de volta a PRONTO.
    """
    todas = LicencaParaTratamentoDeSaude.query.all()

    militares_promovidos = []
    for lts in todas:
        status_anterior = lts.status
        lts.atualizar_status()

        virou_termino_agora = (
            lts.status == "Término da Licença para Tratamento de Saúde"
            and status_anterior != lts.status
        )
        if not virou_termino_agora:
            continue

        militar = lts.militar
        ainda_em_lts = (
            militar is not None
            and lts.modalidade_id is not None
            and militar.modalidade_id == lts.modalidade_id
        )
        if ainda_em_lts:
            militar.situacao = "PRONTO"
            militar.modalidade_id = MODALIDADE_PRONTO_ID
            militar.motivo_id = MOTIVO_SEM_AGREGACOES_ID
            militares_promovidos.append(militar)

    return militares_promovidos


def sincronizar_blocos_funcionais(militar, form_militar):
    hoje = date.today()

    modalidade_obj = obter_modalidade_por_id(form_militar.modalidade_id.data)
    modalidade_nome = normalizar_str(
        modalidade_obj.descricao if modalidade_obj else None)
    situacao_principal = normalizar_str(form_militar.situacao.data)

    bg_id = obter_publicacao_bg_id(militar.id)

    # AGREGAÇÃO
    if situacao_principal == "AGREGADO":
        militar_agregado = MilitaresAgregados.query.filter(
            MilitaresAgregados.militar_id == militar.id,
            or_(
                MilitaresAgregados.fim_periodo_agregacao.is_(None),
                MilitaresAgregados.fim_periodo_agregacao >= hoje
            )
        ).order_by(MilitaresAgregados.id.desc()).first()

        if not militar_agregado:
            militar_agregado = MilitaresAgregados(militar_id=militar.id)
            database.session.add(militar_agregado)

        militar_agregado.posto_grad_id = form_militar.posto_grad_id.data
        militar_agregado.quadro_id = form_militar.quadro_id.data
        militar_agregado.destino_id = form_militar.destino_id.data
        militar_agregado.modalidade_id = modalidade_obj.id if modalidade_obj else None
        militar_agregado.inicio_periodo = parse_date_flex(
            form_militar.inicio_periodo.data)
        militar_agregado.fim_periodo_agregacao = parse_date_flex(
            form_militar.fim_periodo.data)
        militar_agregado.publicacao_bg_id = bg_id
        militar_agregado.atualizar_status()
    else:
        encerrar_agregacao_vigente(militar.id)

    # À DISPOSIÇÃO
    if modalidade_nome == "À DISPOSIÇÃO":
        militar_a_disposicao = MilitaresADisposicao.query.filter(
            MilitaresADisposicao.militar_id == militar.id,
            or_(
                MilitaresADisposicao.fim_periodo_disposicao.is_(None),
                MilitaresADisposicao.fim_periodo_disposicao >= hoje
            )
        ).order_by(MilitaresADisposicao.id.desc()).first()

        if not militar_a_disposicao:
            militar_a_disposicao = MilitaresADisposicao(militar_id=militar.id)
            database.session.add(militar_a_disposicao)

        militar_a_disposicao.posto_grad_id = form_militar.posto_grad_id.data
        militar_a_disposicao.quadro_id = form_militar.quadro_id.data
        militar_a_disposicao.destino_id = form_militar.destino_id.data
        militar_a_disposicao.modalidade_id = modalidade_obj.id if modalidade_obj else None
        militar_a_disposicao.inicio_periodo = parse_date_flex(
            form_militar.inicio_periodo.data)
        militar_a_disposicao.fim_periodo_disposicao = parse_date_flex(
            form_militar.fim_periodo.data)
        militar_a_disposicao.publicacao_bg_id = bg_id
        militar_a_disposicao.atualizar_status()
    else:
        encerrar_disposicao_vigente(militar.id)

    # LE
    if modalidade_nome == "LICENÇA ESPECIAL":
        inicio_le = parse_date_flex(form_militar.inicio_periodo.data)
        fim_le = parse_date_flex(form_militar.fim_periodo.data)

        militar_le = LicencaEspecial.query.filter(
            LicencaEspecial.militar_id == militar.id,
            LicencaEspecial.inicio_periodo_le == inicio_le,
            LicencaEspecial.fim_periodo_le == fim_le,
        ).first()

        if not militar_le:
            militar_le = LicencaEspecial(militar_id=militar.id)
            database.session.add(militar_le)

        militar_le.posto_grad_id = form_militar.posto_grad_id.data
        militar_le.quadro_id = form_militar.quadro_id.data
        militar_le.destino_id = form_militar.destino_id.data
        militar_le.modalidade_id = modalidade_obj.id if modalidade_obj else None
        militar_le.inicio_periodo_le = inicio_le
        militar_le.fim_periodo_le = fim_le
        militar_le.publicacao_bg_id = bg_id
        militar_le.atualizar_status()
    else:
        encerrar_le_vigente(militar.id)

    # LTS
    if modalidade_nome == "LTS":
        militar_lts = LicencaParaTratamentoDeSaude.query.filter_by(
            militar_id=militar.id).first()
        if not militar_lts:
            militar_lts = LicencaParaTratamentoDeSaude(militar_id=militar.id)
            database.session.add(militar_lts)

        militar_lts.posto_grad_id = form_militar.posto_grad_id.data
        militar_lts.quadro_id = form_militar.quadro_id.data
        militar_lts.destino_id = form_militar.destino_id.data
        militar_lts.modalidade_id = modalidade_obj.id if modalidade_obj else None
        militar_lts.inicio_periodo_lts = parse_date_flex(
            form_militar.inicio_periodo.data)
        militar_lts.fim_periodo_lts = parse_date_flex(
            form_militar.fim_periodo.data)
        militar_lts.publicacao_bg_id = bg_id
        militar_lts.atualizar_status()
    else:
        encerrar_lts_vigente(militar.id)
