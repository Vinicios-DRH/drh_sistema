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

from src.routes_helpers import build_tabela_militares_query


@app.route("/militares", methods=["GET"])
@login_required
@checar_ocupacao(
    "DIRETOR",
    "CHEFE",
    "MAPA DA FORÇA",
    "DRH",
    "SUPER USER",
    "DIRETOR DRH",
    "ATUALIZACAO CADASTRAL",
)
def militares():
    f = FormFiltroMilitar()

    # ================================================================
    # CHOICES DOS FILTROS
    # ================================================================

    f.obm_id_1.choices = [
        (obm.id, obm.sigla)
        for obm in Obm.query.order_by(Obm.sigla.asc()).all()
    ]

    f.funcao_id.choices = [
        (funcao_item.id, funcao_item.ocupacao)
        for funcao_item in Funcao.query.order_by(Funcao.ocupacao.asc()).all()
    ]

    f.posto_grad_id.choices = [
        (posto.id, posto.sigla)
        for posto in PostoGrad.query.order_by(PostoGrad.sigla.asc()).all()
    ]

    f.quadro_id.choices = [
        (quadro.id, quadro.quadro)
        for quadro in Quadro.query.order_by(Quadro.quadro.asc()).all()
    ]

    f.especialidade_id.choices = [
        (especialidade.id, especialidade.ocupacao)
        for especialidade in Especialidade.query.order_by(
            Especialidade.ocupacao.asc()
        ).all()
    ]

    f.localidade_id.choices = [
        (localidade.id, localidade.sigla)
        for localidade in Localidade.query.order_by(
            Localidade.sigla.asc()
        ).all()
    ]

    f.modalidade_id.choices = [
        (modalidade.id, modalidade.descricao)
        for modalidade in Modalidade.query.order_by(
            Modalidade.descricao.asc()
        ).all()
    ]

    f.destino_id.choices = [
        (destino.id, destino.local)
        for destino in Destino.query.order_by(Destino.local.asc()).all()
    ]

    # ================================================================
    # PARÂMETROS DA REQUISIÇÃO
    # ================================================================

    page = request.args.get("page", 1, type=int)
    search = (request.args.get("search") or "").strip()

    obm_ids = request.args.getlist("obm_ids", type=int)
    funcao_ids = request.args.getlist("funcao_ids", type=int)
    posto_grad_ids = request.args.getlist("posto_grad_ids", type=int)
    quadro_ids = request.args.getlist("quadro_ids", type=int)
    especialidade_ids = request.args.getlist(
        "especialidade_ids",
        type=int,
    )
    localidade_ids = request.args.getlist(
        "localidade_ids",
        type=int,
    )
    modalidade_ids = request.args.getlist(
        "modalidade_ids",
        type=int,
    )
    destino_ids = request.args.getlist(
        "destino_ids",
        type=int,
    )

    # Situação é texto, portanto não utiliza type=int.
    situacoes = [
        situacao.strip().upper()
        for situacao in request.args.getlist("situacoes")
        if situacao and situacao.strip()
    ]

    sexo_filtro = (
        request.args.get("sexo") or ""
    ).strip().upper()

    # ================================================================
    # CONSULTA BASE
    # ================================================================

    query = (
        Militar.query
        .options(
            selectinload(Militar.obm_funcoes).selectinload(
                MilitarObmFuncao.obm
            ),
            selectinload(Militar.obm_funcoes).selectinload(
                MilitarObmFuncao.funcao
            ),
            selectinload(Militar.posto_grad),
            selectinload(Militar.quadro),
            selectinload(Militar.destino),
        )
        .filter(Militar.inativo.is_(False))
    )

    # ================================================================
    # PESQUISA POR TEXTO
    # ================================================================

    if search:
        search_text = search.strip()
        search_like = f"%{search_text}%"

        # Remove caracteres não numéricos para buscar CPF, RG e matrícula.
        search_digits = re.sub(r"\D", "", search_text)
        digits_like = (
            f"%{search_digits}%"
            if search_digits
            else None
        )

        def norm_text(column):
            return func.lower(
                func.unaccent(
                    func.coalesce(column, "")
                )
            )

        filtros_busca = [
            norm_text(Militar.nome_completo).like(
                func.lower(
                    func.unaccent(search_like)
                )
            ),
            norm_text(Militar.nome_guerra).like(
                func.lower(
                    func.unaccent(search_like)
                )
            ),
            func.coalesce(
                Militar.cpf,
                "",
            ).ilike(search_like),
            func.coalesce(
                Militar.rg,
                "",
            ).ilike(search_like),
            func.coalesce(
                Militar.matricula,
                "",
            ).ilike(search_like),
        ]

        if digits_like:
            filtros_busca.extend([
                func.regexp_replace(
                    func.coalesce(Militar.cpf, ""),
                    r"[^0-9]",
                    "",
                    "g",
                ).like(digits_like),

                func.regexp_replace(
                    func.coalesce(Militar.rg, ""),
                    r"[^0-9]",
                    "",
                    "g",
                ).like(digits_like),

                func.regexp_replace(
                    func.coalesce(Militar.matricula, ""),
                    r"[^0-9]",
                    "",
                    "g",
                ).like(digits_like),
            ])

        query = query.filter(
            or_(*filtros_busca)
        )

    # ================================================================
    # FILTROS DIRETOS DA TABELA MILITAR
    # ================================================================

    if posto_grad_ids:
        query = query.filter(
            Militar.posto_grad_id.in_(posto_grad_ids)
        )

    if quadro_ids:
        query = query.filter(
            Militar.quadro_id.in_(quadro_ids)
        )

    if especialidade_ids:
        query = query.filter(
            Militar.especialidade_id.in_(
                especialidade_ids
            )
        )

    if localidade_ids:
        query = query.filter(
            Militar.localidade_id.in_(
                localidade_ids
            )
        )

    if situacoes:
        query = query.filter(
            func.upper(
                func.trim(
                    func.coalesce(
                        Militar.situacao,
                        "",
                    )
                )
            ).in_(situacoes)
        )

    if modalidade_ids:
        query = query.filter(
            Militar.modalidade_id.in_(
                modalidade_ids
            )
        )

    if destino_ids:
        query = query.filter(
            Militar.destino_id.in_(
                destino_ids
            )
        )

    # ================================================================
    # FILTROS DE OBM E FUNÇÃO ATIVAS
    # ================================================================

    if obm_ids or funcao_ids:
        query = (
            query
            .join(
                MilitarObmFuncao,
                MilitarObmFuncao.militar_id == Militar.id,
            )
            .filter(
                MilitarObmFuncao.data_fim.is_(None)
            )
        )

        if obm_ids:
            query = query.filter(
                MilitarObmFuncao.obm_id.in_(
                    obm_ids
                )
            )

        if funcao_ids:
            query = query.filter(
                MilitarObmFuncao.funcao_id.in_(
                    funcao_ids
                )
            )

        query = query.distinct()

    # ================================================================
    # FILTRO DE SEXO
    # ================================================================

    sexo_normalizado = func.lower(
        func.trim(
            func.coalesce(
                Militar.sexo,
                "",
            )
        )
    )

    if sexo_filtro == "M":
        query = query.filter(
            sexo_normalizado.like("m%")
        )

    elif sexo_filtro == "F":
        query = query.filter(
            sexo_normalizado.like("f%")
        )

    # ================================================================
    # ORDENAÇÃO E PAGINAÇÃO
    # ================================================================

    per_page = 50

    query = query.order_by(
        Militar.nome_completo.asc()
    )

    militares_paginados = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    # ================================================================
    # FUNÇÕES AUXILIARES
    # ================================================================

    def fmt_cpf(cpf):
        digitos = re.sub(
            r"\D",
            "",
            cpf or "",
        )

        if len(digitos) == 11:
            return (
                f"{digitos[:3]}."
                f"{digitos[3:6]}."
                f"{digitos[6:9]}-"
                f"{digitos[9:11]}"
            )

        return cpf or ""

    # ================================================================
    # MONTAGEM DOS DADOS PARA O TEMPLATE
    # ================================================================

    militares = []

    for militar in militares_paginados.items:
        obm_funcoes_ativas = [
            vinculo
            for vinculo in militar.obm_funcoes
            if vinculo.data_fim is None
        ]

        obm_funcoes_ativas = sorted(
            obm_funcoes_ativas,
            key=lambda vinculo: (
                vinculo.data_criacao
                or datetime.min
            ),
            reverse=True,
        )

        obms_recentes = [
            vinculo.obm.sigla
            if vinculo.obm
            else "OBM não encontrada"
            for vinculo in obm_funcoes_ativas
        ]

        funcoes_recentes = [
            vinculo.funcao.ocupacao
            if vinculo.funcao
            else "Função não encontrada"
            for vinculo in obm_funcoes_ativas
        ]

        militares.append({
            "id": militar.id,
            "nome_completo": militar.nome_completo,
            "nome_guerra": militar.nome_guerra,
            "cpf": militar.cpf,
            "cpf_fmt": fmt_cpf(militar.cpf),
            "rg": militar.rg,
            "matricula": militar.matricula,
            "obms": obms_recentes,
            "funcoes": funcoes_recentes,
            "posto_grad": (
                militar.posto_grad.sigla
                if militar.posto_grad
                else ""
            ),
            "quadro": (
                militar.quadro.quadro
                if militar.quadro
                else ""
            ),
            "situacao": militar.situacao or "",
            "destino": (
                militar.destino.local
                if militar.destino
                else ""
            ),
        })

    # ================================================================
    # RENDERIZAÇÃO
    # ================================================================

    total = militares_paginados.total

    return render_template(
        "militares.html",
        militares=militares,
        form_militar=f,
        page=page,
        has_next=militares_paginados.has_next,
        has_prev=militares_paginados.has_prev,
        next_page=militares_paginados.next_num,
        prev_page=militares_paginados.prev_num,
        pages=militares_paginados.pages,
        total=total,
        start=(
            ((page - 1) * per_page) + 1
            if total
            else 0
        ),
        end=min(
            page * per_page,
            total,
        ),
        has_novo_militar=(
            "novo_militar"
            in current_app.view_functions
        ),
    )


