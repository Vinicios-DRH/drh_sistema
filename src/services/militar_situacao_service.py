from datetime import date, datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

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
        # Reaproveita a LTS ainda vigente (sem fim, ou fim >= hoje), igual ao
        # que já é feito pra Agregação/Disposição. Sem esse filtro de
        # vigência, cairia sempre na primeira LTS que o militar já teve na
        # vida — e reeditar uma LTS nova sobrescreveria (apagaria) o
        # histórico de uma LTS antiga e já encerrada.
        militar_lts = LicencaParaTratamentoDeSaude.query.filter(
            LicencaParaTratamentoDeSaude.militar_id == militar.id,
            or_(
                LicencaParaTratamentoDeSaude.fim_periodo_lts.is_(None),
                LicencaParaTratamentoDeSaude.fim_periodo_lts >= hoje
            )
        ).order_by(LicencaParaTratamentoDeSaude.id.desc()).first()
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


# ---------------------------------------------------------------------------
# SITUAÇÕES EXTRAS
#
# `sincronizar_blocos_funcionais` (acima) trata a situação do militar como
# um "slot" só: qualquer modalidade que não seja a selecionada no formulário
# principal é encerrada (`encerrar_*_vigente`). Isso é correto pra situação
# principal, mas não dá margem pra um caso real: o militar está de LTS
# (vigente agora) e sai uma publicação de Licença Especial que ele só vai
# tirar ano que vem — não dá pra registrar isso trocando a situação
# principal, porque encerraria a LTS que ainda está em curso.
#
# As funções abaixo resolvem isso criando um registro adicional direto na
# tabela certa (Agregação/Disposição/Licença Especial/LTS), sem passar pelo
# `sincronizar_blocos_funcionais` e sem tocar nos campos de situação
# principal do Militar. Cada situação extra vira sua própria linha, com sua
# própria publicação — nada é sobrescrito ou encerrado.
# ---------------------------------------------------------------------------

SITUACAO_EXTRA_CONFIG = {
    "AGREGACAO": {
        "model": MilitaresAgregados,
        "label": "Agregação",
        "campo_inicio": "inicio_periodo",
        "campo_fim": "fim_periodo_agregacao",
        "modalidade_descricao": "AGREGADO",
    },
    "A_DISPOSICAO": {
        "model": MilitaresADisposicao,
        "label": "À Disposição",
        "campo_inicio": "inicio_periodo",
        "campo_fim": "fim_periodo_disposicao",
        "modalidade_descricao": "À DISPOSIÇÃO",
    },
    "LICENCA_ESPECIAL": {
        "model": LicencaEspecial,
        "label": "Licença Especial",
        "campo_inicio": "inicio_periodo_le",
        "campo_fim": "fim_periodo_le",
        "modalidade_descricao": "LICENÇA ESPECIAL",
    },
    "LTS": {
        "model": LicencaParaTratamentoDeSaude,
        "label": "LTS",
        "campo_inicio": "inicio_periodo_lts",
        "campo_fim": "fim_periodo_lts",
        "modalidade_descricao": "LTS",
    },
}


def criar_situacao_extra(militar, tipo, destino_id, inicio, fim, publicacao_texto=None):
    """Cria uma situação adicional (Agregação, À Disposição, Licença Especial
    ou LTS) pro militar sem mexer na situação principal e sem encerrar
    nenhuma outra situação em curso. Levanta ValueError se os dados
    obrigatórios não vierem preenchidos.

    Não comita a sessão — quem chama decide o commit.
    """
    config = SITUACAO_EXTRA_CONFIG.get(tipo)
    if not config:
        raise ValueError("Tipo de situação extra inválido.")
    if not inicio:
        raise ValueError("Informe a data de início da situação extra.")

    modalidade_obj = Modalidade.query.filter_by(
        descricao=config["modalidade_descricao"]).first()

    publicacao_texto = (publicacao_texto or "").strip()
    publicacao_bg_id = None
    if publicacao_texto:
        publicacao = PublicacaoBg(
            militar_id=militar.id,
            tipo_bg=f"extra_{tipo.lower()}",
            boletim_geral=publicacao_texto,
        )
        database.session.add(publicacao)
        database.session.flush()
        publicacao_bg_id = publicacao.id

    registro = config["model"](
        militar_id=militar.id,
        posto_grad_id=militar.posto_grad_id,
        quadro_id=militar.quadro_id,
        destino_id=destino_id,
        modalidade_id=modalidade_obj.id if modalidade_obj else None,
        publicacao_bg_id=publicacao_bg_id,
        situacao_extra=True,
    )
    setattr(registro, config["campo_inicio"], inicio)
    setattr(registro, config["campo_fim"], fim)
    registro.atualizar_status()

    database.session.add(registro)
    return registro


