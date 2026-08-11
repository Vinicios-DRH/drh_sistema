import unicodedata

from flask import current_app
import io
import math
from zoneinfo import ZoneInfo
from flask_wtf.csrf import validate_csrf
from flask_login import login_required
from flask import abort, json, request, jsonify, make_response, current_app
from random import shuffle
import os
import zipfile
import qrcode
import pytz
import pandas as pd
import base64
import matplotlib.pyplot as plt
import requests
import urllib
from src.decorators.utils_acumulo import b2_bucket_name, b2_client, b2_delete_all_versions, b2_upload_fileobj
from src.identificacao import buscar_pessoa_por_cpf, normaliza_matricula
from src.formatar_cpf import cadete_restantes, formatar_cpf, get_militar_por_user, is_cadete
from flask import render_template, redirect, url_for, request, flash, jsonify, session, send_file, make_response, \
    Response, stream_with_context
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import validate_csrf, generate_csrf
from werkzeug.utils import secure_filename
from src import app, database, bcrypt
from src.forms import (AtualizacaoCadastralForm, ControleConvocacaoForm, CriarSenhaForm, FichaAlunosForm, FormEsqueciSenha, FormFiltroMilitar, FormMilitarInativo, FormResetarSenhaPublica, FormViatura,
                       IdentificacaoForm, ImpactoForm, FormLogin, FormMilitar, FormCriarUsuario, FormMotoristas, FormFiltroMotorista, LtsAlunoForm, RecompensaAlunoForm,
                       RestricaoAlunoForm, SancaoAlunoForm, TabelaVencimentoForm, InativarAlunoForm, MatriculaConfirmForm)
from src.models import (ControleConvocacao, Convocacao, DocumentoMilitar, EfetivoDiarioOBM, HistoricoEfetivoDiario, ImportacaoMilitarHistorico, LogAcesso, LtsAlunos, Militar, MilitaresInativos, NomeConvocado, PostoGrad, Quadro, Obm, Localidade, Funcao, RecompensaAluno, RestricaoAluno, SancaoAluno, SegundoVinculo, SituacaoConvocacao, User, FuncaoUser, PublicacaoBg,
                        EstadoCivil, Especialidade, Destino, Motivo, Modalidade, Punicao, Comportamento, MilitarObmFuncao,
                        FuncaoGratificada,
                        MilitaresAgregados, MilitaresADisposicao, LicencaEspecial, LicencaParaTratamentoDeSaude, Paf,
                        Meses, Motoristas, Categoria, TabelaVencimento, ValorDetalhadoPostoGrad, FichaAlunos, AlunoInativo, Viaturas, ViaturaMilitar, MilitarGraduacao, MilitarContatoEmergencia, MilitarConjuge, LogExportacaoExcel, Curso, MilitarCurso, AuditoriaAtualizacaoCadastral, now_manaus_naive)
from src.querys import dados_para_mapa, obter_estatisticas_militares, login_usuario
from src.decorators.control import checar_ocupacao, militar_esta_no_escopo, obms_permitidas_para_usuario, sync_user_admin_obms_from_militar
from src.decorators.business_logic import processar_militares_a_disposicao, processar_militares_agregados, \
    processar_militares_le, processar_militares_lts
from datetime import datetime, date, timedelta
from io import BytesIO
from sqlalchemy.orm import joinedload, selectinload, load_only, aliased
from sqlalchemy import case, distinct, extract, func, not_, or_, cast, String, and_
from sqlalchemy.exc import IntegrityError
from openpyxl import Workbook
from openpyxl.styles import Border, Font, Side
from openpyxl.utils import get_column_letter
from decimal import Decimal, ROUND_HALF_UP, getcontext
from docx import Document
from urllib.parse import urlencode
from collections import defaultdict, Counter
from docx.shared import Pt
from docx.oxml.ns import qn
from src.decorators.formatar_datas import formatar_data_extenso, formatar_data_sem_zero
from src.decorators.email_utils import send_reset_password_email, verify_password_reset_token
import re
import plotly.graph_objs as go
import plotly.io as pio
from collections import defaultdict
from src.utils.sa_serialize import sa_to_dict
from sqlalchemy.inspection import inspect as sa_inspect
from src.security.perms import has_perm
from src.authz import is_super_or_perm, can_ferias_bypass_janela, is_super, require_perm
from src.utils.cadastro_status import cadastro_esta_completo
from src.utils.painel import (
    _obter_obm_principal,
    listar_situacoes_atualizacao,
    obter_resumo_atualizacao_cadastral,
    obter_militares_atualizacao_cadastral,
    serializar_militar_atualizacao,
    listar_obms_atualizacao,
    listar_postos_grad_atualizacao,
    obter_detalhes_militar_atualizacao,)
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from src.services.importar_militares import (
    ler_planilha,
    colunas_reconhecidas,
    colunas_nao_reconhecidas,
    analisar_importacao,
    importar_dataframe,
    salvar_historico_importacao,
)
from src.services.militar_situacao_service import (
    parse_date_flex,
    sincronizar_blocos_funcionais,
)
import time
from src.utils.utils import registrar_log_download
from dateutil.relativedelta import relativedelta

