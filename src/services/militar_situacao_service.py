from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from src import database
from src.models import (
    Militar,
    Modalidade,
    Motivo,
    PublicacaoBg,
    MilitaresAgregados,
    MilitaresADisposicao,
    LicencaEspecial,
    LicencaParaTratamentoDeSaude,
    MilitarObmFuncao,
    Funcao,
    Obm,
    DESTINO_DEFESA_CIVIL_ID,
)

# (função, sigla da OBM) do Comandante-Geral, Subcomandante-Geral e Chefe do
# Estado-Maior Geral. Os três têm Situação/Modalidade de Agregado/À
# Disposição só por formalidade administrativa do posto — não representam um
# "emprestado a outro órgão" de verdade, então não contam nos módulos
# operacionais de Agregados/À Disposição (dashboards, listagens e filtro de
# /militares). Por função+OBM (não por militar_id) pra acompanhar quem quer
# que ocupe o cargo — "SUBCOMANDANTE" sozinho pegaria também os
# subcomandantes de OBM (um cargo comum em várias unidades), por isso o
# pareamento com a OBM certa é obrigatório.
_ALTO_COMANDO_FUNCAO_OBM = (
    ("COMANDANTE GERAL", "GAB CMT GERAL"),
    ("SUBCOMANDANTE", "GAB SUBCMT-GERAL"),
    ("CHEFE DO ESTADO MAIOR", "EMG"),
)


def ids_alto_comando_excluidos_de_agregado_disposicao():
    """Ids dos militares no alto comando (ver `_ALTO_COMANDO_FUNCAO_OBM`) que
    devem ficar de fora das contagens/listagens de Agregados e À Disposição."""
    ids = set()
    for funcao_nome, obm_sigla in _ALTO_COMANDO_FUNCAO_OBM:
        vinculos = (
            MilitarObmFuncao.query
            .join(Funcao, Funcao.id == MilitarObmFuncao.funcao_id)
            .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
            .filter(MilitarObmFuncao.data_fim.is_(None))
            .filter(Funcao.ocupacao == funcao_nome, Obm.sigla == obm_sigla)
            .with_entities(MilitarObmFuncao.militar_id)
            .all()
        )
        ids.update(mid for (mid,) in vinculos)
    return ids


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


def obter_publicacao_bg_id(militar_id, tipo_bg="boletim_geral"):
    """A publicação mais recente desse tipo pro militar. Pode haver mais de
    uma linha (uma por situação já registrada — ver
    src.services.militar_cadastro_service._salvar_publicacoes_bg), então o
    order_by garante que é sempre a atual que volta, não uma antiga."""
    bg = (
        PublicacaoBg.query
        .filter_by(militar_id=militar_id, tipo_bg=tipo_bg)
        .order_by(PublicacaoBg.id.desc())
        .first()
    )
    return bg.id if bg else None


def _mapa_publicacao_bg_atual(militar_ids, tipo_bg) -> dict:
    """Texto do PublicacaoBg mais recente de um `tipo_bg` (ex.: 'doe',
    'boletim_geral') pra cada militar em `militar_ids`, numa consulta só —
    pras telas de listagem (/militares, /tabela-militares, exportação)
    mostrarem/filtrarem sem um SELECT por militar. Maior id vence, mesmo
    critério usado em todo lugar que resolve "qual é o valor atual" de um
    PublicacaoBg."""
    ids = [mid for mid in (militar_ids or []) if mid]
    if not ids:
        return {}

    linhas = (
        database.session.query(
            PublicacaoBg.militar_id,
            PublicacaoBg.boletim_geral,
            func.row_number().over(
                partition_by=PublicacaoBg.militar_id,
                order_by=PublicacaoBg.id.desc(),
            ).label("linha"),
        )
        .filter(PublicacaoBg.tipo_bg == tipo_bg, PublicacaoBg.militar_id.in_(ids))
        .subquery()
    )

    linhas_mais_recentes = (
        database.session.query(linhas.c.militar_id, linhas.c.boletim_geral)
        .filter(linhas.c.linha == 1)
        .all()
    )

    return {militar_id: (boletim_geral or "") for militar_id, boletim_geral in linhas_mais_recentes}


def mapa_doe_atual(militar_ids) -> dict:
    """DOE atual (texto do PublicacaoBg mais recente com tipo_bg='doe') de
    cada militar em `militar_ids`. Ver `_mapa_publicacao_bg_atual`."""
    return _mapa_publicacao_bg_atual(militar_ids, "doe")