@app.route("/militares-inativos", methods=['GET'])
@login_required
def militares_inativos():
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '', type=str)

        query = Militar.query.options(
            joinedload(Militar.posto_grad),
            joinedload(Militar.quadro),
            joinedload(Militar.especialidade),
            joinedload(Militar.localidade),
            joinedload(Militar.modalidade),
            joinedload(Militar.obm_funcoes)
        ).filter(Militar.modalidade.has(Modalidade.descricao.in_(['RESERVA', 'INATIVO'])))

        if search:
            query = query.filter(Militar.nome_completo.ilike(f"%{search}%"))

        militares_inativos = query.order_by(
            Militar.nome_completo.asc()).paginate(page=page, per_page=100)

        return render_template(
            'militares_inativos.html',
            militares=militares_inativos.items,
            page=page,
            has_next=militares_inativos.has_next,
            has_prev=militares_inativos.has_prev,
            next_page=militares_inativos.next_num,
            prev_page=militares_inativos.prev_num
        )

    except Exception as e:
        app.logger.error(f"Erro ao processar a requisição: {str(e)}")
        return jsonify({'error': 'Ocorreu um erro ao processar a requisição.', 'details': str(e)}), 500


@app.route("/tabela-militares", methods=["GET", "POST"])
@login_required
@checar_ocupacao(
    "DIRETOR",
    "CHEFE",
    "MAPA DA FORÇA",
    "SUPER USER",
    "DRH",
    "DIRETOR DRH",
    "ATUALIZACAO CADASTRAL",
)
def tabela_militares():
    today = date.today()

    try:
        page = request.args.get("page", 1, type=int)
        per_page = 50

        # Esta consulta já contém TODOS os filtros recebidos.
        query = build_tabela_militares_query()

        total_militares = (
            Militar.query
            .filter(Militar.inativo.is_(False))
            .count()
        )

        militares_filtrados = query.all()

        agregados_count = sum(
            1
            for militar in militares_filtrados
            if (militar.situacao or "").strip().upper() == "AGREGADO"
        )

        adisposicao_count = sum(
            1
            for militar in militares_filtrados
            if militar.modalidade_id == 2
        )

        militares_paginados = (
            query
            .order_by(Militar.nome_completo.asc())
            .paginate(
                page=page,
                per_page=per_page,
                error_out=False,
            )
        )

        militares_filtrados_data = []

        for militar in militares_paginados.items:
            obm_funcoes_ativas = sorted(
                [
                    vinculo
                    for vinculo in militar.obm_funcoes
                    if vinculo.data_fim is None
                ],
                # data_criacao é DateTime; use datetime.min, não date.min.
                key=lambda vinculo: vinculo.data_criacao or datetime.min,
                reverse=True,
            )

            obms = [
                vinculo.obm.sigla
                if vinculo.obm
                else "OBM não encontrada"
                for vinculo in obm_funcoes_ativas
            ]

            funcoes = [
                vinculo.funcao.ocupacao
                if vinculo.funcao
                else "Função não encontrada"
                for vinculo in obm_funcoes_ativas
            ]

            destino_txt = (
                militar.destino.local
                if militar.destino and militar.destino.local
                else "N/A"
            )

            inclusao_fmt = (
                militar.inclusao.strftime("%d/%m/%Y")
                if militar.inclusao
                else "N/A"
            )

            situacao_exibe = (militar.situacao or "").strip().upper()

            if not situacao_exibe:
                situacao_exibe = "N/A"

            # Modalidade permanece uma informação separada da situação.
            modalidade_exibe = (
                militar.modalidade.descricao
                if militar.modalidade and militar.modalidade.descricao
                else "N/A"
            )

            sexo_raw = (militar.sexo or "").strip().lower()
            sexo_exibe = (
                "Masculino"
                if sexo_raw.startswith("m")
                else "Feminino"
                if sexo_raw.startswith("f")
                else (militar.sexo or "N/A")
            )

            militares_filtrados_data.append({
                "id": militar.id,
                "nome_completo": militar.nome_completo or "N/A",
                "nome_guerra": militar.nome_guerra or "N/A",
                "sexo": sexo_exibe,
                "raca": militar.raca or "N/A",
                "cpf": militar.cpf or "N/A",
                "rg": militar.rg or "N/A",
                "matricula": militar.matricula or "N/A",
                "posto_grad": (
                    militar.posto_grad.sigla
                    if militar.posto_grad
                    else "N/A"
                ),
                "quadro": (
                    militar.quadro.quadro
                    if militar.quadro
                    else "N/A"
                ),
                "especialidade": (
                    militar.especialidade.ocupacao
                    if militar.especialidade
                    else "N/A"
                ),
                "localidade": (
                    militar.localidade.sigla
                    if militar.localidade
                    else "N/A"
                ),
                "situacao": situacao_exibe,
                "modalidade": modalidade_exibe,
                "destino": destino_txt,
                "inclusao": inclusao_fmt,
                "obms": obms,
                "funcoes": funcoes,
                "data_nascimento": (
                    militar.data_nascimento.strftime("%d/%m/%Y")
                    if militar.data_nascimento
                    else "N/A"
                ),
                "graduacao": militar.graduacao or "N/A",
                "grau_instrucao": militar.grau_instrucao or "N/A",
                "pos_graduacao": militar.pos_graduacao or "N/A",
                "mestrado": militar.mestrado or "N/A",
                "doutorado": militar.doutorado or "N/A",
            })

        return render_template(
            "relacao_militares.html",
            militares=militares_filtrados_data,
            total_militares=total_militares,
            militares_filtrados_count=militares_paginados.total,
            agregados_count=agregados_count,
            adisposicao_count=adisposicao_count,
            page=page,
            total_pages=militares_paginados.pages,
            has_next=militares_paginados.has_next,
            has_prev=militares_paginados.has_prev,
            per_page=per_page,
        )

    except Exception as exc:
        app.logger.exception("Erro ao processar /tabela-militares")
        return jsonify({
            "error": "Ocorreu um erro ao processar a requisição.",
            "details": str(exc),
        }), 500


@app.route("/militares-a-disposicao")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def militares_a_disposicao():
    militares_a_disposicao = MilitaresADisposicao.query.all()

    return render_template('militares_a_disposicao.html', militares=militares_a_disposicao)


@app.route("/militares-agregados")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def militares_agregados():
    militares_agregados = MilitaresAgregados.query.all()

    return render_template('militares_agregados.html', militares=militares_agregados)


@app.route("/licenca-especial")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def licenca_especial():
    militares_le = LicencaEspecial.query.all()

    return render_template('licenca_especial.html', militares_le=militares_le)


@app.route("/licenca-para-tratamento-de-saude")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def lts():
    militares_lts = LicencaParaTratamentoDeSaude.query.all()

    return render_template('licenca_para_tratamento_de_saude.html', militares_lts=militares_lts)
