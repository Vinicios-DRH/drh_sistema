"""Cursos CBMAM: catálogo (Curso, tabela já existente e reaproveitada aqui),
edições abertas para inscrição (CursoAndamento) e os pedidos de inscrição
dos militares (SolicitacaoInscricaoCurso).

A BM-3 (rota /cursos-cbmam/admin, acesso via
src.authz.can_manage_cursos_cbmam) cadastra o curso, abre uma edição com
prazo de inscrição, define quem pode se inscrever (combatente/saúde e quais
postos/graduações) e analisa os PDFs enviados. O militar (rota /meus-cursos)
vê as edições abertas pras quais é elegível, envia um PDF e acompanha o
parecer.
"""
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src import database
from src.decorators.utils_pdf_bucket import sanitizar_nome, upload_pdf_para_servidor
from src.models import (
    AuditoriaCursoAndamento,
    AuditoriaSolicitacaoCurso,
    Curso,
    CursoAndamento,
    CursoAndamentoPostoGrad,
    Militar,
    SolicitacaoInscricaoCurso,
    User,
)

# Mesmo critério já usado na home (obter_estatisticas_militares): a
# especialidade "COMBATENTE" é a id 3; qualquer outra especialidade conta
# como "saúde" pra fins desse filtro.
ESPECIALIDADE_COMBATENTE_ID = 3

DESTINOS_VALIDOS = {"COMBATENTE", "SAUDE", "AMBOS"}

TAMANHO_MAXIMO_PDF_BYTES = 10 * 1024 * 1024  # 10MB


# ---------------------------------------------------------------------------
# Catálogo de cursos (tabela `curso`)
# ---------------------------------------------------------------------------

def listar_cursos_base():
    return Curso.query.order_by(Curso.nome.asc()).all()


def criar_curso(nome, descricao=None):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do curso.")
    if Curso.query.filter(Curso.nome.ilike(nome)).first():
        raise ValueError(f'Já existe um curso chamado "{nome}".')

    curso = Curso(nome=nome, descricao=(descricao or "").strip() or None)
    database.session.add(curso)
    database.session.flush()
    return curso


# ---------------------------------------------------------------------------
# Edições em andamento (inscrições abertas) — visão administrativa (BM-3)
# ---------------------------------------------------------------------------

def listar_cursos_andamento():
    """Todas as edições, prazo de inscrição mais recente primeiro."""
    return (
        CursoAndamento.query
        .options(
            joinedload(CursoAndamento.curso),
            joinedload(CursoAndamento.postos_grad).joinedload(CursoAndamentoPostoGrad.posto_grad),
        )
        .order_by(CursoAndamento.data_limite_inscricao.desc())
        .all()
    )


def obter_curso_andamento(curso_andamento_id):
    return (
        CursoAndamento.query
        .options(
            joinedload(CursoAndamento.curso),
            joinedload(CursoAndamento.postos_grad).joinedload(CursoAndamentoPostoGrad.posto_grad),
            joinedload(CursoAndamento.cancelado_por).joinedload(User.militar).joinedload(Militar.posto_grad),
        )
        .filter(CursoAndamento.id == curso_andamento_id)
        .first()
    )


def _validar_datas(data_inicio, data_fim, data_limite_inscricao):
    if not data_inicio or not data_fim or not data_limite_inscricao:
        raise ValueError("Informe as três datas: início, fim e limite de inscrição.")
    if data_fim < data_inicio:
        raise ValueError("A data de término não pode ser antes da data de início.")
    if data_limite_inscricao > data_fim:
        raise ValueError("O prazo de inscrição não pode ser depois do término do curso.")


def _log_evento_andamento(andamento, evento, detalhes=None, user_id=None):
    database.session.add(AuditoriaCursoAndamento(
        curso_andamento_id=andamento.id,
        evento=evento,
        detalhes=detalhes,
        realizado_por_user_id=user_id,
    ))