def mapa_boletim_geral_atual(militar_ids) -> dict:
    """Boletim Geral atual da Situação Funcional (texto do PublicacaoBg mais
    recente com tipo_bg='boletim_geral' — o campo que aparece como
    "Boletim Geral" na ficha do militar) de cada militar em `militar_ids`.
    Ver `_mapa_publicacao_bg_atual`."""
    return _mapa_publicacao_bg_atual(militar_ids, "boletim_geral")


def militares_com_doe_contendo(texto: str):
    """Ids de militares cujo DOE (qualquer entrada do histórico, não só a
    atual) contém `texto` — usado pra busca textual em /militares e
    /tabela-militares achar alguém pelo número do Diário Oficial, mesmo que
    já tenha sido substituído por uma publicação mais nova."""
    if not (texto or "").strip():
        return []
    termo = f"%{texto.strip()}%"
    linhas = (
        database.session.query(PublicacaoBg.militar_id)
        .filter(PublicacaoBg.tipo_bg == "doe", PublicacaoBg.boletim_geral.ilike(termo))
        .distinct()
        .all()
    )
    return [militar_id for (militar_id,) in linhas]


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


# Modalidade "PRONTO", motivo "SEM AGREGAÇÕES" e destino "CBMAM" — para onde
# o militar volta automaticamente quando a situação em curso (Agregação, À
# Disposição, Licença Especial ou LTS) termina.
MODALIDADE_PRONTO_ID = 8
MOTIVO_SEM_AGREGACOES_ID = 1
DESTINO_CBMAM_ID = 6

# Modalidade "À DISPOSIÇÃO" — é o campo que sincronizar_blocos_funcionais usa
# pra decidir se o bloco de À Disposição se aplica (ver nota lá).
MODALIDADE_A_DISPOSICAO_ID = 2


def militar_com_modalidade_a_disposicao_expr():
    """True só quando a Modalidade ATUAL da ficha do militar ainda é "À
    DISPOSIÇÃO" — é o mesmo campo que `sincronizar_blocos_funcionais` usa
    pra decidir se grava/mantém um registro em MilitaresADisposicao.

    Por que não basta olhar o registro mais recente (com o período dele já
    vencido, por exemplo) pra decidir se ainda é relevante: quando o
    operador salva a ficha trocando a Modalidade pra outra coisa (ex.:
    "AGUARDANDO"), `encerrar_disposicao_vigente` fecha o registro antigo
    (fim = ontem) — só que ele continua sendo "o mais recente com início
    preenchido" pra sempre. Sem checar a Modalidade atual, esse registro já
    resolvido nunca sai do painel de À Disposição, mesmo a ficha já
    apontando pra outro lugar (ex.: Agregado aguardando RR).

    Isso NÃO esconde uma disposição vencida ainda pendente de decisão: se o
    operador ainda não mexeu na ficha, a Modalidade continua "À DISPOSIÇÃO"
    (só muda quando alguém explicitamente salva outra coisa), então essas
    pendências continuam aparecendo normalmente."""
    return Militar.modalidade_id == MODALIDADE_A_DISPOSICAO_ID


def militar_com_situacao_agregado_expr():
    """Equivalente a `militar_com_modalidade_a_disposicao_expr`, mas pro
    painel de Agregados: só considera relevante quem tem Situação=AGREGADO
    na ficha AGORA (mesmo campo que decide o bloco de Agregação em
    sincronizar_blocos_funcionais).

    Usa `coalesce`/comparação com string vazia em vez de `==` direto porque
    em SQL `coluna = valor` dá NULL (não True/False) quando a coluna é
    NULL — sem isso um militar com Situação em branco poderia se comportar
    de um jeito inesperado dependendo de como a comparação é usada."""
    return func.upper(func.trim(func.coalesce(Militar.situacao, ""))) == "AGREGADO"