from src.routes.helpers import calcular_comportamento


@app.route('/ficha-alunos-soldados', methods=['GET', 'POST'])
@login_required
def ficha_aluno():
    form = FichaAlunosForm()
    ''''
    Pelotões:
        1° Pelotão: Rio Javari
        2° Pelotão: Rio Juruá
        3° Pelotão: Rio Japurá 
        4° Pelotão: Rio Purus
    '''
    # Preenchendo choices se necessário
    form.pelotao.choices = [('', '— Selecionar —'),
                            ('Rio Javari', 'Rio Javari'), ('Rio Juruá', 'Rio Juruá'),
                            ('Rio Japurá', 'Rio Japurá'), ('Rio Purus', 'Rio Purus')]

    form.estado_civil.choices = [('', '— Selecionar —'),
                                 ('Solteiro', 'Solteiro'), ('Casado', 'Casado'),
                                 ('Divorciado', 'Divorciado'), ('Viúvo', 'Viúvo')]

    form.estado.choices = [('', '— Selecionar —'),
                           ('AM', 'Amazonas'), ('AC', 'Acre')]

    form.categoria_cnh.choices = [('', '— Selecionar —'),
                                  ('A', 'A'), ('B', 'B'), ('AB',
                                                           'AB'), ('C', 'C'), ('D', 'D'),
                                  ('E', 'E'), ('AC', 'AC'), ('AD', 'AD'), ('AE', 'AE')]

    foto_url = None

    if form.validate_on_submit():
        foto_filename = None
        if form.foto.data:
            filename = secure_filename(form.foto.data.filename)
            foto_path = os.path.join('uploads/fotos', filename)
            form.foto.data.save(foto_path)
            foto_filename = foto_path

        novo_aluno = FichaAlunos(
            nome_completo=form.nome_completo.data or 'NÃO INFORMADO',
            nome_guerra=form.nome_guerra.data or None,
            idade_atual=form.idade_atual.data,
            cpf=form.cpf.data or None,
            rg=form.rg.data or None,
            estado_civil=form.estado_civil.data or None,
            nome_pai=form.nome_pai.data or 'NÃO INFORMADO',
            nome_mae=form.nome_mae.data or 'NÃO INFORMADO',
            pelotao=form.pelotao.data or None,
            email=form.email.data or None,
            telefone=form.telefone.data or None,
            telefone_emergencia=form.telefone_emergencia.data or None,
            rua=form.rua.data or None,
            bairro=form.bairro.data or None,
            complemento=form.complemento.data or None,
            estado=form.estado.data or None,
            formacao_academica=form.formacao_academica.data or 'NÃO INFORMADO',
            tipo_sanguineo=form.tipo_sanguineo.data or None,
            categoria_cnh=form.categoria_cnh.data or None,
            comportamento=(form.comportamento.data or 'Bom'),
            nota_comportamento=(
                form.nota_comportamento.data if form.nota_comportamento.data is not None else 5.0),
            caso_aluno_nao_resida_em_manaus=form.hospedagem_aluno_de_fora.data or None,
            foto=foto_filename or None,
            matricula=form.matricula.data or None
        )
        database.session.add(novo_aluno)
        database.session.commit()
        flash('Ficha do aluno salva com sucesso!', 'success')
        return redirect(url_for('ficha_aluno'))
    else:
        # Mostra erros explícitos (agora você vai ver por causa do padding/top/flash)
        if form.errors:
            flash('Corrija os campos destacados para salvar a ficha.', 'danger')

    return render_template('ficha_alunos.html', form=form, foto_url=foto_url, ano_atual=datetime.now().year,
                           aluno=None,          # <- importante
                           is_edicao=False      # <- flag
                           )