def criar_curso_andamento(curso_id, data_inicio, data_fim, data_limite_inscricao,
                           destinado_a, posto_grad_ids, criado_por_user_id=None):
    """Abre uma nova edição de inscrição pro curso — a partir daqui já fica
    disponível pros militares elegíveis em /meus-cursos. O mesmo curso pode
    ganhar quantas edições forem precisas ao longo dos anos: nenhuma edição
    antiga é apagada quando uma nova é criada."""
    curso = Curso.query.get(curso_id) if curso_id else None
    if not curso:
        raise ValueError("Selecione o curso.")

    destinado_a = (destinado_a or "").strip().upper()
    if destinado_a not in DESTINOS_VALIDOS:
        raise ValueError("Selecione a quem o curso é destinado (combatente, saúde ou ambos).")

    _validar_datas(data_inicio, data_fim, data_limite_inscricao)

    posto_grad_ids = sorted({int(p) for p in (posto_grad_ids or []) if p})
    if not posto_grad_ids:
        raise ValueError("Selecione ao menos um posto/graduação elegível.")

    andamento = CursoAndamento(
        curso_id=curso.id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        data_limite_inscricao=data_limite_inscricao,
        destinado_a=destinado_a,
        criado_por_user_id=criado_por_user_id,
    )
    database.session.add(andamento)
    database.session.flush()

    for pg_id in posto_grad_ids:
        database.session.add(
            CursoAndamentoPostoGrad(curso_andamento_id=andamento.id, posto_grad_id=pg_id))

    _log_evento_andamento(
        andamento, "CRIADO",
        detalhes=(
            f"Edição aberta: {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}, "
            f"inscrições até {data_limite_inscricao.strftime('%d/%m/%Y')}, destinado a {destinado_a}."
        ),
        user_id=criado_por_user_id,
    )

    return andamento


def atualizar_curso_andamento(andamento, data_inicio, data_fim, data_limite_inscricao,
                               destinado_a, posto_grad_ids, editado_por_user_id=None):
    """A BM-3 pode reajustar prazos e critérios de uma edição já aberta."""
    destinado_a = (destinado_a or "").strip().upper()
    if destinado_a not in DESTINOS_VALIDOS:
        raise ValueError("Selecione a quem o curso é destinado (combatente, saúde ou ambos).")

    _validar_datas(data_inicio, data_fim, data_limite_inscricao)

    posto_grad_ids = sorted({int(p) for p in (posto_grad_ids or []) if p})
    if not posto_grad_ids:
        raise ValueError("Selecione ao menos um posto/graduação elegível.")

    mudancas = []
    if andamento.data_inicio != data_inicio:
        mudancas.append(
            f"Início: {andamento.data_inicio.strftime('%d/%m/%Y')} → {data_inicio.strftime('%d/%m/%Y')}")
    if andamento.data_fim != data_fim:
        mudancas.append(
            f"Término: {andamento.data_fim.strftime('%d/%m/%Y')} → {data_fim.strftime('%d/%m/%Y')}")
    if andamento.data_limite_inscricao != data_limite_inscricao:
        mudancas.append(
            f"Prazo de inscrição: {andamento.data_limite_inscricao.strftime('%d/%m/%Y')} → "
            f"{data_limite_inscricao.strftime('%d/%m/%Y')}")
    if andamento.destinado_a != destinado_a:
        mudancas.append(f"Destinado a: {andamento.destinado_a} → {destinado_a}")

    postos_atuais = sorted({cp.posto_grad_id for cp in andamento.postos_grad})
    if postos_atuais != posto_grad_ids:
        mudancas.append("Postos/graduações elegíveis alterados")

    andamento.data_inicio = data_inicio
    andamento.data_fim = data_fim
    andamento.data_limite_inscricao = data_limite_inscricao
    andamento.destinado_a = destinado_a

    CursoAndamentoPostoGrad.query.filter_by(curso_andamento_id=andamento.id).delete()
    for pg_id in posto_grad_ids:
        database.session.add(
            CursoAndamentoPostoGrad(curso_andamento_id=andamento.id, posto_grad_id=pg_id))

    if mudancas:
        _log_evento_andamento(
            andamento, "EDITADO", detalhes="; ".join(mudancas), user_id=editado_por_user_id)

    return andamento


def cancelar_curso_andamento(andamento, cancelado_por_user_id=None):
    """Cancela a edição — pra de aceitar inscrição nova, mas nada é
    apagado: solicitações já recebidas continuam no histórico do militar e
    visíveis pra BM-3. O mesmo curso do catálogo pode ganhar uma edição nova
    (outro CursoAndamento) quando for oferecido de novo."""
    if andamento.cancelado:
        raise ValueError("Esta edição já está cancelada.")

    andamento.cancelado = True
    andamento.cancelado_em = func.now()
    andamento.cancelado_por_user_id = cancelado_por_user_id

    _log_evento_andamento(andamento, "CANCELADO", user_id=cancelado_por_user_id)

    return andamento