def _reverter_militar_para_pronto(militar):
    """Devolve o militar pra PRONTO/SEM AGREGAÇÕES/CBMAM, com as datas de
    início/término e a publicação da Situação Funcional limpas — chamado
    quando a situação em curso já passou da data de término.

    O registro que estava vigente (Agregação/À Disposição/Licença Especial/
    LTS), com sua publicação original, não é tocado: continua intacto no
    banco como histórico. A publicação também não é apagada — pra "limpar"
    o campo sem perder o texto de quem ainda aponta pra ele, cria uma linha
    nova vazia (mesma regra de nunca dar UPDATE numa linha já existente, ver
    _salvar_publicacoes_bg em militar_cadastro_service.py)."""
    militar.situacao = "PRONTO"
    militar.modalidade_id = MODALIDADE_PRONTO_ID
    militar.motivo_id = MOTIVO_SEM_AGREGACOES_ID
    militar.destino_id = DESTINO_CBMAM_ID
    militar.inicio_periodo = None
    militar.fim_periodo = None

    bg_atual = (
        PublicacaoBg.query
        .filter_by(militar_id=militar.id, tipo_bg="boletim_geral")
        .order_by(PublicacaoBg.id.desc())
        .first()
    )
    if bg_atual and bg_atual.boletim_geral:
        database.session.add(PublicacaoBg(
            militar_id=militar.id, tipo_bg="boletim_geral", boletim_geral=None))


# ---------------------------------------------------------------------------
# PENDÊNCIAS DE DISPOSIÇÃO VENCIDA
#
# Disposição sempre tem uma data de término (~1 ano); Agregação nunca tem.
# Quando o militar está só à disposição, a Disposição vencer significa que a
# situação cessou. Quando está Agregado E à disposição ao mesmo tempo, a
# Disposição vencer não encerra nada sozinha — a Agregação continua aberta
# até uma decisão explícita: o órgão manda prorrogar (o operador atualiza a
# data de término, publicação e DOE) ou sai uma portaria revertendo a
# agregação (o militar volta pra PRONTO). Nenhuma das duas decisões pode ser
# tomada automaticamente por data — precisa perguntar pro operador. Essas
# funções alimentam esse "pergunte ao operador" nas telas /militares-a-
# disposicao e /militares-agregados.
# ---------------------------------------------------------------------------

def listar_pendencias_disposicao_vencida():
    """Militares (deduplicados pelo registro mais recente, sem o alto
    comando, sem inativos) cuja Disposição já venceu por data mas cuja
    Situação ainda não foi atualizada pelo operador. Cada item indica se é
    "dual" (tem uma Agregação aberta junto) ou "solo" (só à disposição),
    porque a ação certa muda conforme o caso."""
    from src.services.situacoes_militares_service import _ids_mais_recentes_por_militar

    hoje = date.today()
    excluidos = ids_alto_comando_excluidos_de_agregado_disposicao()

    disposicoes = (
        MilitaresADisposicao.query
        .join(Militar, Militar.id == MilitaresADisposicao.militar_id)
        .filter(Militar.inativo.is_(False))
        .filter(MilitaresADisposicao.id.in_(_ids_mais_recentes_por_militar(MilitaresADisposicao)))
        .filter(MilitaresADisposicao.militar_id.notin_(excluidos))
        # Defesa Civil não tem vencimento — nunca é pendência (ver
        # DESTINO_DEFESA_CIVIL_ID em models.py). `!=` puro excluiria também
        # quem não tem destino nenhum (NULL != 24 é NULL em SQL, não True).
        .filter(or_(
            MilitaresADisposicao.destino_id != DESTINO_DEFESA_CIVIL_ID,
            MilitaresADisposicao.destino_id.is_(None),
        ))
        # Se a Modalidade da ficha já não é mais "À DISPOSIÇÃO", o operador
        # já resolveu isso salvando outra coisa (PRONTO, Agregado aguardando
        # RR, etc.) — não é mais uma pendência, é só o histórico de uma
        # situação já resolvida.
        .filter(militar_com_modalidade_a_disposicao_expr())
        .filter(MilitaresADisposicao.fim_periodo_disposicao.isnot(None))
        .filter(MilitaresADisposicao.fim_periodo_disposicao < hoje)
        .options(
            joinedload(MilitaresADisposicao.militar),
            joinedload(MilitaresADisposicao.destino),
            joinedload(MilitaresADisposicao.publicacao_bg),
        )
        .all()
    )

    pendencias = []
    for disp in disposicoes:
        militar = disp.militar
        if militar is None:
            continue
        agregacao_aberta = (
            MilitaresAgregados.query
            .filter(MilitaresAgregados.militar_id == militar.id)
            .filter(or_(
                MilitaresAgregados.fim_periodo_agregacao.is_(None),
                MilitaresAgregados.fim_periodo_agregacao >= hoje,
            ))
            .order_by(MilitaresAgregados.id.desc())
            .first()
        )
        sugestao_inicio = disp.fim_periodo_disposicao + timedelta(days=1)
        pendencias.append({
            "militar": militar,
            "disposicao": disp,
            "dual": agregacao_aberta is not None,
            "agregacao": agregacao_aberta,
            "dias_vencido": (hoje - disp.fim_periodo_disposicao).days,
            "sugestao_inicio": sugestao_inicio,
            "sugestao_fim": sugestao_inicio + relativedelta(years=1),
        })

    pendencias.sort(key=lambda p: p["dias_vencido"], reverse=True)
    return pendencias


