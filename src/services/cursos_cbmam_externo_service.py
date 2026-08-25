"""Cursos CBMAM — inscrição do público externo (civil ou militar de outra
força: Exército, Marinha, Aeronáutica, Polícia Militar).

Espelha src.services.cursos_cbmam_service, mas ancorado em PessoaExterna em
vez de Militar — de propósito, sem misturar as duas tabelas de solicitação:
uma pessoa de fora não tem posto_grad_id/especialidade_id do CBMAM, então a
elegibilidade dela não é decidida por CursoAndamentoPostoGrad como a do
militar, e sim só por CursoAndamento.aberto_publico_externo (a BM-3 decide,
por edição, se ela também aceita público externo).
"""
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src import database
from src.decorators.utils_pdf_bucket import sanitizar_nome, upload_pdf_para_servidor
from src.services.cursos_cbmam_service import TAMANHO_MAXIMO_PDF_BYTES
from src.models import (
    AuditoriaSolicitacaoCursoExterno,
    CursoAndamento,
    PessoaExterna,
    SolicitacaoInscricaoCursoExterno,
    User,
)


# ---------------------------------------------------------------------------
# Elegibilidade e visão da pessoa externa
# ---------------------------------------------------------------------------

def listar_cursos_disponiveis_para_externo(pessoa_externa):
    """Edições que ainda fazem sentido pra pessoa AGIR: pra quem nunca se
    inscreveu, é aberta+elegível; pra quem já foi indeferido, é a chance de
    reenviar (enquanto o prazo não fechou). Uma vez que a pessoa já está
    inscrita — aguardando análise ou já deferida — a edição some daqui,
    porque não sobra nada pra fazer; ela continua visível em "Meus cursos",
    sem duplicar a mesma edição nas duas listas."""
    todas = (
        CursoAndamento.query
        .options(
            joinedload(CursoAndamento.curso),
            joinedload(CursoAndamento.disciplinas),
        )
        .order_by(CursoAndamento.data_limite_inscricao.asc())
        .all()
    )

    minhas_solicitacoes = {
        s.curso_andamento_id: s
        for s in (
            SolicitacaoInscricaoCursoExterno.query
            .options(joinedload(SolicitacaoInscricaoCursoExterno.analisado_por))
            .filter_by(pessoa_externa_id=pessoa_externa.id)
            .all()
        )
    }

    disponiveis = []
    for andamento in todas:
        solicitacao = minhas_solicitacoes.get(andamento.id)
        elegivel = andamento.aberto_publico_externo

        if solicitacao is not None:
            # Já tem solicitação: só continua aparecendo aqui se foi
            # indeferida e ainda dá pra reenviar. Pendente ou deferida já
            # está resolvida — o rastro dela mora só em "Meus cursos".
            if solicitacao.deferido is not False or not andamento.inscricoes_abertas:
                continue
        elif not andamento.inscricoes_abertas or not elegivel:
            continue

        disponiveis.append({
            "andamento": andamento,
            "solicitacao": solicitacao,
            "elegivel": elegivel,
        })

    return disponiveis


