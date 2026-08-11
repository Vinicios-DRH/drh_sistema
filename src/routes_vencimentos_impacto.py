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

from src.routes_helpers import arred, dias360_europeu


@app.route('/vencimentos/novo', methods=['GET', 'POST'])
@login_required
def novo_vencimento():
    form = TabelaVencimentoForm()

    if 'tabela_id' in session:
        form.nome.validators = []
        form.lei.validators = []
        form.data_inicio.validators = []
        form.data_fim.validators = []

    postos = PostoGrad.query.all()
    form.posto_grad.choices = [(p.id, p.sigla) for p in postos]

    if request.method == 'POST' and form.validate_on_submit():
        # Finalizar a tabela e ir para o cálculo
        if 'finalizar' in request.form:
            session.pop('tabela_id', None)
            flash("Tabela finalizada com sucesso!", "success")
            # Altere para seu endpoint real
            return redirect(url_for('home'))

        # Criar nova tabela se ainda não houver na sessão
        if 'tabela_id' not in session:
            tabela = TabelaVencimento(
                nome=form.nome.data,
                lei=form.lei.data,
                data_inicio=form.data_inicio.data,
                data_fim=form.data_fim.data
            )
            database.session.add(tabela)
            database.session.flush()
            session['tabela_id'] = tabela.id
        else:
            tabela = TabelaVencimento.query.get(session['tabela_id'])
            if tabela is None:
                session.pop('tabela_id', None)
                flash(
                    "A tabela anterior foi removida ou expirou. Por favor, inicie novamente.", "warning")
                return redirect(url_for('novo_vencimento'))

        valor = ValorDetalhadoPostoGrad(
            tabela_id=tabela.id,
            posto_grad_id=form.posto_grad.data,
            soldo=form.soldo.data,
            grat_tropa=form.grat_tropa.data,
            gams=form.gams.data,
            valor_bruto=form.valor_bruto.data,
            curso_25=form.curso_25.data,
            curso_30=form.curso_30.data,
            curso_35=form.curso_35.data,
            bruto_esp=form.bruto_esp.data,
            bruto_mestre=form.bruto_mestre.data,
            bruto_dout=form.bruto_dout.data,
            fg_1=form.fg_1.data,
            fg_2=form.fg_2.data,
            fg_3=form.fg_3.data,
            fg_4=form.fg_4.data,
            aux_moradia=form.aux_moradia.data,
            etapas_capital=form.etapas_capital.data,
            etapas_interior=form.etapas_interior.data,
            seg_hora=form.seg_hora.data,
            motorista_a=form.motorista_a.data,
            motorista_b=form.motorista_b.data,
            motorista_ab=form.motorista_ab.data,
            motorista_cde=form.motorista_cde.data,
            tecnico_raiox=form.tecnico_raiox.data,
            tecnico_lab=form.tecnico_lab.data,
            mecanico=form.mecanico.data,
            fluvial=form.fluvial.data,
            explosivista=form.explosivista.data,
            coe=form.coe.data,
            tripulante=form.tripulante.data,
            piloto=form.piloto.data,
            aviacao=form.aviacao.data,
            mergulhador=form.mergulhador.data
        )

        database.session.add(valor)
        database.session.commit()

        flash("Posto adicionado à tabela com sucesso!", "success")
        return redirect(url_for('novo_vencimento', step=2))

    return render_template("form_tabela_vencimento.html", form=form, step=request.args.get('step'))


getcontext().prec = 10