def prorrogar_disposicao(militar, novo_inicio, novo_fim, publicacao_texto, doe_texto=None):
    """Prorroga a Disposição do militar: cria um registro NOVO em
    MilitaresADisposicao (o vencido continua intacto como histórico — nunca
    dá UPDATE numa linha já existente), com a publicação/DOE da prorrogação
    também como linha nova. Não mexe na Agregação (se houver) nem na
    Situação/Modalidade do militar — só o período de disposição muda.
    Não comita a sessão — quem chama decide o commit."""
    disposicao_anterior = (
        MilitaresADisposicao.query
        .filter_by(militar_id=militar.id)
        .order_by(MilitaresADisposicao.id.desc())
        .first()
    )

    nova = MilitaresADisposicao(
        militar_id=militar.id,
        posto_grad_id=militar.posto_grad_id,
        quadro_id=militar.quadro_id,
        destino_id=disposicao_anterior.destino_id if disposicao_anterior else militar.destino_id,
        modalidade_id=disposicao_anterior.modalidade_id if disposicao_anterior else militar.modalidade_id,
        inicio_periodo=novo_inicio,
        fim_periodo_disposicao=novo_fim,
    )

    publicacao_texto = (publicacao_texto or "").strip()
    if publicacao_texto:
        publicacao = PublicacaoBg(
            militar_id=militar.id, tipo_bg="boletim_geral", boletim_geral=publicacao_texto)
        database.session.add(publicacao)
        database.session.flush()
        nova.publicacao_bg_id = publicacao.id

    nova.atualizar_status()
    database.session.add(nova)

    doe_texto = (doe_texto or "").strip()
    if doe_texto:
        database.session.add(PublicacaoBg(
            militar_id=militar.id, tipo_bg="doe", boletim_geral=doe_texto))

    # Situação/Modalidade continuam as mesmas — só o período espelhado no
    # militar acompanha a nova disposição (é a mesma coisa que salvar a
    # ficha de novo com as datas atualizadas).
    militar.inicio_periodo = novo_inicio
    militar.fim_periodo = novo_fim

    return nova


def reverter_disposicao(militar, data_reversao, publicacao_texto, doe_texto=None):
    """Encerra a Disposição vigente (e a Agregação, se estiver aberta junto)
    e devolve o militar pra PRONTO — usado quando NÃO houve prorrogação:
    "cessação" se o militar estava só à disposição, "reversão" se estava
    Agregado e à disposição ao mesmo tempo. A publicação/DOE informados são
    da portaria que formaliza isso (histórico, nunca sobrescreve).
    Não comita a sessão — quem chama decide o commit."""
    disposicao = (
        MilitaresADisposicao.query
        .filter_by(militar_id=militar.id)
        .order_by(MilitaresADisposicao.id.desc())
        .first()
    )
    if disposicao and (
        not disposicao.fim_periodo_disposicao
        or disposicao.fim_periodo_disposicao >= data_reversao
    ):
        disposicao.fim_periodo_disposicao = data_reversao
        disposicao.atualizar_status()

    agregacao = (
        MilitaresAgregados.query
        .filter_by(militar_id=militar.id)
        .order_by(MilitaresAgregados.id.desc())
        .first()
    )
    if agregacao and (
        not agregacao.fim_periodo_agregacao
        or agregacao.fim_periodo_agregacao >= data_reversao
    ):
        agregacao.fim_periodo_agregacao = data_reversao
        agregacao.atualizar_status()

    militar.situacao = "PRONTO"
    militar.modalidade_id = MODALIDADE_PRONTO_ID
    militar.motivo_id = MOTIVO_SEM_AGREGACOES_ID
    militar.destino_id = DESTINO_CBMAM_ID
    militar.inicio_periodo = None
    militar.fim_periodo = None

    publicacao_texto = (publicacao_texto or "").strip()
    if publicacao_texto:
        database.session.add(PublicacaoBg(
            militar_id=militar.id, tipo_bg="boletim_geral", boletim_geral=publicacao_texto))

    doe_texto = (doe_texto or "").strip()
    if doe_texto:
        database.session.add(PublicacaoBg(
            militar_id=militar.id, tipo_bg="doe", boletim_geral=doe_texto))