def criar_solicitacao_inscricao_externo(andamento, pessoa_externa, file_storage):
    """Recebe o PDF de inscrição, sobe pro servidor e grava o pedido. Se a
    pessoa já tinha uma inscrição indeferida pra essa mesma edição, o
    reenvio reaproveita a mesma linha (volta pra "aguardando análise").
    Levanta ValueError pra qualquer motivo de recusa."""
    if not andamento.aberto_publico_externo:
        raise ValueError("Este curso não está disponível para inscrição externa.")
    if not andamento.inscricoes_abertas:
        raise ValueError("O prazo de inscrição para este curso já encerrou.")

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

    existente = SolicitacaoInscricaoCursoExterno.query.filter_by(
        curso_andamento_id=andamento.id, pessoa_externa_id=pessoa_externa.id
    ).first()

    if existente:
        if existente.deferido is None:
            raise ValueError("Você já tem uma inscrição aguardando análise para este curso.")
        if existente.deferido is True:
            raise ValueError("Sua inscrição para este curso já foi deferida.")

    nome_curso = sanitizar_nome(andamento.curso.nome if andamento.curso else "curso")
    nome_pessoa = sanitizar_nome(pessoa_externa.nome_completo)
    subfolder = f"cursos_cbmam/{nome_curso}_{andamento.curso_id}/andamento_{andamento.id}"
    novo_nome = f"inscricao_externo_{pessoa_externa.id}_{nome_pessoa}"

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

    solicitacao = SolicitacaoInscricaoCursoExterno(
        curso_andamento_id=andamento.id,
        pessoa_externa_id=pessoa_externa.id,
        nome_original=filename,
        content_type=content_type or "application/pdf",
        tamanho_bytes=tamanho_bytes,
        url_arquivo=url_arquivo,
    )
    database.session.add(solicitacao)
    return solicitacao


