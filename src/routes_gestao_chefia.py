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



def sanitizar_nome(texto):
    """Remove acentos, troca espaços por '_' e deixa minúsculo para usar em arquivos/pastas."""
    if not texto: return "doc"
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-zA-Z0-9]', '_', texto).lower()
    return re.sub(r'_+', '_', texto).strip('_')


def upload_pdf_para_servidor(file_obj, subfolder, novo_nome=None):
    """
    Tenta criar a pasta e fazer o upload do PDF.
    Se 'novo_nome' for fornecido, renomeia o arquivo antes de enviar.
    """
    headers = {"X-API-Key": API_BUCKET_KEY}
    
    try:
        # 1. Criar pasta (Ignora o 409 se já existir)
        requests.post(
            f"{API_BUCKET_URL}/bucket.php?action=mkdir",
            headers={**headers, "Content-Type": "application/json"},
            json={"folder": subfolder},
            timeout=10
        )
        
        # 2. Preparar nome do arquivo
        nome_arquivo_envio = file_obj.filename
        if novo_nome:
            extensao = nome_arquivo_envio.rsplit('.', 1)[-1].lower() if '.' in nome_arquivo_envio else 'pdf'
            nome_arquivo_envio = f"{novo_nome}.{extensao}"
            
        conteudo_arquivo = file_obj.read()
        files = {'file': (nome_arquivo_envio, conteudo_arquivo, file_obj.mimetype)}
        
        print(f"🚀 [UPLOAD INICIADO] Enviando '{nome_arquivo_envio}' para a pasta '{subfolder}'...")
        
        resposta = requests.post(
            f"{API_BUCKET_URL}/upload_pdf.php?folder={subfolder}",
            headers=headers, 
            files=files,
            timeout=30
        )
        
        print(f"📥 [API RESPONDEU] Status: {resposta.status_code} | Corpo: {resposta.text}")
        
        if resposta.status_code == 200:
            dados = resposta.json()
            if dados.get("success"):
                url_final = dados.get("url")
                if not url_final:
                    nome_arquivo_retornado = dados.get("filename")
                    folder_encoded = urllib.parse.quote(subfolder, safe='')
                    url_final = f"{API_BUCKET_URL}/download_pdf.php?folder={folder_encoded}&file={nome_arquivo_retornado}"
                return True, url_final
            else:
                return False, dados.get("message", "API retornou 200, mas success=False.")
        else:
            return False, f"Erro HTTP {resposta.status_code}: {resposta.text}"
            
    except Exception as e:
        print(f"❌ [ERRO DE CONEXÃO] {str(e)}")
        return False, f"Falha de conexão: {str(e)}"


# ==============================================================================
# ROTAS
# ==============================================================================