def processar_fim_de_lts(militar_id=None):
    """Atualiza o status das LTS (recalculado a partir de hoje) e devolve o
    militar pra PRONTO em toda LTS já vencida que ainda seja a que o card de
    Situação Funcional dele reflete como atual — verificado batendo
    modalidade E as datas espelhadas em `militar.inicio_periodo`/
    `fim_periodo` com as da LTS (evita reverter por engano quando o militar
    já está numa LTS *nova*, com modalidade igual mas período diferente, ou
    quando outra pessoa já mudou a situação dele manualmente).

    Não é "só a que acabou de vencer nesta chamada": qualquer LTS parada há
    meses sem ninguém ter reaberto a ficha do militar também precisa ser
    pega aqui — por isso o gatilho é o estado atual (`status == "Término
    ..."`), não uma transição.

    `militar_id` restringe a varredura a um único militar (usado ao abrir a
    ficha dele); sem isso, varre todo mundo (usado nas telas de listagem).
    Não comita a sessão — quem chama decide o commit.
    Retorna a lista de militares que foram promovidos de volta a PRONTO.
    """
    query = LicencaParaTratamentoDeSaude.query
    if militar_id is not None:
        query = query.filter_by(militar_id=militar_id)
    todas = query.all()

    militares_promovidos = []
    for lts in todas:
        lts.atualizar_status()
        if lts.status != "Término da Licença para Tratamento de Saúde":
            continue

        militar = lts.militar
        eh_a_situacao_atual_do_militar = (
            militar is not None
            and lts.modalidade_id is not None
            and militar.modalidade_id == lts.modalidade_id
            and militar.inicio_periodo == lts.inicio_periodo_lts
            and militar.fim_periodo == lts.fim_periodo_lts
        )
        if eh_a_situacao_atual_do_militar:
            _reverter_militar_para_pronto(militar)
            militares_promovidos.append(militar)

    return militares_promovidos


def processar_fim_de_agregacao(militar_id=None):
    """Recalcula o status ("Término de Agregação" etc.) dos registros de
    Agregação. NÃO reverte o militar pra PRONTO — a reversão automática de
    situação só se aplica à LTS (ver `processar_fim_de_lts`); em Agregação e
    À Disposição ela atrapalhava o serviço, então foi desativada aqui."""
    query = MilitaresAgregados.query
    if militar_id is not None:
        query = query.filter_by(militar_id=militar_id)
    todas = query.all()

    for reg in todas:
        reg.atualizar_status()

    return []


def processar_fim_de_disposicao(militar_id=None):
    """Recalcula o status ("Venceu" etc.) dos registros de À Disposição. NÃO
    reverte o militar pra PRONTO — ver nota em `processar_fim_de_agregacao`."""
    query = MilitaresADisposicao.query
    if militar_id is not None:
        query = query.filter_by(militar_id=militar_id)
    todas = query.all()

    for reg in todas:
        reg.atualizar_status()

    return []


def processar_fim_de_le(militar_id=None):
    """Recalcula o status ("Término da Licença Especial" etc.) dos registros
    de Licença Especial. NÃO reverte o militar pra PRONTO — a reversão
    automática ficou restrita à LTS (ver `processar_fim_de_lts`)."""
    query = LicencaEspecial.query
    if militar_id is not None:
        query = query.filter_by(militar_id=militar_id)
    todas = query.all()

    for reg in todas:
        reg.atualizar_status()

    return []


def processar_fim_de_situacao_militar(militar_id):
    """Roda as quatro varreduras de fim de situação (Agregação, À
    Disposição, Licença Especial, LTS) pra um único militar — chamado ao
    abrir a ficha dele. Só a varredura de LTS reverte o militar pra PRONTO
    automaticamente; as outras três só atualizam o status do próprio
    registro (ex.: "Venceu"), sem mexer na situação do militar.
    Não comita a sessão — quem chama decide o commit."""
    processar_fim_de_agregacao(militar_id=militar_id)
    processar_fim_de_disposicao(militar_id=militar_id)
    processar_fim_de_le(militar_id=militar_id)
    processar_fim_de_lts(militar_id=militar_id)