def reativar_curso_andamento(andamento, reativado_por_user_id=None):
    """Desfaz um cancelamento feito por engano. Não mexe no prazo de
    inscrição — se ele já passou, a edição volta a ficar "Encerrado" (não
    "Cancelado"), e a BM-3 pode reabrir o prazo separadamente se quiser."""
    if not andamento.cancelado:
        raise ValueError("Esta edição não está cancelada.")

    andamento.cancelado = False
    andamento.cancelado_em = None
    andamento.cancelado_por_user_id = None

    _log_evento_andamento(andamento, "REATIVADO", user_id=reativado_por_user_id)

    return andamento


# ---------------------------------------------------------------------------
# Elegibilidade e visão do militar
# ---------------------------------------------------------------------------

def militar_elegivel(militar, andamento):
    if andamento.destinado_a != "AMBOS":
        eh_combatente = militar.especialidade_id == ESPECIALIDADE_COMBATENTE_ID
        if andamento.destinado_a == "COMBATENTE" and not eh_combatente:
            return False
        if andamento.destinado_a == "SAUDE" and eh_combatente:
            return False

    postos_permitidos = {cp.posto_grad_id for cp in andamento.postos_grad}
    return militar.posto_grad_id in postos_permitidos


def listar_cursos_disponiveis_para_militar(militar):
    """Edições com inscrição aberta e elegíveis pro militar — cada item já
    vem com a solicitação dele, se houver, pra tela mostrar o status certo.
    Uma edição encerrada ou pra qual ele não é elegível só some da lista se
    ele nunca chegou a se inscrever (senão ele perderia o rastro do próprio
    pedido)."""
    todas = (
        CursoAndamento.query
        .options(
            joinedload(CursoAndamento.curso),
            joinedload(CursoAndamento.postos_grad),
        )
        .order_by(CursoAndamento.data_limite_inscricao.asc())
        .all()
    )

    minhas_solicitacoes = {
        s.curso_andamento_id: s
        for s in (
            SolicitacaoInscricaoCurso.query
            .options(
                joinedload(SolicitacaoInscricaoCurso.analisado_por)
                .joinedload(User.militar).joinedload(Militar.posto_grad),
            )
            .filter_by(militar_id=militar.id)
            .all()
        )
    }

    disponiveis = []
    for andamento in todas:
        solicitacao = minhas_solicitacoes.get(andamento.id)
        elegivel = militar_elegivel(militar, andamento)
        if not solicitacao and (not andamento.inscricoes_abertas or not elegivel):
            continue
        disponiveis.append({
            "andamento": andamento,
            "solicitacao": solicitacao,
            "elegivel": elegivel,
        })

    return disponiveis


def criar_solicitacao_inscricao(andamento, militar, file_storage):
    """Recebe o PDF de inscrição do militar, sobe pro B2 e grava o pedido.
    Se ele já tinha uma inscrição indeferida pra essa mesma edição, o
    reenvio reaproveita a mesma linha (volta pra "aguardando análise").
    Levanta ValueError pra qualquer motivo de recusa."""
    if not andamento.inscricoes_abertas:
        raise ValueError("O prazo de inscrição para este curso já encerrou.")
    if not militar_elegivel(militar, andamento):
        raise ValueError("Você não atende aos critérios de elegibilidade deste curso.")

    if not file_storage or not (file_storage.filename or "").strip():
        raise ValueError("Selecione o arquivo PDF da sua inscrição.")

    filename = file_storage.filename or ""
    content_type = (file_storage.mimetype or "").lower()
    if content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise ValueError("O arquivo precisa ser um PDF.")

    try:
        pos = file_storage.stream.tell()
    except Exception:
        pos = 0
    try:
        file_storage.stream.seek(0, 2)
        tamanho_bytes = file_storage.stream.tell()
    finally:
        file_storage.stream.seek(pos, 0)

    if tamanho_bytes > TAMANHO_MAXIMO_PDF_BYTES:
        raise ValueError("O arquivo excede o tamanho máximo de 10MB.")

    existente = SolicitacaoInscricaoCurso.query.filter_by(
        curso_andamento_id=andamento.id, militar_id=militar.id
    ).first()

    if existente:
        if existente.deferido is None:
            raise ValueError("Você já tem uma inscrição aguardando análise para este curso.")
        if existente.deferido is True:
            raise ValueError("Sua inscrição para este curso já foi deferida.")

    nome_curso = sanitizar_nome(andamento.curso.nome if andamento.curso else "curso")
    nome_militar = sanitizar_nome(militar.nome_guerra or militar.nome_completo)
    subfolder = f"cursos_cbmam/{nome_curso}_{andamento.curso_id}/andamento_{andamento.id}"
    novo_nome = f"inscricao_{militar.id}_{nome_militar}"

    sucesso, resultado = upload_pdf_para_servidor(file_storage, subfolder, novo_nome=novo_nome)
    if not sucesso:
        raise ValueError(f"Falha ao enviar o arquivo: {resultado}")
    url_arquivo = resultado

    if existente:
        existente.nome_original = filename
        existente.content_type = content_type or "application/pdf"
        existente.tamanho_bytes = tamanho_bytes
        existente.url_arquivo = url_arquivo
        existente.deferido = None
        existente.analisado_em = None
        existente.analisado_por_user_id = None
        existente.observacao_analise = None
        return existente

    solicitacao = SolicitacaoInscricaoCurso(
        curso_andamento_id=andamento.id,
        militar_id=militar.id,
        nome_original=filename,
        content_type=content_type or "application/pdf",
        tamanho_bytes=tamanho_bytes,
        url_arquivo=url_arquivo,
    )
    database.session.add(solicitacao)
    return solicitacao