@app.route('/gestao-chefia', methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR DRH', 'DIRETOR', 'CHEFE', 'SUPER USER')
def gestao_chefia():
    permitidas = obms_permitidas_para_usuario(current_user)
    lista_obms = Obm.query.filter(Obm.id.in_(sorted(permitidas))).order_by(Obm.sigla.asc()).all()
    return render_template('gestao_chefia.html', lista_obms=lista_obms)


@app.route('/gestao-chefia/tabela/<int:obm_id>', methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR DRH', 'DIRETOR', 'CHEFE', 'SUPER USER')
def tabela_gestao_chefia(obm_id):
    if getattr(current_user, "funcao_user_id", None) != 6:
        permitidas = obms_permitidas_para_usuario(current_user)

        if obm_id not in permitidas:
            return "<div class='alert alert-danger'>Sem permissão para esta OBM.</div>", 403

    obm = Obm.query.get_or_404(obm_id)

    # =========================================================================
    # EFETIVO DA OBM
    # Exclui civis (funcao_id == 26)
    # =========================================================================
    militares = (
        Militar.query
        .join(
            MilitarObmFuncao,
            Militar.id == MilitarObmFuncao.militar_id
        )
        .filter(
            MilitarObmFuncao.obm_id == obm_id,
            MilitarObmFuncao.data_fim.is_(None),
            Militar.obm_funcoes.any(
                MilitarObmFuncao.funcao_id != 26
            )
        )
        .all()
    )

    # =========================================================================
    # MAPA DA SITUAÇÃO DIÁRIA DA OBM
    # =========================================================================
    registros_diarios = EfetivoDiarioOBM.query.filter_by(
        obm_id=obm_id
    ).all()

    mapa_diario = {
        registro.militar_id: registro
        for registro in registros_diarios
    }

    # =========================================================================
    # FÉRIAS VIGENTES
    # Não usa ano_referencia propositalmente.
    # Assim também cobre férias que atravessam dezembro/janeiro.
    # =========================================================================
    hoje = datetime.now().date()

    ids_militares = [militar.id for militar in militares]
    ferias_por_militar = {}

    if ids_militares:
        pafs_com_ferias_vigentes = (
            Paf.query
            .filter(
                Paf.militar_id.in_(ids_militares),

                or_(
                    and_(
                        Paf.primeiro_periodo_ferias <= hoje,
                        Paf.fim_primeiro_periodo >= hoje
                    ),
                    and_(
                        Paf.segundo_periodo_ferias <= hoje,
                        Paf.fim_segundo_periodo >= hoje
                    ),
                    and_(
                        Paf.terceiro_periodo_ferias <= hoje,
                        Paf.fim_terceiro_periodo >= hoje
                    )
                )
            )
            .all()
        )

        for paf in pafs_com_ferias_vigentes:
            periodos = [
                (
                    paf.primeiro_periodo_ferias,
                    paf.fim_primeiro_periodo
                ),
                (
                    paf.segundo_periodo_ferias,
                    paf.fim_segundo_periodo
                ),
                (
                    paf.terceiro_periodo_ferias,
                    paf.fim_terceiro_periodo
                )
            ]

            for inicio, fim in periodos:
                if inicio and fim and inicio <= hoje <= fim:
                    ferias_por_militar[paf.militar_id] = {
                        "inicio": inicio,
                        "fim": fim
                    }
                    break

    # =========================================================================
    # MOTORISTAS
    # =========================================================================
    motoristas_ativos = (
        Motoristas.query
        .filter(
            Motoristas.modified.is_(None),
            or_(
                Motoristas.desclassificar.is_(None),
                Motoristas.desclassificar != 'SIM'
            )
        )
        .all()
    )

    ids_motoristas = {
        motorista.militar_id
        for motorista in motoristas_ativos
    }

    # =========================================================================
    # DADOS AUXILIARES DA TELA
    # =========================================================================
    viaturas_obm = (
        Viaturas.query
        .filter_by(obm_id=obm_id)
        .order_by(Viaturas.prefixo.asc())
        .all()
    )

    ids_permitidos = [4, 5, 6, 8]

    modalidades = (
        Modalidade.query
        .filter(Modalidade.id.in_(ids_permitidos))
        .order_by(Modalidade.descricao.asc())
        .all()
    )

    cursos = Curso.query.order_by(Curso.nome.asc()).all()

    return render_template(
        'partial_tabela_gestao_chefia.html',
        obm=obm,
        militares=militares,
        mapa_diario=mapa_diario,
        ferias_por_militar=ferias_por_militar,
        ids_motoristas=ids_motoristas,
        viaturas_obm=viaturas_obm,
        modalidades=modalidades,
        cursos=cursos
    )


@app.route('/gestao-chefia/update', methods=['POST'])
@login_required
@checar_ocupacao('DIRETOR DRH', 'DIRETOR', 'CHEFE', 'SUPER USER')
def update_gestao_chefia():
    militar_id = request.form.get('militar_id', type=int)
    obm_id = request.form.get('obm_id', type=int) 
    modalidade_id = request.form.get('modalidade_id', type=int)
    inicio_periodo = request.form.get('inicio_periodo')
    fim_periodo = request.form.get('fim_periodo')
    
    presente_na_obm = request.form.get('presente_na_obm') == 'on'
    local_disposicao = request.form.get('local_disposicao')
    viatura_diaria_id = request.form.get('viatura_diaria_id', type=int)
    cursos_ids = request.form.getlist('cursos_ids[]')

    if not militar_id or not obm_id:
        return jsonify({"status": "error", "message": "Dados incompletos."}), 400

    militar = Militar.query.get_or_404(militar_id)

    if getattr(current_user, "funcao_user_id", None) != 6:
        permitidas = obms_permitidas_para_usuario(current_user)
        if not militar_esta_no_escopo(militar.id, permitidas):
            return jsonify({"status": "error", "message": "Militar fora do escopo da sua OBM."}), 403

    try:
        nome_militar_limpo = sanitizar_nome(militar.nome_guerra or militar.nome_completo)
        pasta_base_militar = f"obm_{obm_id}/militar_{militar.id}_{nome_militar_limpo}"

        # =========================================================
        # 1. UPLOAD DE LICENÇAS (COM EXCEÇÃO PARA "PRONTO" ID 8)
        # =========================================================
        efetivo = EfetivoDiarioOBM.query.filter_by(militar_id=militar.id, obm_id=obm_id).first()
        
        modalidade_antiga = efetivo.modalidade_id if efetivo else None
        url_comprovante_licenca = efetivo.comprovante_modalidade_url if efetivo else None
        
        arquivo_modalidade = request.files.get('arquivo_modalidade')
        
        # Ignora a obrigatoriedade de arquivo se for a modalidade 8 (Pronto)
        if modalidade_id and modalidade_id != 8:
            if arquivo_modalidade and arquivo_modalidade.filename:
                pasta_licencas = f"{pasta_base_militar}/licencas"
                mod_obj = Modalidade.query.get(modalidade_id)
                nome_documento_licenca = f"comprovante_{sanitizar_nome(mod_obj.descricao)}"
                
                sucesso, resultado = upload_pdf_para_servidor(arquivo_modalidade, pasta_licencas, novo_nome=nome_documento_licenca)
                if sucesso:
                    url_comprovante_licenca = resultado
                else:
                    return jsonify({"status": "error", "message": f"Falha no anexo da licença: {resultado}"}), 400
            else:
                # SE NÃO ENVIAR ARQUIVO NOVO, MAS MUDAR A LICENÇA: BLOQUEIA
                if modalidade_id != modalidade_antiga:
                    return jsonify({"status": "error", "message": "O envio do comprovante da nova licença/situação é obrigatório."}), 400
        else:
            url_comprovante_licenca = None

        # =========================================================
        # 2. ATUALIZAR EFETIVO DIÁRIO
        # =========================================================
        if not efetivo:
            efetivo = EfetivoDiarioOBM(militar_id=militar.id, obm_id=obm_id)
            database.session.add(efetivo)
            
        efetivo.modalidade_id = modalidade_id if modalidade_id else None
        efetivo.inicio_periodo = datetime.strptime(inicio_periodo, '%Y-%m-%d').date() if inicio_periodo else None
        efetivo.fim_periodo = datetime.strptime(fim_periodo, '%Y-%m-%d').date() if fim_periodo else None
        efetivo.comprovante_modalidade_url = url_comprovante_licenca 
        efetivo.presente_na_obm = presente_na_obm
        efetivo.local_disposicao = local_disposicao if not presente_na_obm else None
        efetivo.viatura_diaria_id = viatura_diaria_id if viatura_diaria_id else None
        efetivo.atualizado_em = now_manaus_naive()
        efetivo.atualizado_por = current_user.id
        database.session.add(efetivo)

        # =========================================================
        # 3. HISTÓRICO IMUTÁVEL
        # =========================================================
        historico = HistoricoEfetivoDiario(
            militar_id=militar.id, obm_id=obm_id, modalidade_id=efetivo.modalidade_id,
            inicio_periodo=efetivo.inicio_periodo, fim_periodo=efetivo.fim_periodo,
            comprovante_modalidade_url=efetivo.comprovante_modalidade_url, presente_na_obm=efetivo.presente_na_obm,
            local_disposicao=efetivo.local_disposicao, viatura_diaria_id=efetivo.viatura_diaria_id,
            data_registro=now_manaus_naive(), registrado_por=current_user.id
        )
        database.session.add(historico)

        # =========================================================
        # 4. UPLOAD DE ESPECIALIDADES (COM TRAVA DE OBRIGATORIEDADE)
        # =========================================================
        cursos_selecionados = [int(c) for c in cursos_ids if c.isdigit()]
        cursos_atuais = {mc.curso_id: mc for mc in militar.cursos_especializacao}
        pasta_especialidades = f"{pasta_base_militar}/especialidades"

        for cid in cursos_selecionados:
            arquivo_curso = request.files.get(f'arquivo_curso_{cid}')
            nova_url_curso = None
            
            if arquivo_curso and arquivo_curso.filename:
                curso_obj = Curso.query.get(cid)
                nome_documento_curso = f"comprovante_{sanitizar_nome(curso_obj.nome)}"
                
                sucesso, resultado = upload_pdf_para_servidor(arquivo_curso, pasta_especialidades, novo_nome=nome_documento_curso)
                if sucesso:
                    nova_url_curso = resultado
                else:
                    database.session.rollback()
                    return jsonify({"status": "error", "message": f"Falha no anexo da especialidade: {resultado}"}), 400
            elif cid not in cursos_atuais:
                database.session.rollback()
                return jsonify({"status": "error", "message": "O envio do comprovante é obrigatório para as novas especialidades selecionadas."}), 400

            if cid not in cursos_atuais:
                novo_curso = MilitarCurso(militar_id=militar.id, curso_id=cid, comprovante_url=nova_url_curso, criado_em=now_manaus_naive())
                database.session.add(novo_curso)
            else:
                if nova_url_curso:
                    cursos_atuais[cid].comprovante_url = nova_url_curso
                    database.session.add(cursos_atuais[cid]) 

        for cid, mc in cursos_atuais.items():
            if cid not in cursos_selecionados:
                database.session.delete(mc)

        # =========================================================
        # 5. AUDITORIA E COMMIT FINAL
        # =========================================================
        auditoria = AuditoriaAtualizacaoCadastral(
            militar_id=militar.id, user_id=current_user.id, acao="ATUALIZACAO_MAPA_FORCA_OBM",
            ip_address=request.remote_addr, observacao="Chefia atualizou situação diária, anexos e/ou viatura."
        )
        database.session.add(auditoria)
        database.session.commit()
        return jsonify({"status": "success", "message": "Mapa da força atualizado e arquivos salvos!"})

    except Exception as e:
        database.session.rollback()
        return jsonify({"status": "error", "message": f"Erro interno: {str(e)}"}), 500
