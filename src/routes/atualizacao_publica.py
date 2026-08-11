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

from src.routes.helpers import _limpa_sessao_validacao


@app.route('/atualizacao-cadastral', methods=['GET', 'POST'])
def atualizacao_cadastral():
    form = IdentificacaoForm()

    if form.validate_on_submit():
        print("VALIDOU ✅")
        cpf_raw = form.cpf.data
        email_digitado = form.email.data.strip().lower()

        # mantém seu formato padrão com máscara
        cpf_formatado = formatar_cpf(cpf_raw)

        # 👉 NOVO: procurar em Militar OU FichaAlunos
        pessoa = buscar_pessoa_por_cpf(cpf_formatado)
        if not pessoa:
            flash("⚠️ CPF não encontrado no sistema (Militar/Aluno). Verifique e tente novamente ou contate a DRH.", "danger")
            return render_template("atualizacao/identificacao.html", form=form)

        session['email_atualizacao'] = email_digitado

        # Já existe User com esse CPF?
        user = User.query.filter_by(cpf=cpf_formatado).first()
        if user:
            flash(
                "⚠️ Já existe uma conta vinculada a este CPF. Faça login para continuar.", "warning")
            return redirect(url_for('login_atualizacao'))

        # 👉 Guarda no fluxo de validação de identidade
        session['cpf_em_validacao'] = cpf_formatado
        session['pessoa_tipo'] = pessoa['tipo']           # 'militar' | 'aluno'
        session['pessoa_id'] = pessoa['obj'].id           # id correspondente

        return redirect(url_for('confirmar_matricula'))

    return render_template("atualizacao/identificacao.html", form=form)


@app.route('/confirmar-matricula', methods=['GET', 'POST'])
def confirmar_matricula():
    cpf = session.get('cpf_em_validacao')
    pessoa_tipo = session.get('pessoa_tipo')  # 'militar' | 'aluno'
    pessoa_id = session.get('pessoa_id')

    if not cpf or not pessoa_tipo or not pessoa_id:
        flash("Sessão expirada ou inválida. Refaça a identificação.", "warning")
        return redirect(url_for('atualizacao_cadastral'))

    form = MatriculaConfirmForm()

    # Carrega a pessoa do tipo correto
    if pessoa_tipo == 'militar':
        pessoa = Militar.query.get(pessoa_id)
        if not pessoa:
            flash("Registro militar não encontrado para o CPF em validação.", "danger")
            _limpa_sessao_validacao()
            return redirect(url_for('atualizacao_cadastral'))
        nome_pessoa = getattr(pessoa, 'nome_completo',
                              getattr(pessoa, 'nome', ''))
        matricula_oficial = pessoa.matricula

    else:  # 'aluno'
        pessoa = FichaAlunos.query.get(pessoa_id)
        if not pessoa:
            flash("Registro de aluno não encontrado para o CPF em validação.", "danger")
            _limpa_sessao_validacao()
            return redirect(url_for('atualizacao_cadastral'))
        nome_pessoa = getattr(pessoa, 'nome_completo', '')
        matricula_oficial = pessoa.matricula

    if form.validate_on_submit():
        matricula_informada = (form.matricula_completa.data or "").strip()

        if normaliza_matricula(matricula_informada) != normaliza_matricula(matricula_oficial or ""):
            flash("❌ Matrícula não confere com nossos registros para este CPF.", "danger")
            return render_template('atualizacao/confirmar_matricula.html',
                                   form=form, cpf=cpf, militar_nome=nome_pessoa)

        session['matricula_validada'] = True
        # mantém pessoa_tipo/pessoa_id já na sessão

        flash("✅ Identidade confirmada com sucesso. Crie sua senha.", "success")
        return redirect(url_for('criar_senha', cpf=cpf))

    return render_template('atualizacao/confirmar_matricula.html',
                           form=form, cpf=cpf, militar_nome=nome_pessoa,
                           matricula=matricula_oficial)


@app.route('/formulario-atualizacao-cadastral', methods=['GET', 'POST'])
@login_required
def formulario_atualizacao_cadastral():
    if current_user.funcao_user_id != 12:
        flash("⚠️ Acesso restrito à atualização cadastral.", "danger")
        return redirect(url_for('home'))

    # Busca o militar vinculado ao CPF do usuário logado
    militar = Militar.query.filter_by(cpf=current_user.cpf).first()

    if not militar:
        flash("❌ Dados do militar não encontrados.", "danger")
        return redirect(url_for('home'))

    form = AtualizacaoCadastralForm(obj=militar)

    if form.validate_on_submit():
        militar.celular = form.celular.data
        militar.email = form.email.data
        militar.endereco = form.endereco.data
        militar.complemento = form.complemento.data
        militar.cidade = form.cidade.data
        militar.estado = form.estado.data
        militar.grau_instrucao = form.grau_instrucao.data

        database.session.commit()

        vinculo = SegundoVinculo.query.filter_by(militar_id=militar.id).first()
        if not vinculo:
            vinculo = SegundoVinculo(militar_id=militar.id)

        vinculo.possui_vinculo = form.possui_vinculo.data
        vinculo.quantidade_vinculos = form.quantidade_vinculos.data
        vinculo.descricao_vinculo = form.descricao_vinculo.data
        vinculo.horario_inicio = form.horario_inicio.data
        vinculo.horario_fim = form.horario_fim.data

        database.session.add(vinculo)
        database.session.commit()
        flash("✅ Dados atualizados com sucesso!", "success")
        return redirect(url_for('ficha_atualizada'))

    return render_template('atualizacao/formulario_cadastro.html', form=form)


@app.route("/login-militar", methods=['GET', 'POST'])
def login_atualizacao():
    if current_user.is_authenticated:
        militar = get_militar_por_user(current_user)
        session['militar_id'] = militar.id
        if not militar:
            flash("Não foi possível localizar seus dados de militar.", "danger")
            return redirect(url_for("home"))
        return redirect(url_for('home_atualizacao'))

    form_login = FormLogin()

    if form_login.validate_on_submit() and 'botao_submit_login' in request.form:
        cpf_formatado = form_login.cpf.data.strip()
        usuario = User.query.filter_by(cpf=cpf_formatado).first()

        if usuario and bcrypt.check_password_hash(usuario.senha, form_login.senha.data):
            if usuario.funcao_user_id == 12:
                login_user(usuario, remember=form_login.lembrar_dados.data)
                militar = get_militar_por_user(usuario)
                if not militar:
                    flash("Não foi possível localizar seus dados de militar.", "danger")
                    return redirect(url_for("home"))
                flash('Login realizado com sucesso.', 'success')
                return redirect(url_for('home_atualizacao'))
            else:
                flash(
                    'Este usuário não tem permissão para acessar a atualização cadastral.', 'danger')
        else:
            flash('CPF ou senha incorretos.', 'danger')

    return render_template("atualizacao/login_atualizacao.html", form_login=form_login)


@app.route('/ficha-atualizada')
@login_required
def ficha_atualizada():
    militar = Militar.query.filter_by(cpf=current_user.cpf).first_or_404()
    segundo_vinculo = SegundoVinculo.query.filter_by(
        militar_id=militar.id).first()

    return render_template(
        'atualizacao/ficha_atualizada.html',
        militar=militar,
        segundo_vinculo=segundo_vinculo
    )