def listar_minhas_solicitacoes(militar_id):
    return (
        SolicitacaoInscricaoCurso.query
        .options(
            joinedload(SolicitacaoInscricaoCurso.curso_andamento).joinedload(CursoAndamento.curso),
            joinedload(SolicitacaoInscricaoCurso.analisado_por)
            .joinedload(User.militar).joinedload(Militar.posto_grad),
        )
        .filter_by(militar_id=militar_id)
        .order_by(SolicitacaoInscricaoCurso.criado_em.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Análise das inscrições (BM-3)
# ---------------------------------------------------------------------------

def listar_solicitacoes_para_analise(curso_andamento_id=None, apenas_pendentes=False):
    query = SolicitacaoInscricaoCurso.query.options(
        joinedload(SolicitacaoInscricaoCurso.militar).joinedload(Militar.posto_grad),
        joinedload(SolicitacaoInscricaoCurso.curso_andamento).joinedload(CursoAndamento.curso),
        joinedload(SolicitacaoInscricaoCurso.analisado_por)
        .joinedload(User.militar).joinedload(Militar.posto_grad),
    )
    if curso_andamento_id is not None:
        query = query.filter_by(curso_andamento_id=curso_andamento_id)
    if apenas_pendentes:
        query = query.filter(SolicitacaoInscricaoCurso.deferido.is_(None))
    return query.order_by(SolicitacaoInscricaoCurso.criado_em.desc()).all()


def listar_militares_inscritos_para_relatorio(curso_andamento_id):
    """Dados de contato de quem se inscreveu numa edição, pra BM-3 exportar
    em Excel (logística do curso): posto/grad, quadro, nome, OBM 1/2,
    telefone e contato de emergência. Inclui todo mundo que se inscreveu,
    não só quem foi deferido — a situação da inscrição vai junto na
    planilha pra BM-3 filtrar como quiser."""
    from src.models import MilitarObmFuncao, MilitarContatoEmergencia, Quadro

    solicitacoes = (
        SolicitacaoInscricaoCurso.query
        .options(
            joinedload(SolicitacaoInscricaoCurso.militar).joinedload(Militar.posto_grad),
            joinedload(SolicitacaoInscricaoCurso.militar).joinedload(Militar.quadro),
        )
        .filter_by(curso_andamento_id=curso_andamento_id)
        .join(Militar, SolicitacaoInscricaoCurso.militar_id == Militar.id)
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    linhas = []
    for s in solicitacoes:
        m = s.militar
        if not m:
            continue

        obm1 = (
            MilitarObmFuncao.query.options(joinedload(MilitarObmFuncao.obm))
            .filter_by(militar_id=m.id, tipo=1).filter(MilitarObmFuncao.data_fim.is_(None))
            .first()
        )
        obm2 = (
            MilitarObmFuncao.query.options(joinedload(MilitarObmFuncao.obm))
            .filter_by(militar_id=m.id, tipo=2).filter(MilitarObmFuncao.data_fim.is_(None))
            .first()
        )
        contato = (
            MilitarContatoEmergencia.query
            .filter_by(militar_id=m.id)
            .order_by(MilitarContatoEmergencia.id.asc())
            .first()
        )

        if s.deferido is None:
            situacao = "Aguardando análise"
        elif s.deferido:
            situacao = "Deferido"
        else:
            situacao = "Indeferido"

        linhas.append({
            "posto_grad": m.posto_grad.sigla if m.posto_grad else "",
            "quadro": m.quadro.quadro if m.quadro else "",
            "nome_completo": m.nome_completo or "",
            "nome_guerra": m.nome_guerra or "",
            "obm_1": obm1.obm.sigla if obm1 and obm1.obm else "",
            "obm_2": obm2.obm.sigla if obm2 and obm2.obm else "",
            "telefone": m.celular or "",
            "telefone_emergencia": contato.telefone if contato else "",
            "contato_emergencia_nome": contato.nome if contato else "",
            "situacao_inscricao": situacao,
        })

    return linhas


def obter_solicitacao(solicitacao_id):
    return (
        SolicitacaoInscricaoCurso.query
        .options(
            joinedload(SolicitacaoInscricaoCurso.militar),
            joinedload(SolicitacaoInscricaoCurso.curso_andamento).joinedload(CursoAndamento.curso),
        )
        .filter(SolicitacaoInscricaoCurso.id == solicitacao_id)
        .first()
    )


def _rotulo_status_solicitacao(deferido):
    if deferido is None:
        return "Aguardando análise"
    return "Deferido" if deferido else "Indeferido"


def analisar_solicitacao(solicitacao, deferido, observacao=None, analisado_por_user_id=None):
    """Defere/indefere — e também é usado pra corrigir uma análise já feita.
    Cada chamada (a primeira análise e qualquer correção depois) vira uma
    linha em AuditoriaSolicitacaoCurso, pra nunca perder o rastro de quem
    decidiu o quê e quando, mesmo que a decisão tenha sido corrigida
    depois."""
    de_status = _rotulo_status_solicitacao(solicitacao.deferido)

    solicitacao.deferido = bool(deferido)
    solicitacao.analisado_em = func.now()
    solicitacao.analisado_por_user_id = analisado_por_user_id
    solicitacao.observacao_analise = (observacao or "").strip() or None

    para_status = _rotulo_status_solicitacao(solicitacao.deferido)

    database.session.add(AuditoriaSolicitacaoCurso(
        solicitacao_id=solicitacao.id,
        de_status=de_status,
        para_status=para_status,
        observacao=solicitacao.observacao_analise,
        alterado_por_user_id=analisado_por_user_id,
    ))

    return solicitacao


# ---------------------------------------------------------------------------
# Histórico / auditoria
# ---------------------------------------------------------------------------

def listar_auditoria_solicitacao(solicitacao_id):
    """Toda análise já feita pra uma solicitação — a primeira e qualquer
    correção depois, mais recente primeiro."""
    return (
        AuditoriaSolicitacaoCurso.query
        .options(joinedload(AuditoriaSolicitacaoCurso.alterado_por).joinedload(User.militar).joinedload(Militar.posto_grad))
        .filter_by(solicitacao_id=solicitacao_id)
        .order_by(AuditoriaSolicitacaoCurso.data_alteracao.desc())
        .all()
    )


def listar_auditoria_solicitacoes_do_andamento(curso_andamento_id):
    """Auditoria de todas as solicitações de uma edição, já agrupada por
    solicitacao_id — pra tela de análise mostrar o histórico de cada uma
    sem disparar uma consulta por linha."""
    registros = (
        AuditoriaSolicitacaoCurso.query
        .options(joinedload(AuditoriaSolicitacaoCurso.alterado_por).joinedload(User.militar).joinedload(Militar.posto_grad))
        .join(SolicitacaoInscricaoCurso, AuditoriaSolicitacaoCurso.solicitacao_id == SolicitacaoInscricaoCurso.id)
        .filter(SolicitacaoInscricaoCurso.curso_andamento_id == curso_andamento_id)
        .order_by(AuditoriaSolicitacaoCurso.data_alteracao.desc())
        .all()
    )
    agrupado = {}
    for reg in registros:
        agrupado.setdefault(reg.solicitacao_id, []).append(reg)
    return agrupado


def listar_auditoria_andamento(curso_andamento_id):
    """Linha do tempo de uma edição: criação, edições, cancelamento(s) e
    reativação(ões), mais recente primeiro."""
    return (
        AuditoriaCursoAndamento.query
        .options(joinedload(AuditoriaCursoAndamento.realizado_por).joinedload(User.militar).joinedload(Militar.posto_grad))
        .filter_by(curso_andamento_id=curso_andamento_id)
        .order_by(AuditoriaCursoAndamento.realizado_em.desc())
        .all()
    )
