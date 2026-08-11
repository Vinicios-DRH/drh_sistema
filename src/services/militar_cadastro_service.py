import unicodedata
from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from flask import flash, request
from flask_login import current_user

from src import database
from src.models import (
    AuditoriaAtualizacaoCadastral,
    Comportamento,
    Curso,
    Destino,
    EstadoCivil,
    Especialidade,
    Funcao,
    FuncaoGratificada,
    Localidade,
    Militar,
    Modalidade,
    Motivo,
    MilitarConjuge,
    MilitarContatoEmergencia,
    MilitarCurso,
    MilitarGraduacao,
    MilitarObmFuncao,
    Obm,
    PostoGrad,
    PublicacaoBg,
    Punicao,
    Quadro,
    now_manaus_naive,
)
from src.routes.helpers import get_user_ip
from src.services.militar_situacao_service import (
    parse_date_flex,
    sincronizar_blocos_funcionais,
)

# Modalidades cujo <select> de "Modalidade" deve exibir na tela de cadastro do militar.
MODALIDADES_VALIDAS = {
    'AGUARDANDO',
    'À DISPOSIÇÃO',
    'LICENÇA ESPECIAL',
    'LICENÇA MATERNIDADE',
    'LTS',
    'ORDEM DE SERVIÇO',
    'PRONTO',
    'EM CURSO',
}

# Campos do FormMilitar que, na verdade, são publicações de Boletim Geral
# (tabela PublicacaoBg) e não colunas diretas de Militar.
CAMPOS_BG = [
    "transferencia", "situacao_militar", "cfsd", "cfc", "cfs", "cas",
    "choa", "cfo", "cbo", "cao", "csbm", "soldado_tres",
    "soldado_dois", "soldado_um", "cabo", "terceiro_sgt",
    "segundo_sgt", "primeiro_sgt", "subtenente",
    "publicidade_segundo_tenente", "publicidade_primeiro_tenente",
    "pub_cap", "pub_maj", "pub_tc", "pub_cel", "pub_alteracao",
    "situacao_militar_2",
]


# ---------------------------------------------------------------------------
# Tempo de serviço
# ---------------------------------------------------------------------------

