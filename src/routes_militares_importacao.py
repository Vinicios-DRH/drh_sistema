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



@app.route("/militares/importar", methods=["GET"])
@login_required
@require_perm("NAV_MIL_ATIVOS_IMPORT")
def tela_importar_militares():
    obms = Obm.query.order_by(Obm.sigla).all()
    return render_template(
        "militares/importar_upload.html",
        obms=obms
    )


@app.route("/militares/importar/modelo", methods=["GET"])
@login_required
@require_perm("NAV_MIL_ATIVOS_IMPORT")
def download_modelo_importacao():
    # Ajuste o caminho de acordo com a pasta onde você salvou o arquivo no seu projeto
    caminho_arquivo = os.path.join(
        current_app.root_path, 'static/downloads', 'modelo_planilha_importacao.xlsx')

    return send_file(
        caminho_arquivo,
        as_attachment=True,
        download_name="modelo_planilha_importacao.xlsx"
    )


@app.route("/militares/importar/analisar", methods=["POST"])
@login_required
def analisar_importacao_militares():
    arquivo = request.files.get("arquivo")

    # Captura o modo escolhido no formulário de upload (padrão é misto)
    modo = request.form.get("modo", "misto")

    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo Excel ou CSV.", "danger")
        return redirect(url_for("tela_importar_militares"))

    try:
        nome_arquivo = arquivo.filename
        df = ler_planilha(arquivo)

        if df.empty:
            flash("A planilha está vazia.", "warning")
            return redirect(url_for("tela_importar_militares"))

        colunas_ok = colunas_reconhecidas(df)
        colunas_invalidas = colunas_nao_reconhecidas(df)

        if not colunas_ok:
            flash("Nenhuma coluna reconhecida para importação.", "warning")
            return redirect(url_for("tela_importar_militares"))

        campos_preselecionados = [c for c in colunas_ok if c != "obm"]

        # Passamos o MODO para a análise (para a prévia mostrar o resultado correto)
        resumo = analisar_importacao(df, campos_preselecionados, modo=modo)
        obms = Obm.query.order_by(Obm.sigla).all()

        json_str = df.to_json(orient="records", force_ascii=False)
        payload_b64 = base64.b64encode(
            json_str.encode("utf-8")).decode("utf-8")

        return render_template(
            "militares/importar_confirmacao.html",
            colunas_ok=colunas_ok,
            colunas_invalidas=colunas_invalidas,
            resumo=resumo,
            obms=obms,
            payload_b64=payload_b64,
            campos_preselecionados=campos_preselecionados,
            nome_arquivo=nome_arquivo,
            total_colunas=len(df.columns),
            modo=modo,  # <-- Enviamos para o template de confirmação
        )

    except Exception as e:
        flash(f"Erro ao analisar planilha: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))


@app.route("/militares/importar/reanalisar", methods=["POST"])
@login_required
def reanalisar_importacao_militares():
    payload_b64 = request.form.get("payload_b64")
    campos_selecionados = request.form.getlist("campos")
    nome_arquivo = request.form.get("nome_arquivo", "arquivo_importado")

    # Recupera o modo do formulário escondido na tela de confirmação
    modo = request.form.get("modo", "misto")

    if not payload_b64:
        flash("Dados da planilha não encontrados.", "danger")
        return redirect(url_for("tela_importar_militares"))

    if not campos_selecionados:
        flash("Selecione pelo menos um campo para reanalisar.", "warning")
        return redirect(url_for("tela_importar_militares"))

    try:
        json_bytes = base64.b64decode(payload_b64.encode("utf-8"))
        json_str = json_bytes.decode("utf-8")
        df = pd.read_json(io.StringIO(json_str), orient="records", dtype=False)

        colunas_ok = colunas_reconhecidas(df)
        colunas_invalidas = colunas_nao_reconhecidas(df)

        # Passamos o MODO novamente para a reanálise
        resumo = analisar_importacao(df, campos_selecionados, modo=modo)
        obms = Obm.query.order_by(Obm.sigla).all()

        return render_template(
            "militares/importar_confirmacao.html",
            colunas_ok=colunas_ok,
            colunas_invalidas=colunas_invalidas,
            resumo=resumo,
            obms=obms,
            payload_b64=payload_b64,
            campos_preselecionados=campos_selecionados,
            nome_arquivo=nome_arquivo,
            total_colunas=len(df.columns),
            modo=modo,  # <-- Mantemos o modo vivo no template
        )

    except Exception as e:
        flash(f"Erro ao reanalisar planilha: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))


@app.route("/militares/importar/confirmar", methods=["POST"])
@login_required
def confirmar_importacao_militares():
    payload_b64 = request.form.get("payload_b64")
    campos_selecionados = request.form.getlist("campos")

    # Captura o modo invisível (Misto, Apenas Inserir, etc)
    modo = request.form.get("modo", "misto")

    # NOVO: Captura os Radio Buttons (Complementar ou Sobrescrever)
    regra_atualizacao = request.form.get("regra_atualizacao", "complementar")

    aplicar_obm = request.form.get("aplicar_obm")
    obm_id = request.form.get("obm_id")
    nome_arquivo = request.form.get("nome_arquivo", "arquivo_importado")

    if not payload_b64:
        flash("Dados da planilha não encontrados para importação.", "danger")
        return redirect(url_for("tela_importar_militares"))

    if not campos_selecionados:
        flash("Selecione pelo menos um campo para importar.", "warning")
        return redirect(url_for("tela_importar_militares"))

    try:
        json_bytes = base64.b64decode(payload_b64.encode("utf-8"))
        json_str = json_bytes.decode("utf-8")
        df = pd.read_json(io.StringIO(json_str), orient="records", dtype=False)
    except Exception as e:
        current_app.logger.exception(
            "Erro ao reconstruir DataFrame da importação.")
        flash(
            f"Erro ao ler os dados da planilha para importação: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))

    obm_id_final = None
    if aplicar_obm == "1" and obm_id:
        try:
            obm_id_final = int(obm_id)
        except ValueError:
            flash("OBM inválida selecionada.", "danger")
            return redirect(url_for("tela_importar_militares"))

    try:
        relatorio = importar_dataframe(
            df=df,
            campos_selecionados=campos_selecionados,
            modo=modo,  # <-- O modo é entregue ao motor de importação aqui!
            regra_atualizacao=regra_atualizacao,  # <-- E a regra de atualização também!
            obm_id=obm_id_final,
            usuario_id=current_user.id,
        )
    except Exception as e:
        current_app.logger.exception(
            "Erro durante a importação dos militares.")
        flash(f"Erro ao importar planilha: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))

    try:
        salvar_historico_importacao(
            usuario_id=current_user.id,
            nome_arquivo=nome_arquivo,
            modo=modo,  # Salva o modo no histórico pra auditoria
            campos_selecionados=campos_selecionados,
            relatorio=relatorio,
            total_linhas=len(df),
            obm_id=obm_id_final,
        )
    except Exception as e:
        current_app.logger.exception("Erro ao salvar histórico da importação.")
        flash(
            f"Importação concluída, mas falhou ao salvar o histórico: {str(e)}", "warning")

    session["ultimo_relatorio_importacao_militares"] = relatorio
    session["ultimo_nome_arquivo_importacao_militares"] = nome_arquivo
    session["ultimo_modo_importacao_militares"] = modo
    session["ultimo_campos_importacao_militares"] = campos_selecionados

    flash(
        f"Importação concluída. Inseridos: {relatorio['inseridos']} | "
        f"Atualizados: {relatorio['atualizados']} | "
        f"Ignorados: {relatorio['ignorados']}",
        "success"
    )

    return redirect(url_for("resultado_importacao_militares"))


@app.route("/militares/importar/historico", methods=["GET"])
@login_required
def historico_importacao_militares():
    historicos = (
        ImportacaoMilitarHistorico.query
        .order_by(ImportacaoMilitarHistorico.criado_em.desc())
        .limit(100)
        .all()
    )

    print("TOTAL HISTORICOS:", len(historicos))

    return render_template(
        "militares/importar_historico.html",
        historicos=historicos
    )


@app.route("/militares/importar/historico/<int:historico_id>", methods=["GET"])
@login_required
def detalhe_historico_importacao_militares(historico_id):
    historico = ImportacaoMilitarHistorico.query.get_or_404(historico_id)

    campos = []
    relatorio = {}

    try:
        if historico.campos_json:
            campos = json.loads(historico.campos_json)
    except Exception:
        campos = []

    try:
        if historico.relatorio_json:
            relatorio = json.loads(historico.relatorio_json)
    except Exception:
        relatorio = {}

    return render_template(
        "militares/importar_historico_detalhe.html",
        historico=historico,
        campos=campos,
        relatorio=relatorio,
    )


@app.route("/militares/importar/resultado", methods=["GET"])
@login_required
def resultado_importacao_militares():
    relatorio = session.get("ultimo_relatorio_importacao_militares")
    nome_arquivo = session.get("ultimo_nome_arquivo_importacao_militares")
    modo = session.get("ultimo_modo_importacao_militares")
    campos_selecionados = session.get("ultimo_campos_importacao_militares", [])

    if not relatorio:
        flash("Nenhum resultado de importação disponível.", "warning")
        return redirect(url_for("tela_importar_militares"))

    return render_template(
        "militares/importar_resultado.html",
        relatorio=relatorio,
        nome_arquivo=nome_arquivo,
        modo=modo,
        campos_selecionados=campos_selecionados,
    )


# @app.route("/painel-efetivo/api")
# def painel_efetivo_publico_api():
#     try:
#         q = (request.args.get("q") or "").strip()
#         status = (request.args.get("status") or "").strip()
#         obm_id = request.args.get("obm_id", type=int)
#         posto_grad_id = request.args.get("posto_grad_id", type=int)
#         modalidade_id = request.args.get("modalidade_id", type=int)
#         page = request.args.get("page", default=1, type=int)
#         per_page = request.args.get("per_page", default=50, type=int)

#         # Verifica se é a "consulta automática da TV" (sem nenhum filtro de busca e na página 1)
#         # Se a pessoa estiver digitando um nome pra buscar, não queremos usar o cache
#         is_consulta_padrao = not any(
#             [q, status, obm_id, posto_grad_id, modalidade_id]) and page == 1

#         # SE FOR A CONSULTA DA TV E O CACHE AINDA ESTIVER DENTRO DOS 5 MINUTOS:
#         agora = time.time()
#         if is_consulta_padrao and CACHE_PAINEL["dados"] and (agora - CACHE_PAINEL["ultima_atualizacao"] < TEMPO_CACHE_SEGUNDOS):
#             return jsonify(CACHE_PAINEL["dados"])

#         # ======== AQUI OCORRE O GASTO DE EGRESS (SUPABASE) ========
#         estatisticas = obter_estatisticas_militares()
#         resumo_atualizacao = obter_resumo_atualizacao_cadastral(
#             obm_id=obm_id, posto_grad_id=posto_grad_id, modalidade_id=modalidade_id,
#         )
#         militares, total_filtrado = obter_militares_atualizacao_cadastral(
#             q=q, status=status, obm_id=obm_id, posto_grad_id=posto_grad_id,
#             modalidade_id=modalidade_id, page=page, per_page=per_page,
#         )

#         militares_data = [serializar_militar_atualizacao(m) for m in militares]

#         resposta_final = {
#             "ok": True,
#             "estatisticas": estatisticas,
#             "resumo_atualizacao": resumo_atualizacao,
#             "militares": militares_data,
#             "q": q, "status": status, "obm_id": obm_id,
#             "posto_grad_id": posto_grad_id, "modalidade_id": modalidade_id,
#             "page": page, "per_page": per_page,
#             "total_filtrado": total_filtrado,
#             "total_paginas": (total_filtrado + per_page - 1) // per_page,
#             "atualizado_em": datetime.now(ZoneInfo("America/Manaus")).strftime("%d/%m/%Y %H:%M:%S"),
#         }

#         # SE FOI A CONSULTA PADRÃO, SALVAMOS O RESULTADO NO CACHE PARA OS PRÓXIMOS 5 MINUTOS
#         if is_consulta_padrao:
#             CACHE_PAINEL["dados"] = resposta_final
#             CACHE_PAINEL["ultima_atualizacao"] = agora

#         return jsonify(resposta_final)

#     except Exception as e:
#         print(f"Erro ao carregar API do painel público: {e}")
#         return jsonify({"ok": False, "error": "Erro ao carregar dados"}), 500