def listar_minhas_solicitacoes_externo(pessoa_externa_id):
    return (
        SolicitacaoInscricaoCursoExterno.query
        .options(
            joinedload(SolicitacaoInscricaoCursoExterno.curso_andamento).joinedload(CursoAndamento.curso),
            joinedload(SolicitacaoInscricaoCursoExterno.analisado_por),
        )
        .filter_by(pessoa_externa_id=pessoa_externa_id)
        .order_by(SolicitacaoInscricaoCursoExterno.criado_em.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Análise das inscrições (BM-3)
# ---------------------------------------------------------------------------

def listar_solicitacoes_externas_para_analise(curso_andamento_id=None, apenas_pendentes=False):
    query = SolicitacaoInscricaoCursoExterno.query.options(
        joinedload(SolicitacaoInscricaoCursoExterno.pessoa_externa).joinedload(PessoaExterna.forca),
        joinedload(SolicitacaoInscricaoCursoExterno.curso_andamento).joinedload(CursoAndamento.curso),
        joinedload(SolicitacaoInscricaoCursoExterno.analisado_por),
    )
    if curso_andamento_id is not None:
        query = query.filter_by(curso_andamento_id=curso_andamento_id)
    if apenas_pendentes:
        query = query.filter(SolicitacaoInscricaoCursoExterno.deferido.is_(None))
    return query.order_by(SolicitacaoInscricaoCursoExterno.criado_em.desc()).all()


def listar_pessoas_externas_inscritas_para_relatorio(curso_andamento_id):
    """Dados de contato de quem se inscreveu (público externo) numa edição,
    pra BM-3 exportar em Excel — mesma ideia de
    listar_militares_inscritos_para_relatorio, adaptada aos campos que
    existem pra pessoa externa."""
    solicitacoes = (
        SolicitacaoInscricaoCursoExterno.query
        .options(
            joinedload(SolicitacaoInscricaoCursoExterno.pessoa_externa).joinedload(PessoaExterna.forca),
        )
        .filter_by(curso_andamento_id=curso_andamento_id)
        .join(PessoaExterna, SolicitacaoInscricaoCursoExterno.pessoa_externa_id == PessoaExterna.id)
        .order_by(PessoaExterna.nome_completo.asc())
        .all()
    )

    linhas = []
    for s in solicitacoes:
        p = s.pessoa_externa
        if not p:
            continue

        if s.deferido is None:
            situacao = "Aguardando análise"
        elif s.deferido:
            situacao = "Deferido"
        else:
            situacao = "Indeferido"

        linhas.append({
            "nome_completo": p.nome_completo or "",
            "cpf": p.cpf or "",
            "telefone": p.telefone or "",
            "email": p.email or "",
            "instituicao_origem": p.instituicao_origem or "",
            "tipo_pessoa": "Militar" if p.tipo_pessoa == "MILITAR" else "Civil",
            "forca": p.forca.nome if p.forca else "",
            "posto_graduacao": p.posto_graduacao or "",
            "situacao_inscricao": situacao,
        })

    return linhas


def obter_solicitacao_externo(solicitacao_id):
    return (
        SolicitacaoInscricaoCursoExterno.query
        .options(
            joinedload(SolicitacaoInscricaoCursoExterno.pessoa_externa),
            joinedload(SolicitacaoInscricaoCursoExterno.curso_andamento).joinedload(CursoAndamento.curso),
        )
        .filter(SolicitacaoInscricaoCursoExterno.id == solicitacao_id)
        .first()
    )


def _rotulo_status_solicitacao(deferido):
    if deferido is None:
        return "Aguardando análise"
    return "Deferido" if deferido else "Indeferido"


def analisar_solicitacao_externo(solicitacao, deferido, observacao=None, analisado_por_user_id=None):
    """Defere/indefere — e também serve pra corrigir uma análise já feita.
    Cada chamada vira uma linha em AuditoriaSolicitacaoCursoExterno, sem
    apagar a decisão anterior."""
    de_status = _rotulo_status_solicitacao(solicitacao.deferido)

    solicitacao.deferido = bool(deferido)
    solicitacao.analisado_em = func.now()
    solicitacao.analisado_por_user_id = analisado_por_user_id
    solicitacao.observacao_analise = (observacao or "").strip() or None

    para_status = _rotulo_status_solicitacao(solicitacao.deferido)

    database.session.add(AuditoriaSolicitacaoCursoExterno(
        solicitacao_id=solicitacao.id,
        de_status=de_status,
        para_status=para_status,
        observacao=solicitacao.observacao_analise,
        alterado_por_user_id=analisado_por_user_id,
    ))

    return solicitacao


def marcar_conclusao_externo(solicitacao, concluido, realizado_por_user_id=None):
    """Confirma (ou desfaz) que a pessoa concluiu esta edição do curso — só
    faz sentido pra quem já foi deferido. Mesmo padrão de
    analisar_solicitacao_externo."""
    if not solicitacao.deferido:
        raise ValueError("Só é possível marcar conclusão de uma inscrição já deferida.")

    de_status = "Concluído" if solicitacao.concluido else "Deferido"

    solicitacao.concluido = bool(concluido)
    solicitacao.concluido_em = func.now() if solicitacao.concluido else None
    solicitacao.concluido_por_user_id = realizado_por_user_id if solicitacao.concluido else None

    para_status = "Concluído" if solicitacao.concluido else "Deferido"

    database.session.add(AuditoriaSolicitacaoCursoExterno(
        solicitacao_id=solicitacao.id,
        de_status=de_status,
        para_status=para_status,
        alterado_por_user_id=realizado_por_user_id,
    ))

    return solicitacao


# ---------------------------------------------------------------------------
# Histórico / auditoria
# ---------------------------------------------------------------------------

def listar_auditoria_solicitacao_externo(solicitacao_id):
    return (
        AuditoriaSolicitacaoCursoExterno.query
        .options(joinedload(AuditoriaSolicitacaoCursoExterno.alterado_por))
        .filter_by(solicitacao_id=solicitacao_id)
        .order_by(AuditoriaSolicitacaoCursoExterno.data_alteracao.desc())
        .all()
    )


def listar_auditoria_solicitacoes_externo_do_andamento(curso_andamento_id):
    registros = (
        AuditoriaSolicitacaoCursoExterno.query
        .options(joinedload(AuditoriaSolicitacaoCursoExterno.alterado_por))
        .join(SolicitacaoInscricaoCursoExterno,
              AuditoriaSolicitacaoCursoExterno.solicitacao_id == SolicitacaoInscricaoCursoExterno.id)
        .filter(SolicitacaoInscricaoCursoExterno.curso_andamento_id == curso_andamento_id)
        .order_by(AuditoriaSolicitacaoCursoExterno.data_alteracao.desc())
        .all()
    )
    agrupado = {}
    for reg in registros:
        agrupado.setdefault(reg.solicitacao_id, []).append(reg)
    return agrupado