def normalizar_date(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def calcular_datas_servico(efetivo_servico):
    """Calcula anos/meses/dias de serviço e as datas de 25 e 30 anos a partir
    da data de efetivo serviço do militar."""
    efetivo = normalizar_date(efetivo_servico)

    if not efetivo:
        return {
            "completa_25_anos_sv": None,
            "completa_30_anos_sv": None,
            "anos": None,
            "meses": None,
            "dias": None,
            "total_dias": None,
        }

    hoje = date.today()

    if efetivo > hoje:
        anos = meses = dias = total_dias = 0
    else:
        diff = relativedelta(hoje, efetivo)
        anos = diff.years
        meses = diff.months
        dias = diff.days
        total_dias = (hoje - efetivo).days

    return {
        "completa_25_anos_sv": efetivo + relativedelta(years=25),
        "completa_30_anos_sv": efetivo + relativedelta(years=30),
        "anos": anos,
        "meses": meses,
        "dias": dias,
        "total_dias": total_dias,
    }


# ---------------------------------------------------------------------------
# Montagem do formulário (tela de exibir/editar militar)
# ---------------------------------------------------------------------------

def montar_choices_form_militar(form_militar):
    """Popula todos os <select> (choices) do FormMilitar a partir do banco.

    Precisa rodar tanto no GET quanto no POST: no POST é o que permite o
    WTForms validar os valores enviados.
    """
    form_militar.funcao_gratificada_id.choices = [
        (fg.id, fg.gratificacao) for fg in FuncaoGratificada.query.all()]
    form_militar.posto_grad_id.choices = [
        (posto.id, posto.sigla) for posto in PostoGrad.query.all()]
    form_militar.quadro_id.choices = [
        (quadro.id, quadro.quadro) for quadro in Quadro.query.all()]
    form_militar.localidade_id.choices = [
        (loc.id, loc.sigla) for loc in Localidade.query.all()]

    form_militar.obm_ids_1.choices = [
        ("", "-- Selecione uma opção --")] + [(obm.id, obm.sigla) for obm in Obm.query.all()]
    form_militar.funcao_ids_1.choices = [("", "-- Selecione uma opção --")] + [
        (funcao.id, funcao.ocupacao) for funcao in Funcao.query.all()]
    form_militar.obm_ids_2.choices = [
        ("", "-- Selecione uma opção --")] + [(obm.id, obm.sigla) for obm in Obm.query.all()]
    form_militar.funcao_ids_2.choices = [("", "-- Selecione uma opção --")] + [
        (funcao.id, funcao.ocupacao) for funcao in Funcao.query.all()]

    modalidades = Modalidade.query.filter(Modalidade.descricao.in_(
        MODALIDADES_VALIDAS)).order_by(Modalidade.descricao.asc()).all()
    form_militar.modalidade_id.choices = [
        ("", "-- Selecione --")] + [(m.id, m.descricao) for m in modalidades]

    form_militar.estado_civil.choices = [
        (estado.id, estado.estado) for estado in EstadoCivil.query.all()]
    form_militar.especialidade_id.choices = [
        (esp.id, esp.ocupacao) for esp in Especialidade.query.all()]
    form_militar.destino_id.choices = [
        ("", "-- Selecione uma opção --")] + [(dest.id, dest.local) for dest in Destino.query.all()]

    motivos = Motivo.query.order_by(Motivo.descricao.asc()).all()
    form_militar.motivo_id.choices = [
        ("", "-- Selecione --")] + [(m.id, m.descricao) for m in motivos]

    form_militar.punicao_id.choices = [
        (punicao.id, punicao.sancao) for punicao in Punicao.query.all()]
    form_militar.comportamento_id.choices = [("", "-- Selecione uma opção --")] + [
        (comp.id, comp.conduta) for comp in Comportamento.query.all()]

    form_militar.cursos_ids.choices = [
        (curso.id, curso.nome) for curso in Curso.query.order_by(Curso.nome.asc()).all()
    ]


def preencher_form_para_exibicao(form_militar, militar, obm_funcao_tipo_1, obm_funcao_tipo_2):
    """Preenche o FormMilitar com os dados atuais do militar (fluxo GET).

    Retorna o valor atual da publicação BG de 'situacao_militar_2': esse
    campo não é uma coluna do Militar, então o WTForms não o carrega sozinho
    a partir de `obj=militar` e o template precisa dele à parte.
    """
    if militar.completa_25_inclusao:
        form_militar.completa_25_inclusao.data = militar.completa_25_inclusao.strftime("%d/%m/%Y")
    if militar.completa_30_inclusao:
        form_militar.completa_30_inclusao.data = militar.completa_30_inclusao.strftime("%d/%m/%Y")

    calculo_servico = calcular_datas_servico(militar.efetivo_servico)

    form_militar.completa_25_anos_sv.data = (
        calculo_servico["completa_25_anos_sv"].strftime("%d/%m/%Y")
        if calculo_servico["completa_25_anos_sv"] else ""
    )
    form_militar.completa_30_anos_sv.data = (
        calculo_servico["completa_30_anos_sv"].strftime("%d/%m/%Y")
        if calculo_servico["completa_30_anos_sv"] else ""
    )
    form_militar.anos.data = calculo_servico["anos"]
    form_militar.meses.data = calculo_servico["meses"]
    form_militar.dias.data = calculo_servico["dias"]
    form_militar.total_dias.data = calculo_servico["total_dias"]

    if obm_funcao_tipo_1:
        form_militar.obm_ids_1.data = obm_funcao_tipo_1.obm_id
        form_militar.funcao_ids_1.data = obm_funcao_tipo_1.funcao_id

    if obm_funcao_tipo_2:
        form_militar.obm_ids_2.data = obm_funcao_tipo_2.obm_id
        form_militar.funcao_ids_2.data = obm_funcao_tipo_2.funcao_id

    form_militar.sexo.data = militar.sexo if militar.sexo else None
    form_militar.raca.data = militar.raca if militar.raca else None
    form_militar.cursos_ids.data = [mc.curso_id for mc in militar.cursos_especializacao]

    hoje = date.today()
    dn = militar.data_nascimento.date() if isinstance(
        militar.data_nascimento, datetime) else militar.data_nascimento
    if dn:
        idade = hoje.year - dn.year - ((hoje.month, hoje.day) < (dn.month, dn.day))
    else:
        idade = None
    form_militar.idade_atual.data = idade

    publicacoes_bg = PublicacaoBg.query.filter_by(militar_id=militar.id).all()

    for campo in CAMPOS_BG:
        if hasattr(form_militar, campo):
            getattr(form_militar, campo).data = ""

    for pub in publicacoes_bg:
        if pub.tipo_bg in CAMPOS_BG and hasattr(form_militar, pub.tipo_bg):
            getattr(form_militar, pub.tipo_bg).data = pub.boletim_geral or ""

    bg_sit2_ultima = (
        PublicacaoBg.query
        .filter_by(militar_id=militar.id, tipo_bg="situacao_militar_2")
        .order_by(PublicacaoBg.id.desc())
        .first()
    )
    bg_sit2_val = bg_sit2_ultima.boletim_geral if bg_sit2_ultima else ""
    if hasattr(form_militar, "situacao_militar_2"):
        form_militar.situacao_militar_2.data = bg_sit2_val

    form_militar.situacao.data = militar.situacao or None
    form_militar.modalidade_id.data = militar.modalidade_id or None
    form_militar.motivo_id.data = militar.motivo_id or None
    form_militar.destino_id.data = militar.destino_id or None

    return bg_sit2_val


# ---------------------------------------------------------------------------
# Salvamento (fluxo POST) — cada função cuida de um grupo coeso de campos.
# Nenhuma delas comita a sessão: quem orquestra decide o commit.
# ---------------------------------------------------------------------------

def _aplicar_dados_cadastrais(militar, form_militar):
    """Identificação, documentos, posto/quadro/localidade e tempo de serviço."""
    militar.nome_completo = form_militar.nome_completo.data
    militar.nome_guerra = form_militar.nome_guerra.data
    militar.cpf = form_militar.cpf.data
    militar.rg = form_militar.rg.data
    militar.nome_pai = form_militar.nome_pai.data
    militar.nome_mae = form_militar.nome_mae.data
    militar.matricula = form_militar.matricula.data
    militar.pis_pasep = form_militar.pis_pasep.data
    militar.num_titulo_eleitor = form_militar.num_titulo_eleitor.data
    militar.digito_titulo_eleitor = form_militar.digito_titulo_eleitor.data
    militar.zona = form_militar.zona.data
    militar.secao = form_militar.secao.data
    militar.posto_grad_id = form_militar.posto_grad_id.data
    militar.quadro_id = form_militar.quadro_id.data
    militar.localidade_id = form_militar.localidade_id.data
    militar.antiguidade = form_militar.antiguidade.data
    militar.sexo = form_militar.sexo.data
    militar.raca = form_militar.raca.data
    militar.data_nascimento = form_militar.data_nascimento.data
    militar.inclusao = form_militar.inclusao.data

    militar.completa_25_inclusao = (
        datetime.strptime(str(form_militar.completa_25_inclusao.data), "%d/%m/%Y").date()
        if form_militar.completa_25_inclusao.data else None
    )
    militar.completa_30_inclusao = (
        datetime.strptime(str(form_militar.completa_30_inclusao.data), "%d/%m/%Y").date()
        if form_militar.completa_30_inclusao.data else None
    )

    militar.punicao_id = form_militar.punicao_id.data
    militar.comportamento_id = form_militar.comportamento_id.data
    militar.efetivo_servico = form_militar.efetivo_servico.data

    calculo_servico = calcular_datas_servico(militar.efetivo_servico)
    militar.completa_25_anos_sv = calculo_servico["completa_25_anos_sv"]
    militar.completa_30_anos_sv = calculo_servico["completa_30_anos_sv"]
    militar.anos = calculo_servico["anos"]
    militar.meses = calculo_servico["meses"]
    militar.dias = calculo_servico["dias"]
    militar.total_dias = calculo_servico["total_dias"]

    militar.idade_reserva_grad = 0
    militar.estado_civil = form_militar.estado_civil.data
    militar.especialidade_id = form_militar.especialidade_id.data


def _aplicar_situacao_principal(militar, form_militar):
    """Situação/modalidade/motivo/destino vindos do próprio FormMilitar."""
    militar.situacao = form_militar.situacao.data or None
    militar.modalidade_id = int(
        form_militar.modalidade_id.data) if form_militar.modalidade_id.data not in ("", None) else None
    militar.motivo_id = int(
        form_militar.motivo_id.data) if form_militar.motivo_id.data not in ("", None) else None
    militar.destino_id = int(
        form_militar.destino_id.data) if form_militar.destino_id.data not in ("", None) else None
    militar.inicio_periodo = parse_date_flex(form_militar.inicio_periodo.data)
    militar.fim_periodo = parse_date_flex(form_militar.fim_periodo.data)


def _aplicar_situacao_extra_manual(militar):
    """Segunda situação/agregação: campos manuais fora do FormMilitar, lidos
    direto do request (incluindo a publicação de BG correspondente)."""
    situacao2_id_req = request.form.get("situacao2_id")
    militar.situacao2_id = int(situacao2_id_req) if situacao2_id_req else None

    agregacoes2_id_req = request.form.get("agregacoes2_id")
    militar.agregacoes2_id = int(agregacoes2_id_req) if agregacoes2_id_req else None

    militar.inicio_situacao2 = parse_date_flex(request.form.get("inicio_situacao2"))
    militar.fim_situacao2 = parse_date_flex(request.form.get("fim_situacao2"))

    bg_sit2_input = request.form.get("situacao_militar_2")
    if bg_sit2_input is not None:
        bg_existente_sit2 = PublicacaoBg.query.filter_by(
            militar_id=militar.id, tipo_bg="situacao_militar_2").first()
        if bg_sit2_input.strip():
            if bg_existente_sit2:
                bg_existente_sit2.boletim_geral = bg_sit2_input.strip()
            else:
                database.session.add(PublicacaoBg(
                    militar_id=militar.id, tipo_bg="situacao_militar_2", boletim_geral=bg_sit2_input.strip()))
        elif bg_existente_sit2:
            # Se o usuário apagou o campo, entendemos que é para limpar a publicação
            database.session.delete(bg_existente_sit2)


def _aplicar_dados_academicos_e_ltip(militar, form_militar):
    """LTIP, escolaridade/cursos e o histórico de promoções (cfsd..csbm)."""
    militar.ltip_afastamento_cargo_eletivo = form_militar.ltip_afastamento_cargo_eletivo.data
    militar.periodo_ltip = form_militar.periodo_ltip.data
    militar.total_ltip = form_militar.total_ltip.data
    militar.completa_25_anos_ltip = form_militar.completa_25_anos_ltip.data
    militar.completa_30_anos_ltip = form_militar.completa_30_anos_ltip.data
    militar.cursos = form_militar.cursos.data
    militar.grau_instrucao = form_militar.grau_instrucao.data
    militar.graduacao = form_militar.graduacao.data
    militar.pos_graduacao = form_militar.pos_graduacao.data
    militar.mestrado = form_militar.mestrado.data
    militar.doutorado = form_militar.doutorado.data
    militar.cfsd = form_militar.cfsd.data
    militar.cfc = form_militar.cfc.data
    militar.cfs = form_militar.cfs.data
    militar.cas = form_militar.cas.data
    militar.choa = form_militar.choa.data
    militar.cfo = form_militar.cfo.data
    militar.cbo = form_militar.cbo.data
    militar.cao = form_militar.cao.data
    militar.csbm = form_militar.csbm.data
    militar.cursos_civis = form_militar.cursos_civis.data


def _aplicar_dados_contato_e_endereco(militar, form_militar):
    militar.endereco = form_militar.endereco.data
    militar.complemento = form_militar.complemento.data
    militar.cidade = form_militar.cidade.data
    militar.estado = form_militar.estado.data
    militar.cep = form_militar.cep.data
    militar.celular = form_militar.celular.data
    militar.email = form_militar.email.data


def _aplicar_dados_fisicos(militar, form_militar):
    militar.local_nascimento = form_militar.local_nascimento.data
    militar.altura = form_militar.altura.data
    militar.cor_olhos = form_militar.cor_olhos.data
    militar.cor_cabelos = form_militar.cor_cabelos.data
    militar.bigode = bool(form_militar.bigode.data)
    militar.medida_cabeca = form_militar.medida_cabeca.data
    militar.numero_sapato = form_militar.numero_sapato.data
    militar.medida_calca = form_militar.medida_calca.data
    militar.medida_camisa = form_militar.medida_camisa.data
    militar.tipo_sanguineo = form_militar.tipo_sanguineo.data
    militar.sinais_particulares = form_militar.sinais_particulares.data
    militar.tatuagem = bool(form_militar.tatuagem.data)
    militar.local_tatuagem = form_militar.local_tatuagem.data if form_militar.tatuagem.data else None


def _aplicar_boletins_promocao(militar, form_militar):
    """BG de inclusão e o histórico de publicações de graduação (soldado..cel)."""
    militar.inclusao_bg = form_militar.inclusao_bg.data
    militar.soldado_tres = form_militar.soldado_tres.data
    militar.soldado_dois = form_militar.soldado_dois.data
    militar.soldado_um = form_militar.soldado_um.data
    militar.cabo = form_militar.cabo.data
    militar.terceiro_sgt = form_militar.terceiro_sgt.data
    militar.segundo_sgt = form_militar.segundo_sgt.data
    militar.primeiro_sgt = form_militar.primeiro_sgt.data
    militar.subtenente = form_militar.subtenente.data
    militar.segundo_tenente = form_militar.segundo_tenente.data
    militar.primeiro_tenente = form_militar.primeiro_tenente.data
    militar.cap = form_militar.cap.data
    militar.maj = form_militar.maj.data
    militar.tc = form_militar.tc.data
    militar.cel = form_militar.cel.data
    militar.funcao_gratificada_id = form_militar.funcao_gratificada_id.data
    militar.alteracao_nome_guerra = form_militar.alteracao_nome_guerra.data


def _salvar_cursos_especializacao(militar, form_militar):
    """Sincroniza a relação many-to-many MilitarCurso com o que foi marcado no form."""
    cursos_selecionados = form_militar.cursos_ids.data or []
    cursos_atuais = {mc.curso_id: mc for mc in militar.cursos_especializacao}

    for curso_id in cursos_selecionados:
        if curso_id not in cursos_atuais:
            database.session.add(MilitarCurso(
                militar_id=militar.id, curso_id=curso_id, criado_em=now_manaus_naive()))

    for curso_id, mc in cursos_atuais.items():
        if curso_id not in cursos_selecionados:
            database.session.delete(mc)


def _salvar_graduacoes(militar):
    """Recria a lista livre de graduações/cursos (linhas dinâmicas do formulário)."""
    graduacoes_curso = request.form.getlist("graduacoes_curso[]")
    graduacoes_instituicao = request.form.getlist("graduacoes_instituicao[]")
    graduacoes_ano = request.form.getlist("graduacoes_ano[]")

    MilitarGraduacao.query.filter_by(militar_id=militar.id).delete()

    for i, curso in enumerate(graduacoes_curso):
        curso = (curso or "").strip()
        if not curso:
            continue

        instituicao = (graduacoes_instituicao[i] or "").strip() if i < len(graduacoes_instituicao) else ""
        ano_raw = (graduacoes_ano[i] or "").strip() if i < len(graduacoes_ano) else ""

        database.session.add(MilitarGraduacao(
            militar_id=militar.id,
            curso=curso,
            instituicao=instituicao or None,
            ano_conclusao=int(ano_raw) if ano_raw.isdigit() else None,
            criado_em=now_manaus_naive()
        ))


def _salvar_contatos_emergencia(militar):
    """Recria a lista de contatos de emergência (linhas dinâmicas do formulário)."""
    contato_nome = request.form.getlist("contato_nome[]")
    contato_parentesco = request.form.getlist("contato_parentesco[]")
    contato_telefone = request.form.getlist("contato_telefone[]")
    contato_telefone_secundario = request.form.getlist("contato_telefone_secundario[]")
    contato_observacao = request.form.getlist("contato_observacao[]")

    MilitarContatoEmergencia.query.filter_by(militar_id=militar.id).delete()

    for i, nome in enumerate(contato_nome):
        nome = (nome or "").strip()
        telefone = (contato_telefone[i] or "").strip() if i < len(contato_telefone) else ""

        if not nome or not telefone:
            continue

        database.session.add(MilitarContatoEmergencia(
            militar_id=militar.id,
            nome=nome,
            parentesco=(contato_parentesco[i] or "").strip() if i < len(contato_parentesco) else None,
            telefone=telefone,
            telefone_secundario=(contato_telefone_secundario[i] or "").strip()
            if i < len(contato_telefone_secundario) else None,
            observacao=(contato_observacao[i] or "").strip() if i < len(contato_observacao) else None,
            criado_em=now_manaus_naive()
        ))


def _normalizar_texto(txt):
    txt = (txt or "").strip().upper()
    txt = unicodedata.normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")
    return " ".join(txt.split())


def _salvar_conjuge(militar):
    """Cria/atualiza o cônjuge quando o estado civil exige, remove quando não exige mais.

    Depende de `militar.estado_civil` já estar atualizado — deve rodar depois
    de `_aplicar_dados_cadastrais`.
    """
    estado_civil_obj = EstadoCivil.query.get(militar.estado_civil) if militar.estado_civil else None
    estado_nome = _normalizar_texto(estado_civil_obj.estado if estado_civil_obj else "")
    exige_conjuge = "CASAD" in estado_nome or "UNIAO ESTAVEL" in estado_nome

    conjuge_nome = (request.form.get("conjuge_nome") or "").strip()
    conjuge_cpf = (request.form.get("conjuge_cpf") or "").strip()
    conjuge_telefone = (request.form.get("conjuge_telefone") or "").strip()
    conjuge_data_nascimento = (request.form.get("conjuge_data_nascimento") or "").strip()
    conjuge_endereco = (request.form.get("conjuge_endereco") or "").strip()
    conjuge_observacao = (request.form.get("conjuge_observacao") or "").strip()

    conjuge_db = MilitarConjuge.query.filter_by(militar_id=militar.id).first()

    tem_dado_conjuge = any([
        conjuge_nome, conjuge_cpf, conjuge_telefone,
        conjuge_data_nascimento, conjuge_endereco, conjuge_observacao,
    ])

    if exige_conjuge and tem_dado_conjuge:
        if not conjuge_db:
            conjuge_db = MilitarConjuge(militar_id=militar.id, criado_em=now_manaus_naive())
            database.session.add(conjuge_db)

        conjuge_db.nome = conjuge_nome or "-"
        conjuge_db.cpf = conjuge_cpf or None
        conjuge_db.telefone = conjuge_telefone or None
        conjuge_db.data_nascimento = parse_date_flex(conjuge_data_nascimento)
        conjuge_db.endereco = conjuge_endereco or None
        conjuge_db.observacao = conjuge_observacao or None
    elif conjuge_db:
        database.session.delete(conjuge_db)


def _salvar_obm_funcao(militar, form_militar):
    """Encerra vínculos de OBM/função que mudaram e abre os novos, para os dois slots (1 e 2)."""
    obm_1 = form_militar.obm_ids_1.data
    funcao_1 = form_militar.funcao_ids_1.data
    obm_2 = form_militar.obm_ids_2.data
    funcao_2 = form_militar.funcao_ids_2.data

    registros_ativos = (
        MilitarObmFuncao.query
        .filter_by(militar_id=militar.id)
        .filter(MilitarObmFuncao.data_fim.is_(None))
        .all()
    )

    for registro in registros_ativos:
        if registro.tipo == 1:
            if not obm_1 or not funcao_1:
                registro.data_fim = now_manaus_naive()
            elif registro.obm_id != obm_1 or registro.funcao_id != funcao_1:
                registro.data_fim = now_manaus_naive()
        elif registro.tipo == 2:
            if not obm_2 or not funcao_2:
                registro.data_fim = now_manaus_naive()
            elif registro.obm_id != obm_2 or registro.funcao_id != funcao_2:
                registro.data_fim = now_manaus_naive()

    registro_tipo_1 = MilitarObmFuncao.query.filter_by(
        militar_id=militar.id, tipo=1).filter(MilitarObmFuncao.data_fim.is_(None)).first()
    if obm_1 and funcao_1 and not registro_tipo_1:
        database.session.add(MilitarObmFuncao(
            militar_id=militar.id, obm_id=obm_1, funcao_id=funcao_1, tipo=1, data_criacao=now_manaus_naive()
        ))

    registro_tipo_2 = MilitarObmFuncao.query.filter_by(
        militar_id=militar.id, tipo=2).filter(MilitarObmFuncao.data_fim.is_(None)).first()
    if obm_2 and funcao_2 and not registro_tipo_2:
        database.session.add(MilitarObmFuncao(
            militar_id=militar.id, obm_id=obm_2, funcao_id=funcao_2, tipo=2, data_criacao=now_manaus_naive()
        ))


def _salvar_publicacoes_bg(militar, form_militar):
    """Grava as publicações de BG mapeadas em CAMPOS_BG (situacao_militar_2 já
    foi tratada manualmente em `_aplicar_situacao_extra_manual`)."""
    for campo in CAMPOS_BG:
        if campo == "situacao_militar_2":
            continue

        if not hasattr(form_militar, campo):
            continue

        valor = getattr(form_militar, campo).data
        bg_existente = PublicacaoBg.query.filter_by(militar_id=militar.id, tipo_bg=campo).first()

        if valor:
            if bg_existente:
                bg_existente.boletim_geral = valor
            else:
                database.session.add(PublicacaoBg(militar_id=militar.id, tipo_bg=campo, boletim_geral=valor))


def criar_militar_em_branco():
    """Cria e insere (flush, sem commit) um Militar novo com os metadados de
    quem/de onde veio o cadastro.

    O flush garante um `militar.id` já disponível para `salvar_dados_militar`,
    já que suas sub-rotinas gravam tabelas relacionadas (OBM/função,
    publicações de BG etc.) referenciando esse id. Quem chama decide o commit
    final — se algo der errado, um rollback desfaz também este insert.
    """
    militar = Militar(usuario_id=current_user.id, ip_address=get_user_ip())
    database.session.add(militar)
    database.session.flush()
    return militar


def salvar_dados_militar(militar, form_militar):
    """Aplica todos os dados validados do FormMilitar ao Militar e grava as
    coleções relacionadas (cursos, graduações, contatos, cônjuge, OBM/função,
    publicações de BG). Não comita a sessão — quem chama decide o commit."""
    _aplicar_dados_cadastrais(militar, form_militar)
    _aplicar_situacao_principal(militar, form_militar)
    _aplicar_situacao_extra_manual(militar)
    _aplicar_dados_academicos_e_ltip(militar, form_militar)
    _aplicar_dados_contato_e_endereco(militar, form_militar)
    _aplicar_dados_fisicos(militar, form_militar)
    _aplicar_boletins_promocao(militar, form_militar)

    _salvar_cursos_especializacao(militar, form_militar)
    _salvar_graduacoes(militar)
    _salvar_contatos_emergencia(militar)
    _salvar_conjuge(militar)
    _salvar_obm_funcao(militar, form_militar)
    _salvar_publicacoes_bg(militar, form_militar)

    sincronizar_blocos_funcionais(militar, form_militar)


def flashar_erros_formulario(form_militar):
    """Mostra, campo a campo, os erros de validação do WTForms (fluxo POST inválido)."""
    for field, errors in form_militar.errors.items():
        for error in errors:
            campo = getattr(form_militar, field)
            label = campo.label.text if hasattr(campo, 'label') else field
            flash(f"Erro no campo {label}: {error}", "danger")


def obter_info_auditoria_situacao(militar):
    """Retorna um texto 'Modificado por X em Y' com a última alteração de
    situação feita pela chefia via mapa da força, ou None se nunca houve uma."""
    ultima_auditoria = AuditoriaAtualizacaoCadastral.query.filter_by(
        militar_id=militar.id,
        acao="ATUALIZACAO_SITUACAO_CHEFIA"
    ).order_by(AuditoriaAtualizacaoCadastral.id.desc()).first()

    if not ultima_auditoria:
        return None

    data_aud = (
        getattr(ultima_auditoria, 'criado_em', None)
        or getattr(ultima_auditoria, 'data_hora', None)
        or getattr(ultima_auditoria, 'data_criacao', None)
    )
    data_str = data_aud.strftime('%d/%m/%Y às %H:%M') if data_aud else "Data desconhecida"

    user_rel = getattr(ultima_auditoria, 'usuario', None) or getattr(ultima_auditoria, 'user', None)
    nome_str = "Usuário não identificado"
    if user_rel:
        nome_str = (
            getattr(user_rel, 'nome_guerra', None)
            or getattr(user_rel, 'username', None)
            or getattr(user_rel, 'nome', "Usuário")
        )

    return f"Modificado por {nome_str} em {data_str}"