def sincronizar_blocos_funcionais(militar, form_militar):
    hoje = date.today()

    modalidade_obj = obter_modalidade_por_id(form_militar.modalidade_id.data)
    modalidade_nome = normalizar_str(
        modalidade_obj.descricao if modalidade_obj else None)
    situacao_principal = normalizar_str(form_militar.situacao.data)

    # Só usado pra LIGAR um registro que ainda não tem publicacao_bg_id (é
    # novo, ou nunca foi vinculado). Um registro que já está vinculado nunca
    # é religado aqui, mesmo que bg_id aponte pra uma linha mais nova agora —
    # senão qualquer save do cadastro (mesmo sem mexer na situação) troca
    # silenciosamente o que a licença/agregação/disposição/LTS ainda vigente
    # mostra como sua publicação, só porque o campo "Publicação" da Situação
    # Funcional foi editado ou limpo por outro motivo.
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
        # Agregação nunca tem data de término — só é encerrada por um ato
        # administrativo explícito (portaria de reversão), nunca por data
        # passando. Isso vale mesmo quando o militar está Agregado E à
        # disposição ao mesmo tempo: quem tem prazo é a Disposição (bloco
        # abaixo), não a Agregação. Ver reverter_disposicao/prorrogar_disposicao.
        militar_agregado.fim_periodo_agregacao = None
        if not militar_agregado.publicacao_bg_id:
            militar_agregado.publicacao_bg_id = bg_id
        militar_agregado.atualizar_status()
    else:
        encerrar_agregacao_vigente(militar.id)

    # À DISPOSIÇÃO
    # Gatilho é a Modalidade, não a Situação — de propósito: um militar pode
    # estar simultaneamente Situação=AGREGADO (agregado a um órgão) e
    # Modalidade=À DISPOSIÇÃO (à disposição desse mesmo órgão), caso legítimo
    # e comum na corporação. Por isso as duas checagens usam campos
    # diferentes: Agregação por Situação, À Disposição por Modalidade — não
    # são mutuamente exclusivas.
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
        if militar_a_disposicao.destino_id == DESTINO_DEFESA_CIVIL_ID:
            # Defesa Civil nunca vence — o militar pode ficar lá
            # indefinidamente. Enquanto o destino continuar Defesa Civil,
            # `fim_periodo_disposicao` fica sempre em aberto (None); só passa
            # a valer de novo se/quando `encerrar_disposicao_vigente` fechar
            # este registro porque o militar saiu de lá.
            militar_a_disposicao.fim_periodo_disposicao = None
        else:
            militar_a_disposicao.fim_periodo_disposicao = parse_date_flex(
                form_militar.fim_periodo.data)
        if not militar_a_disposicao.publicacao_bg_id:
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
        if not militar_le.publicacao_bg_id:
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
        if not militar_lts.publicacao_bg_id:
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


def mapa_situacoes_extras_vigentes(militar_ids):
    """Pra um conjunto de militar_id, a situação extra (`situacao_extra=True`)
    VIGENTE de cada um agora, se houver — uma consulta por tabela (não uma
    por militar), pra usar nos painéis de Agregados/À Disposição, onde
    precisa saber "esse militar, além do que já aparece na tabela, também
    está de LTS/Licença Especial/Agregação/À Disposição extra ao mesmo
    tempo?" sem rodar centenas de queries. Se um militar tiver mais de uma
    extra vigente ao mesmo tempo, fica só a de fim mais distante (a que
    "dura mais")."""
    if not militar_ids:
        return {}

    militar_ids = set(militar_ids)
    hoje = date.today()
    mapa = {}

    for tipo, config in SITUACAO_EXTRA_CONFIG.items():
        campo_inicio_col = getattr(config["model"], config["campo_inicio"])
        campo_fim_col = getattr(config["model"], config["campo_fim"])
        registros = (
            config["model"].query
            .filter(config["model"].militar_id.in_(militar_ids))
            .filter(config["model"].situacao_extra.is_(True))
            .filter(campo_inicio_col.isnot(None))
            .filter(campo_inicio_col <= hoje)
            .filter(or_(campo_fim_col.is_(None), campo_fim_col >= hoje))
            .options(joinedload(config["model"].destino))
            .all()
        )
        for registro in registros:
            fim = getattr(registro, config["campo_fim"])
            atual = mapa.get(registro.militar_id)
            if atual is not None:
                if atual["fim"] is None:
                    continue  # atual já é "sem prazo" — nada supera
                if fim is not None and fim <= atual["fim"]:
                    continue  # atual dura mais (ou igual) — mantém
            mapa[registro.militar_id] = {
                "tipo": tipo,
                "label": config["label"],
                "inicio": getattr(registro, config["campo_inicio"]),
                "fim": fim,
                "destino": registro.destino.local if registro.destino else None,
            }

    return mapa