@app.route('/impacto/calcular', methods=['GET', 'POST'])
@login_required
def calcular_impacto():
    form = ImpactoForm()
    postos = PostoGrad.query.order_by(PostoGrad.id).all()
    form.posto_origem.choices = [(p.id, p.sigla) for p in postos]
    form.posto_destino.choices = [(p.id, p.sigla) for p in postos]

    resultado = None
    tabelas_usadas = []

    if request.method == 'GET' and request.args.get('show_modal') == '1':
        if "resultado" in session and "tabelas_usadas" in session:
            resultado = session.pop("resultado")
            tabelas_usadas = session.pop("tabelas_usadas")

    if request.method == 'POST' and form.validate_on_submit():
        data_inicio = form.data_inicio.data
        data_fim = form.data_fim.data
        efetivo = form.efetivo.data
        posto_origem_id = form.posto_origem.data
        posto_destino_id = form.posto_destino.data

        tabelas = TabelaVencimento.query.filter(
            TabelaVencimento.data_fim >= data_inicio,
            TabelaVencimento.data_inicio <= data_fim
        ).order_by(TabelaVencimento.data_inicio).all()

        if not tabelas:
            flash("Nenhuma tabela de vencimento encontrada para esse período.", "danger")
            return render_template("impacto_calculo.html", form=form)

        resultado_final = {
            "detalhes": [],
            "total": Decimal('0.00')
        }
        tabelas_usadas = []

        for tabela in tabelas:
            inicio_periodo = max(data_inicio, tabela.data_inicio)
            fim_periodo = min(data_fim, tabela.data_fim)

            dias = dias360_europeu(
                inicio_periodo, fim_periodo + timedelta(days=1))
            meses = Decimal(dias) / Decimal(30)
            coef = meses / Decimal(12)

            valor_origem = ValorDetalhadoPostoGrad.query.filter_by(
                tabela_id=tabela.id, posto_grad_id=posto_origem_id
            ).first()
            valor_destino = ValorDetalhadoPostoGrad.query.filter_by(
                tabela_id=tabela.id, posto_grad_id=posto_destino_id
            ).first()

            if not valor_origem or not valor_destino:
                flash(
                    f"Valores de postos não encontrados na tabela {tabela.nome}.", "danger")
                return render_template("impacto_calculo.html", form=form)

            diferenca = Decimal(valor_destino.valor_bruto) - \
                Decimal(valor_origem.valor_bruto)
            impacto_mensal = arred(diferenca * efetivo)
            retroativo = arred((impacto_mensal / Decimal(30)) * dias)
            ferias = arred((impacto_mensal / Decimal(3)) * coef)
            decimo = arred(impacto_mensal * coef)
            subtotal = retroativo + ferias + decimo

            resultado_final["detalhes"].append({
                "nome": tabela.nome,
                "inicio": tabela.data_inicio.strftime("%d/%m/%Y"),
                "fim": tabela.data_fim.strftime("%d/%m/%Y"),
                "dias": dias,
                "meses": str(meses),
                "coef": str(coef),
                "diferenca": str(diferenca),
                "impacto_mensal": str(impacto_mensal),
                "retroativo": str(retroativo),
                "ferias": str(ferias),
                "decimo": str(decimo),
                "total": str(subtotal)
            })

            resultado_final["total"] += subtotal

            tabelas_usadas.append({
                "nome": tabela.nome,
                "inicio": tabela.data_inicio.strftime("%d/%m/%Y"),
                "fim": tabela.data_fim.strftime("%d/%m/%Y")
            })

        # Cálculo do impacto atual fixo
        data_inicio_atual = date.today()
        data_fim_atual = data_fim
        dias_atual = dias360_europeu(
            data_inicio_atual, data_fim_atual + timedelta(days=1))
        meses_coef = Decimal(dias_atual) / Decimal(30)
        coef_proporcional = meses_coef / Decimal(12)

        tabela_atual = next((t for t in tabelas if t.data_inicio <=
                            data_inicio_atual and t.data_fim >= data_fim_atual), None)
        if tabela_atual:
            valor_origem_atual = ValorDetalhadoPostoGrad.query.filter_by(
                tabela_id=tabela_atual.id, posto_grad_id=posto_origem_id).first()
            valor_destino_atual = ValorDetalhadoPostoGrad.query.filter_by(
                tabela_id=tabela_atual.id, posto_grad_id=posto_destino_id).first()

            if valor_origem_atual and valor_destino_atual:
                diferenca_atual = Decimal(
                    valor_destino_atual.valor_bruto) - Decimal(valor_origem_atual.valor_bruto)
                impacto_mensal_atual = arred(diferenca_atual * efetivo)
                subtotal_atual = arred(impacto_mensal_atual * meses_coef)
                ferias_atual = arred(
                    (impacto_mensal_atual / Decimal(3)) * coef_proporcional)
                decimo_atual = arred(impacto_mensal_atual * coef_proporcional)
                total_sem_retroativo = subtotal_atual + ferias_atual + decimo_atual
                impacto_mensal_estimado = arred(
                    total_sem_retroativo / meses_coef)

                resultado_final["atual"] = {
                    "dias": dias_atual,
                    "meses_coef": str(meses_coef),
                    "coef": str(coef_proporcional),
                    "diferenca": str(diferenca_atual),
                    "impacto_mensal": str(impacto_mensal_atual),
                    "subtotal": str(subtotal_atual),
                    "ferias": str(ferias_atual),
                    "decimo": str(decimo_atual),
                    "total_sem_retroativo": str(total_sem_retroativo),
                    "impacto_mensal_estimado": str(impacto_mensal_estimado)
                }

        # REGISTRA IMPACTOS NA SESSÃO
        impactos_registrados = session.get("impactos_registrados", [])
        impactos_registrados.append(resultado_final)
        session["impactos_registrados"] = impactos_registrados

        session["resultado"] = resultado_final
        session["tabelas_usadas"] = tabelas_usadas

        params = urlencode({"show_modal": "1"})
        return redirect(f"{url_for('calcular_impacto')}?{params}")

    return render_template("impacto_calculo.html", form=form, resultado=resultado, tabelas_usadas=tabelas_usadas)