def listar_situacoes_extras(militar_id, limite=None):
    """Todas as situações (Agregação, À Disposição, Licença Especial, LTS) já
    registradas pro militar, juntas numa lista só, mais recente primeiro —
    prévia rápida na própria ficha do militar. O histórico completo, com
    mais detalhe por seção, mora em src.services.historico_militar_service."""
    itens = []
    for tipo, config in SITUACAO_EXTRA_CONFIG.items():
        registros = (
            config["model"].query
            .options(joinedload(config["model"].destino), joinedload(config["model"].publicacao_bg))
            .filter_by(militar_id=militar_id)
            .all()
        )
        for registro in registros:
            itens.append({
                "tipo": tipo,
                "label": config["label"],
                "inicio": getattr(registro, config["campo_inicio"]),
                "fim": getattr(registro, config["campo_fim"]),
                "status": registro.status,
                "destino": registro.destino.local if registro.destino else None,
                "publicacao": registro.publicacao_bg.boletim_geral if registro.publicacao_bg else None,
            })

    itens.sort(key=lambda item: item["inicio"] or date.min, reverse=True)
    if limite:
        itens = itens[:limite]
    return itens


# Pra qual "situação" (o campo de 3 valores: PRONTO/AGREGADO/À DISPOSIÇÃO) a
# promoção de cada tipo de situação extra deve levar o militar. Licença
# Especial e LTS não têm valor próprio nesse campo — igual já acontece hoje
# pra quem está de LTS pela situação principal (fica "PRONTO" mesmo estando
# de licença; quem marca isso é o `modalidade_id`).
SITUACAO_EXTRA_PARA_SITUACAO_PRINCIPAL = {
    "AGREGACAO": "AGREGADO",
    "A_DISPOSICAO": "À DISPOSIÇÃO",
    "LICENCA_ESPECIAL": "PRONTO",
    "LTS": "PRONTO",
}

_ENCERRAR_POR_TIPO = {
    "AGREGACAO": encerrar_agregacao_vigente,
    "A_DISPOSICAO": encerrar_disposicao_vigente,
    "LICENCA_ESPECIAL": encerrar_le_vigente,
    "LTS": encerrar_lts_vigente,
}


def processar_inicio_situacoes_extras(militar_id=None):
    """Quando uma situação extra (criada via `criar_situacao_extra`, sem
    mexer na situação principal) está "Vigente" e ainda não é a situação
    principal do militar, ela assume o posto — é assim que, por exemplo,
    uma Licença Especial futura registrada enquanto o militar ainda estava
    de LTS passa a valer sozinha quando chega a vez dela, sem que ninguém
    precise entrar manualmente na ficha pra trocar a situação.

    Só olha registros com `situacao_extra=True` — os criados pela situação
    principal (tela de exibir-militar) já são mantidos em dia pelo
    `sincronizar_blocos_funcionais` e não entram nessa varredura.

    Sem `militar_id`, varre todo mundo (telas de listagem). Com `militar_id`,
    fica restrito a um único militar — mais barato pra rodar a cada
    visita à ficha dele.

    A checagem é "está Vigente e ainda não bate com a situação principal
    atual" (não só "acabou de virar Vigente agora"), porque uma situação
    extra pode ser cadastrada já com início no passado/hoje — nesse caso ela
    precisa assumir na hora, sem esperar uma futura mudança de status. Uma
    vez promovida, os campos do militar passam a bater exatamente com o
    registro, então a checagem já não dispara de novo (idempotente). Ao
    promover, encerra qualquer outra modalidade que ainda estivesse vigente
    (mesma regra de exclusividade que já vale pra situação principal).

    Não comita a sessão — quem chama decide o commit.
    Retorna a lista de militares promovidos.
    """
    militares_promovidos = []

    for tipo, config in SITUACAO_EXTRA_CONFIG.items():
        query = config["model"].query.filter_by(situacao_extra=True)
        if militar_id is not None:
            query = query.filter_by(militar_id=militar_id)
        registros = query.all()
        for registro in registros:
            registro.atualizar_status()
            if registro.status != "Vigente":
                continue

            militar = registro.militar
            if militar is None:
                continue

            ja_e_a_principal = (
                militar.modalidade_id == registro.modalidade_id
                and militar.inicio_periodo == getattr(registro, config["campo_inicio"])
            )
            if ja_e_a_principal:
                continue

            for outro_tipo, encerrar in _ENCERRAR_POR_TIPO.items():
                if outro_tipo != tipo:
                    encerrar(militar.id)

            militar.situacao = SITUACAO_EXTRA_PARA_SITUACAO_PRINCIPAL[tipo]
            militar.modalidade_id = registro.modalidade_id
            militar.destino_id = registro.destino_id or militar.destino_id
            militar.inicio_periodo = getattr(registro, config["campo_inicio"])
            militar.fim_periodo = getattr(registro, config["campo_fim"])

            militares_promovidos.append(militar)

    return militares_promovidos