def listar_situacoes_extras(militar_id, limite=None):
    """Situações extras (`situacao_extra=True` — Agregação, À Disposição,
    Licença Especial ou LTS registradas sem mexer na situação principal) já
    cadastradas pro militar, juntas numa lista só, mais recente primeiro —
    prévia rápida na própria ficha do militar. NÃO inclui a situação
    principal em si (essa já aparece nos campos de Situação/Modalidade/
    Destino ali em cima) — sem esse filtro, o registro principal do militar
    aparecia aqui também, e com o destaque novo de "vigente" ficava parecendo
    uma situação extra em andamento quando na verdade é só a principal.
    O histórico completo, com mais detalhe por seção, mora em
    src.services.historico_militar_service."""
    itens = []
    for tipo, config in SITUACAO_EXTRA_CONFIG.items():
        registros = (
            config["model"].query
            .options(joinedload(config["model"].destino), joinedload(config["model"].publicacao_bg))
            .filter_by(militar_id=militar_id, situacao_extra=True)
            .all()
        )
        for registro in registros:
            inicio = getattr(registro, config["campo_inicio"])
            agendada = registro.status == "A iniciar"
            # Vigente = coexistindo com a situação principal AGORA (ver
            # processar_inicio_situacoes_extras) — precisa saltar aos olhos
            # tanto quanto uma agendada, senão o operador não percebe que o
            # militar tem duas situações rolando ao mesmo tempo.
            vigente = registro.status == "Vigente"
            itens.append({
                "tipo": tipo,
                "label": config["label"],
                "inicio": inicio,
                "fim": getattr(registro, config["campo_fim"]),
                "status": registro.status,
                "destino": registro.destino.local if registro.destino else None,
                "publicacao": registro.publicacao_bg.boletim_geral if registro.publicacao_bg else None,
                "agendada": agendada,
                "vigente": vigente,
                "dias_para_iniciar": (inicio - date.today()).days if (agendada and inicio) else None,
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


def _militar_totalmente_pronto(militar):
    """True só quando Situação E Modalidade são as duas PRONTO — mesmo
    critério usado pra decidir se um militar "já foi resolvido" nos painéis
    de Agregados/À Disposição (ver militar_com_situacao_agregado_expr /
    militar_com_modalidade_a_disposicao_expr)."""
    return (
        normalizar_str(militar.situacao) == "PRONTO"
        and militar.modalidade_id == MODALIDADE_PRONTO_ID
    )


def processar_inicio_situacoes_extras(militar_id=None):
    """Quando uma situação extra (criada via `criar_situacao_extra`, sem
    mexer na situação principal) está "Vigente", ela só assume o posto de
    situação principal se o militar estiver TOTALMENTE PRONTO (Situação E
    Modalidade) — é assim que, por exemplo, uma Licença Especial futura
    registrada enquanto o militar ainda estava de LTS passa a valer sozinha
    quando chega a vez dela, sem que ninguém precise entrar manualmente na
    ficha pra trocar a situação.

    Se o militar JÁ tem uma situação principal em curso que não é PRONTO —
    por exemplo, Agregado e à disposição ao mesmo tempo, ou só à disposição
    — a situação extra NÃO toma o lugar dela: ela continua vigente só nela
    mesma (na tabela dela), coexistindo com a principal. É o caso de alguém
    Agregado+À Disposição que também entra de LTS no destino onde está: a
    LTS fica registrada como extra, sem mexer na Agregação/Disposição em
    curso, até que o militar volte a ficar totalmente PRONTO.

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

            if not _militar_totalmente_pronto(militar):
                # Já tem uma situação principal em curso (ex.: Agregado e à
                # disposição) — a extra fica só nela mesma, coexistindo.
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