@app.route('/fichas')
@login_required
def listar_fichas():
    search = request.args.get('search', '').strip()

    query = FichaAlunos.query.filter(FichaAlunos.ativo == True)

    if search:
        query = query.filter(FichaAlunos.nome_completo.ilike(f"%{search}%"))

    alunos = query.order_by(FichaAlunos.nome_completo.asc()).all()

    idade_chart = Counter([a.idade_atual for a in alunos if a.idade_atual])
    cnh_chart = Counter([a.categoria_cnh for a in alunos if a.categoria_cnh])
    comportamento_raw = [a.comportamento.strip().capitalize()
                         for a in alunos if a.comportamento]
    comportamento_chart = Counter(comportamento_raw)

    return render_template(
        'fichas.html',
        alunos=alunos,
        search=search,
        idade_chart=idade_chart,
        cnh_chart=cnh_chart,
        comportamento_chart=comportamento_chart,
        ano_atual=datetime.now().year
    )


@app.route('/fichas/<int:aluno_id>')
def ficha_detalhada(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    return render_template('ficha_detalhada.html', aluno=aluno, ano_atual=datetime.now().year)


@app.route('/fichas/<int:aluno_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_ficha(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    form = FichaAlunosForm(obj=aluno)

    form.pelotao.choices = [('Rio Javari', 'Rio Javari'), ('Rio Juruá', 'Rio Juruá'),
                            ('Rio Japurá', 'Rio Japurá'), ('Rio Purus', 'Rio Purus')]
    form.estado_civil.choices = [('Solteiro', 'Solteiro'), ('Casado', 'Casado'),
                                 ('Divorciado', 'Divorciado'), ('Viúvo', 'Viúvo')]
    form.estado.choices = [('AM', 'Amazonas'), ('AC', 'Acre')]
    form.categoria_cnh.choices = [
        ('A', 'A (Moto)'), ('B', 'B (Carro)'), ('AB', 'AB (Moto + Carro)'),
        ('C', 'C (Caminhão)'), ('D', 'D (Ônibus)'), ('E', 'E (Carreta)'),
        ('AC', 'AC (Moto + Caminhão)'), ('AD', 'AD (Moto + Ônibus)'), ('AE', 'AE (Moto + Carreta)')]
    form.comportamento.choices = [
        ('Excepcional', 'Excepcional'), ('Ótimo', 'Ótimo'), ('Bom', 'Bom'), ('Insuficiente', 'Insuficiente'), ('Mau', 'Mau')]

    foto_url = url_for('static', filename=aluno.foto) if aluno.foto else url_for(
        'static', filename='img/avatar-default.png')

    if form.validate_on_submit():
        # Evita erro com FileStorage
        foto_antiga = aluno.foto  # salva foto atual
        form_data = {k: v for k, v in form.data.items() if k != 'foto'}
        for key, value in form_data.items():
            setattr(aluno, key, value)

        # Processa nova imagem se foi enviada
        if form.foto.data and form.foto.data.filename:
            from werkzeug.utils import secure_filename
            import os

            upload_folder = os.path.join('static', 'uploads', 'fotos')
            os.makedirs(upload_folder, exist_ok=True)

            filename = secure_filename(form.foto.data.filename)
            foto_path = os.path.join(upload_folder, filename)
            form.foto.data.save(foto_path)
            aluno.foto = foto_path
        else:
            aluno.foto = foto_antiga  # mantém a antiga se nenhuma nova enviada

        database.session.commit()
        flash("Ficha atualizada com sucesso!", "success")
        return redirect(url_for('listar_fichas', aluno_id=aluno.id))

    return render_template('ficha_alunos.html', form=form, foto_url=foto_url, aluno=aluno, ano_atual=datetime.now().year,
                           is_edicao=True)


@app.route('/fichas/<int:aluno_id>/inativar', methods=['GET', 'POST'])
@login_required
def inativar_aluno(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)

    if aluno.inativo:
        flash('Este aluno já está marcado como inativo.', 'warning')
        return redirect(url_for('editar_ficha', aluno_id=aluno.id))

    form = InativarAlunoForm()

    if form.validate_on_submit():
        novo_inativo = AlunoInativo(
            ficha_aluno_id=aluno.id,
            motivo_saida=form.motivo_saida.data,
            data_saida=form.data_saida.data
        )
        aluno.ativo = False
        database.session.add(novo_inativo)
        database.session.commit()
        flash('Aluno marcado como inativo com sucesso.', 'success')
        return redirect(url_for('listar_fichas'))

    return render_template('inativar_aluno.html', form=form, aluno=aluno, ano_atual=datetime.now().year)


@app.route('/alunos-inativos')
@login_required
def listar_alunos_inativos():
    nome = request.args.get('nome', '')
    motivo = request.args.get('motivo', '')

    query = AlunoInativo.query.join(FichaAlunos)

    if nome:
        query = query.filter(FichaAlunos.nome_completo.ilike(f'%{nome}%'))
    if motivo:
        query = query.filter(AlunoInativo.motivo_saida == motivo)

    alunos = query.order_by(AlunoInativo.data_saida.desc()).all()

    return render_template('listar_alunos_inativos.html', alunos=alunos, ano_atual=datetime.now().year)


@app.route('/pelotao/<slug>', methods=['GET'])
@login_required
def listar_por_pelotao(slug):
    mapa_pelotoes = {
        'rio-javari': 'Rio Javari',
        'rio-jurua': 'Rio Juruá',
        'rio-japura': 'Rio Japurá',
        'rio-purus': 'Rio Purus'
    }

    nome_pelotao = mapa_pelotoes.get(slug)
    if not nome_pelotao:
        abort(404)

    termo = request.args.get('termo', '').strip()
    query = FichaAlunos.query.filter(FichaAlunos.pelotao == nome_pelotao)

    if termo:
        query = query.filter(FichaAlunos.nome_completo.ilike(f'%{termo}%'))

    alunos = query.order_by(FichaAlunos.nome_completo.asc()).all()

    # GERAÇÃO DOS DADOS PARA OS GRÁFICOS
    idade_chart = Counter([a.idade_atual for a in alunos if a.idade_atual])
    cnh_chart = Counter([a.categoria_cnh for a in alunos if a.categoria_cnh])
    comportamento_raw = [a.comportamento.strip().capitalize()
                         for a in alunos if a.comportamento]
    comportamento_chart = Counter(comportamento_raw)

    return render_template('fichas.html',
                           alunos=alunos,
                           termo_busca=termo,
                           titulo=f'Alunos do {nome_pelotao}',
                           idade_chart=idade_chart,
                           cnh_chart=cnh_chart,
                           comportamento_chart=comportamento_chart,
                           ano_atual=datetime.now().year
                           )


@app.route('/fichas/<int:aluno_id>/lts', methods=['GET', 'POST'])
@login_required
def registrar_lts(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    form = LtsAlunoForm()

    if form.validate_on_submit():
        nova_lts = LtsAlunos(
            ficha_aluno_id=aluno.id,
            boletim_interno=form.boletim_interno.data,
            data_inicio=form.data_inicio.data,
            data_fim=form.data_fim.data,
            usuario_id=current_user.id
        )

        database.session.add(nova_lts)
        database.session.commit()
        flash('LTS registrada com sucesso!', 'success')
        return redirect(url_for('editar_ficha', aluno_id=aluno.id))

    return render_template('registrar_lts_aluno.html', form=form, aluno=aluno, ano_atual=datetime.now().year)


@app.route('/alunos-em-lts')
@login_required
def listar_alunos_em_lts():
    hoje = datetime.utcnow().date()

    licencas_ativas = LtsAlunos.query.join(FichaAlunos).filter(
        LtsAlunos.data_inicio <= hoje,
        LtsAlunos.data_fim >= hoje
    ).order_by(LtsAlunos.data_inicio.asc()).all()

    return render_template('alunos_em_lts.html', licencas=licencas_ativas, ano_atual=datetime.now().year)


@app.route('/fichas/<int:aluno_id>/restricao', methods=['GET', 'POST'])
@login_required
def registrar_restricao(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    form = RestricaoAlunoForm()

    if form.validate_on_submit():
        existe_igual = RestricaoAluno.query.filter_by(
            ficha_aluno_id=aluno.id,
            descricao=form.descricao.data,
            data_inicio=form.data_inicio.data,
            data_fim=form.data_fim.data
        ).first()

        if existe_igual:
            flash('Restrição já registrada para esse período.', 'warning')
            return redirect(url_for('editar_ficha', aluno_id=aluno.id))

        nova_restricao = RestricaoAluno(
            ficha_aluno_id=aluno.id,
            descricao=form.descricao.data,
            data_inicio=form.data_inicio.data,
            data_fim=form.data_fim.data,
            usuario_id=current_user.id
        )
        database.session.add(nova_restricao)
        database.session.commit()
        flash('Restrição registrada com sucesso!', 'success')
        return redirect(url_for('editar_ficha', aluno_id=aluno.id))

    return render_template('registrar_restricao.html', form=form, aluno=aluno, ano_atual=datetime.now().year)


@app.route('/restricoes-ativas')
@login_required
def restricoes_ativas():
    hoje = date.today()

    restricoes = RestricaoAluno.query.join(FichaAlunos).filter(
        RestricaoAluno.data_inicio <= hoje,
        RestricaoAluno.data_fim >= hoje
    ).order_by(RestricaoAluno.data_inicio.asc()).all()

    return render_template('restricoes_ativas.html', restricoes=restricoes, ano_atual=datetime.now().year)


@app.route('/restricoes-ativas/excel')
@login_required
def exportar_restricoes_excel():
    hoje = date.today()
    restricoes = RestricaoAluno.query.join(FichaAlunos).filter(
        RestricaoAluno.data_inicio <= hoje,
        RestricaoAluno.data_fim >= hoje
    ).all()

    dados = [{
        'Nome do Aluno': r.ficha_aluno.nome_completo,
        'Pelotão': r.ficha_aluno.pelotao,
        'Motivo': r.descricao,
        'Data Início': r.data_inicio.strftime('%d/%m/%Y'),
        'Data Fim': r.data_fim.strftime('%d/%m/%Y'),
        'Registrado por': r.usuario.nome,
        'Data Registro': r.data_criacao.strftime('%d/%m/%Y %H:%M'),
    } for r in restricoes]

    df = pd.DataFrame(dados)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Restrições Ativas')

    output.seek(0)
    return send_file(output, download_name='restricoes_ativas.xlsx', as_attachment=True)


@app.route('/restricoes-ativas/print')
@login_required
def imprimir_restricoes_ativas():
    hoje = date.today()
    restricoes = RestricaoAluno.query.join(FichaAlunos).filter(
        RestricaoAluno.data_inicio <= hoje,
        RestricaoAluno.data_fim >= hoje
    ).all()
    return render_template('restricoes_print.html', restricoes=restricoes)


@app.route('/fichas/<int:aluno_id>/imprimir')
@login_required
def imprimir_ficha_aluno(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    return render_template('ficha_detalhada_print.html', aluno=aluno)


@app.route('/dashboard-obms')
@login_required
def dashboard_obms():
    dados = dados_para_mapa()
    return render_template('dashboard_obms.html', dados=dados)


@app.route('/fichas/<int:aluno_id>/recompensa', methods=['GET', 'POST'])
@login_required
def registrar_recompensa(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    form = RecompensaAlunoForm()

    if form.validate_on_submit():
        nova = RecompensaAluno(
            ficha_aluno_id=aluno.id,
            natureza=form.natureza.data,
            autoridade=form.autoridade.data,
            boletim=form.boletim.data,
            discriminacao=form.discriminacao.data,
            usuario_id=current_user.id
        )
        database.session.add(nova)
        database.session.commit()
        flash('Recompensa registrada com sucesso!', 'success')
        return redirect(url_for('editar_ficha', aluno_id=aluno.id))

    return render_template('registrar_recompensa.html', form=form, aluno=aluno)


@app.route('/fichas/<int:aluno_id>/sancao', methods=['GET', 'POST'])
@login_required
def registrar_sancao(aluno_id):
    aluno = FichaAlunos.query.get_or_404(aluno_id)
    form = SancaoAlunoForm()

    if form.validate_on_submit():
        nova = SancaoAluno(
            ficha_aluno_id=aluno.id,
            natureza=form.natureza.data,
            numero_dias=form.numero_dias.data,
            boletim=form.boletim.data,
            data_inicio=form.data_inicio.data,
            data_fim=form.data_fim.data,
            discriminacao=form.discriminacao.data,
            usuario_id=current_user.id
        )
        database.session.add(nova)
        database.session.commit()
        flash('Sanção registrada com sucesso!', 'success')
        return redirect(url_for('editar_ficha', aluno_id=aluno.id))

    return render_template('registrar_sancao.html', form=form, aluno=aluno)


@app.route('/quiz')
def quiz():
    return render_template('quiz.html')
