
from flask_wtf.csrf import validate_csrf
from flask_login import login_required
from flask import request, jsonify, make_response
import os
import zipfile
import qrcode
import pandas as pd
from flask import render_template, redirect, url_for, request, flash, jsonify, send_file, make_response
from flask_login import login_required
from flask_wtf.csrf import validate_csrf, generate_csrf
from werkzeug.utils import secure_filename
from src import app, database
from src.forms import (ControleConvocacaoForm)
from src.models import (ControleConvocacao, Convocacao, NomeConvocado, SituacaoConvocacao)
from src.decorators.control import checar_ocupacao
from datetime import datetime
from io import BytesIO
from collections import defaultdict, Counter
from collections import defaultdict

from src.routes.helpers import calcular_semana


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('SUPER USER')
def dashboard():
    data = None
    if request.method == 'POST':
        convocados = int(request.form['convocados'])
        faltaram = int(request.form['faltaram'])
        desistiram = int(request.form['desistiram'])
        data_input = request.form['data']
        data_dt = datetime.strptime(data_input, '%Y-%m-%d')

        vagas_abertas = faltaram + desistiram
        semana = calcular_semana(data_dt)

        data_dict = {
            'Situação': ['Presentes', 'Faltaram', 'Desistiram', 'Vagas Abertas'],
            'Quantidade': [convocados - vagas_abertas, faltaram, desistiram, vagas_abertas]
        }

        # Salvar no banco
        registro = Convocacao(
            data=datetime.strptime(data_input, '%Y-%m-%d'),
            convocados=convocados,
            faltaram=faltaram,
            desistiram=desistiram,
            vagas_abertas=vagas_abertas,
            semana=semana
        )
        database.session.add(registro)
        database.session.commit()

        return render_template('dashboard.html', data=data_dict)

    return render_template('dashboard.html', data=None)


@app.route('/export-dashboard', methods=['POST'])
def export_dashboard():
    data = request.json
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
    output.seek(0)
    return send_file(output, download_name='dashboard.xlsx', as_attachment=True)


@app.route('/relatorio-convocacao', methods=['GET'])
@login_required
def relatorio_convocacao():
    registros = Convocacao.query.order_by(Convocacao.data).all()

    dados_por_semana = defaultdict(list)
    totais_semanais = {}
    somatorios_geral = {
        "convocados": 0,
        "presentes": 0,
        "faltaram": 0,
        "desistiram": 0,
        "vagas": 0
    }

    for r in registros:
        presentes = r.convocados - r.faltaram - r.desistiram
        vagas = r.faltaram + r.desistiram

        item = {
            "data": r.data.strftime('%d/%m/%Y'),
            "convocados": r.convocados,
            "faltaram": r.faltaram,
            "desistiram": r.desistiram,
            "presentes": presentes,
            "vagas": vagas
        }

        semana = r.semana
        dados_por_semana[semana].append(item)

        somatorios_geral["convocados"] += r.convocados
        somatorios_geral["presentes"] += presentes
        somatorios_geral["faltaram"] += r.faltaram
        somatorios_geral["desistiram"] += r.desistiram
        somatorios_geral["vagas"] += vagas

        if semana not in totais_semanais:
            totais_semanais[semana] = {
                "convocados": 0,
                "presentes": 0,
                "faltaram": 0,
                "desistiram": 0,
                "vagas": 0
            }

        totais_semanais[semana]["convocados"] += r.convocados
        totais_semanais[semana]["presentes"] += presentes
        totais_semanais[semana]["faltaram"] += r.faltaram
        totais_semanais[semana]["desistiram"] += r.desistiram
        totais_semanais[semana]["vagas"] += vagas

    dados_ordenados = dict(
        sorted(dados_por_semana.items(), key=lambda x: int(x[0].split()[-1])))
    totais_ordenados = dict(
        sorted(totais_semanais.items(), key=lambda x: int(x[0].split()[-1])))

    return render_template('relatorio.html', dados=dados_ordenados, totais_semanais=totais_ordenados, somatorios=somatorios_geral)


@app.route('/relatorio-convocacao/excel', methods=['GET'])
def relatorio_convocacao_excel():
    registros = Convocacao.query.order_by(Convocacao.data).all()
    dados = []

    for r in registros:
        presentes = r.convocados - r.faltaram - r.desistiram
        vagas = r.faltaram + r.desistiram
        dados.append({
            "Data": r.data.strftime('%Y-%m-%d'),
            "Convocados": r.convocados,
            "Faltaram": r.faltaram,
            "Desistiram": r.desistiram,
            "Presentes": presentes,
            "Vagas Abertas": vagas
        })

    df = pd.DataFrame(dados)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Convocacoes')
    output.seek(0)

    return send_file(output, download_name="convocacoes_admin.xlsx", as_attachment=True)


@app.route('/adicionar-convocacao', methods=['GET', 'POST'])
@login_required
def adicionar_convocacao():
    form = ControleConvocacaoForm()

    # Situações
    form.situacao_convocacao_id.choices = [
        (s.id, s.situacao) for s in SituacaoConvocacao.query.all()
    ]

    # Nomes (apenas o texto do nome na label)
    nomes = NomeConvocado.query.all()
    form.nome.choices = [(n.id, n.nome) for n in nomes]

    # ➊  ———  dicionário p/ preencher via JS
    nomes_data = {
        n.id: {
            "inscricao": n.inscricao or "",
            "classificacao": n.classificacao or "",
            "nota_final": n.nota_final or "",
        } for n in nomes
    }

    if form.validate_on_submit():
        selected_nome = NomeConvocado.query.get(form.nome.data)
        novo = ControleConvocacao(
            classificacao=form.classificacao.data,
            inscricao=form.inscricao.data,
            nome=selected_nome.nome,
            nota_final=form.nota_final.data,
            ordem_de_convocacao=form.ordem_de_convocacao.data,
            apresentou=form.apresentou.data,
            situacao_convocacao_id=form.situacao_convocacao_id.data,
            matricula=form.matricula.data,
            numero_da_matricula_doe=form.numero_da_matricula_doe.data,
            bg_matricula_doe=form.bg_matricula_doe.data,
            portaria_convocacao=form.portaria_convocacao.data,
            bg_portaria_convocacao=form.bg_portaria_convocacao.data,
            doe_portaria_convocacao=form.doe_portaria_convocacao.data,
            notificacao_pessoal=form.notificacao_pessoal.data,
            termo_desistencia=form.termo_desistencia.data,
            siged_desistencia=form.siged_desistencia.data
        )
        database.session.add(novo)
        database.session.delete(selected_nome)  # remove da fila
        database.session.commit()

        flash('Registro salvo com sucesso!', 'success')
        # ajuste a rota conforme seu sistema
        return redirect(url_for('adicionar_convocacao'))

    return render_template('form_convocacao.html', form=form, nomes_data=nomes_data)


@app.route('/controle-convocacao', methods=['GET'])
@login_required
def controle_convocacao():
    page = request.args.get('page', 1, type=int)
    per_page = 100
    search = request.args.get('search', '').strip()

    # coleta todos os filtros
    filtros = {
        'classificacao': request.args.get('classificacao', '').strip(),
        'inscricao': request.args.get('inscricao', '').strip(),
        'nota_final': request.args.get('nota_final', '').strip(),
        'ordem_de_convocacao': request.args.get('ordem_de_convocacao', '').strip(),
        # 'sim' | 'nao' | None
        'apresentou': request.args.get('apresentou'),
        'situacao_convocacao_id': request.args.get('situacao_convocacao_id', type=int),
        'matricula': request.args.get('matricula'),
        'numero_da_matricula_doe': request.args.get('numero_da_matricula_doe', '').strip(),
        'bg_matricula_doe': request.args.get('bg_matricula_doe', '').strip(),
        'portaria_convocacao': request.args.get('portaria_convocacao', '').strip(),
        'bg_portaria_convocacao': request.args.get('bg_portaria_convocacao', '').strip(),
        'doe_portaria_convocacao': request.args.get('doe_portaria_convocacao', '').strip(),
        'notificacao_pessoal': request.args.get('notificacao_pessoal'),
        'termo_desistencia': request.args.get('termo_desistencia'),
        'siged_desistencia': request.args.get('siged_desistencia', '').strip(),
    }

    query = ControleConvocacao.query

    # busca rápida por nome
    if search:
        query = query.filter(ControleConvocacao.nome.ilike(f'%{search}%'))

    # aplica filtros textuais (LIKE)
    like_map = {
        'classificacao': ControleConvocacao.classificacao,
        'inscricao': ControleConvocacao.inscricao,
        'nota_final': ControleConvocacao.nota_final,
        'ordem_de_convocacao': ControleConvocacao.ordem_de_convocacao,
        'numero_da_matricula_doe': ControleConvocacao.numero_da_matricula_doe,
        'bg_matricula_doe': ControleConvocacao.bg_matricula_doe,
        'portaria_convocacao': ControleConvocacao.portaria_convocacao,
        'bg_portaria_convocacao': ControleConvocacao.bg_portaria_convocacao,
        'doe_portaria_convocacao': ControleConvocacao.doe_portaria_convocacao,
        'siged_desistencia': ControleConvocacao.siged_desistencia,
    }
    for campo, coluna in like_map.items():
        if filtros[campo]:
            query = query.filter(coluna.ilike(f"% {filtros[campo]} %"))

    # filtros exatos / booleanos
    if filtros['situacao_convocacao_id']:
        query = query.filter(
            ControleConvocacao.situacao_convocacao_id == filtros['situacao_convocacao_id'])
    bool_map = {
        'apresentou': ControleConvocacao.apresentou,
        'matricula': ControleConvocacao.matricula,
        'notificacao_pessoal': ControleConvocacao.notificacao_pessoal,
        'termo_desistencia': ControleConvocacao.termo_desistencia,
    }
    for campo, coluna in bool_map.items():
        if filtros[campo] in ('sim', 'nao'):
            query = query.filter(coluna.is_(filtros[campo] == 'sim'))

    convocacoes_paginadas = query.order_by(
        ControleConvocacao.id.asc()).paginate(page=page, per_page=per_page)

    # dados para o gráfico
    situacoes_list = [
        c.situacao.situacao if c.situacao else 'Indefinido'
        for c in convocacoes_paginadas.items
    ]
    contagem_situacoes = dict(Counter(situacoes_list))

    csrf_token = generate_csrf()
    return render_template(
        'controle_convocacao.html',
        convocacoes=convocacoes_paginadas,
        contagem_situacoes=contagem_situacoes,
        csrf_token=csrf_token          # <- aqui
    )


@app.route('/importar-convocados', methods=['GET', 'POST'])
@login_required
def importar_convocados():
    if request.method == 'POST':
        arquivo = request.files['arquivo']
        if arquivo.filename.endswith('.xlsx'):
            filename = secure_filename(arquivo.filename)

            # Garante que a pasta 'uploads' existe
            os.makedirs('uploads', exist_ok=True)

            caminho = os.path.join('uploads', filename)
            arquivo.save(caminho)

            df = pd.read_excel(caminho)

            for _, row in df.iterrows():
                nome = NomeConvocado(
                    nome=row['nome'],
                    inscricao=row.get('inscricao', ''),
                    classificacao=row.get('classificacao', ''),
                    nota_final=row.get('nota_final', '')
                )
                database.session.add(nome)
            database.session.commit()

            flash('Nomes importados com sucesso!', 'success')
            return redirect(url_for('adicionar_convocacao'))
        else:
            flash('Formato inválido. Envie um arquivo .xlsx', 'danger')

    return render_template('importar_convocados.html')


@app.route('/gerar-qrcodes', methods=['GET', 'POST'])
@login_required
def gerar_qrcodes():
    if request.method == 'POST':

        arquivo = request.files.get('arquivo')

        if not arquivo:
            flash('Selecione um arquivo válido.', 'danger')
            return redirect(request.url)

        extensao = arquivo.filename.rsplit('.', 1)[-1].lower()

        if extensao not in ['xlsx', 'csv']:
            flash('Envie um arquivo XLSX ou CSV válido.', 'danger')
            return redirect(request.url)

        try:

            # ==========================
            # LEITURA DO ARQUIVO
            # ==========================

            if extensao == 'xlsx':

                df = pd.read_excel(arquivo)

            else:

                try:
                    df = pd.read_csv(
                        arquivo,
                        sep=None,
                        engine='python',
                        encoding='utf-8'
                    )

                except UnicodeDecodeError:

                    arquivo.seek(0)

                    df = pd.read_csv(
                        arquivo,
                        sep=None,
                        engine='python',
                        encoding='latin1'
                    )

            # ==========================
            # NORMALIZA COLUNAS
            # ==========================

            df.columns = (
                df.columns
                .str.replace('\ufeff', '', regex=False)
                .str.strip()
                .str.lower()
            )
            # print(df.columns.tolist())
            colunas_obrigatorias = {
                'nome_completo',
                'qrcode_link'
            }
            if not colunas_obrigatorias.issubset(df.columns):

                flash(
                    'O arquivo deve conter as colunas nome_completo e qrcode_link.',
                    'danger'
                )

                return redirect(request.url)
            # Mantém somente as colunas necessárias
            df = df[['nome_completo', 'qrcode_link']].copy()
            # Remove linhas completamente vazias
            df = df.dropna(how='all')
            # ==========================
            # NOME DO ZIP
            # ==========================

            nome_base = os.path.splitext(
                secure_filename(arquivo.filename)
            )[0]

            if not nome_base:
                nome_base = 'qrcodes'

            # ==========================
            # GERA ZIP
            # ==========================

            buffer_zip = BytesIO()

            nomes_utilizados = set()

            with zipfile.ZipFile(
                buffer_zip,
                'w',
                zipfile.ZIP_DEFLATED
            ) as zf:

                for _, row in df.iterrows():

                    nome = str(
                        row.get('nome_completo', '')
                    ).strip()

                    link = str(
                        row.get('qrcode_link', '')
                    ).strip()

                    if not nome or not link:
                        continue

                    qr_img = qrcode.make(link)

                    img_bytes = BytesIO()

                    qr_img.save(
                        img_bytes,
                        format='PNG'
                    )

                    img_bytes.seek(0)

                    nome_seguro = secure_filename(nome)

                    if not nome_seguro:
                        nome_seguro = 'qrcode'

                    arquivo_png = f'{nome_seguro}.png'

                    contador = 2

                    while arquivo_png in nomes_utilizados:

                        arquivo_png = (
                            f'{nome_seguro}_{contador}.png'
                        )

                        contador += 1

                    nomes_utilizados.add(arquivo_png)

                    zf.writestr(
                        arquivo_png,
                        img_bytes.read()
                    )

            buffer_zip.seek(0)

            return send_file(
                buffer_zip,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'{nome_base}_qrcodes.zip'
            )

        except Exception as e:

            flash(
                f'Erro ao processar arquivo: {str(e)}',
                'danger'
            )

            return redirect(request.url)

    return render_template('gerar_qrcodes.html')


@app.route('/controle-convocacao/exportar', methods=['GET'])
@login_required
def exportar_convocacoes():
    filtros = {
        'classificacao': request.args.get('classificacao', '').strip(),
        'inscricao': request.args.get('inscricao', '').strip(),
        'nota_final': request.args.get('nota_final', '').strip(),
        'ordem_de_convocacao': request.args.get('ordem_de_convocacao', '').strip(),
        'apresentou': request.args.get('apresentou'),
        'situacao_convocacao_id': request.args.get('situacao_convocacao_id', type=int),
        'matricula': request.args.get('matricula'),
        'numero_da_matricula_doe': request.args.get('numero_da_matricula_doe', '').strip(),
        'bg_matricula_doe': request.args.get('bg_matricula_doe', '').strip(),
        'portaria_convocacao': request.args.get('portaria_convocacao', '').strip(),
        'bg_portaria_convocacao': request.args.get('bg_portaria_convocacao', '').strip(),
        'doe_portaria_convocacao': request.args.get('doe_portaria_convocacao', '').strip(),
        'notificacao_pessoal': request.args.get('notificacao_pessoal'),
        'termo_desistencia': request.args.get('termo_desistencia'),
        'siged_desistencia': request.args.get('siged_desistencia', '').strip(),
    }

    query = ControleConvocacao.query

    # filtros LIKE
    like_map = {
        'classificacao': ControleConvocacao.classificacao,
        'inscricao': ControleConvocacao.inscricao,
        'nota_final': ControleConvocacao.nota_final,
        'ordem_de_convocacao': ControleConvocacao.ordem_de_convocacao,
        'numero_da_matricula_doe': ControleConvocacao.numero_da_matricula_doe,
        'bg_matricula_doe': ControleConvocacao.bg_matricula_doe,
        'portaria_convocacao': ControleConvocacao.portaria_convocacao,
        'bg_portaria_convocacao': ControleConvocacao.bg_portaria_convocacao,
        'doe_portaria_convocacao': ControleConvocacao.doe_portaria_convocacao,
        'siged_desistencia': ControleConvocacao.siged_desistencia,
    }
    for campo, coluna in like_map.items():
        if filtros[campo]:
            query = query.filter(coluna.ilike(f"%{filtros[campo]}%"))

    if filtros['situacao_convocacao_id']:
        query = query.filter(
            ControleConvocacao.situacao_convocacao_id == filtros['situacao_convocacao_id'])

    bool_map = {
        'apresentou': ControleConvocacao.apresentou,
        'matricula': ControleConvocacao.matricula,
        'notificacao_pessoal': ControleConvocacao.notificacao_pessoal,
        'termo_desistencia': ControleConvocacao.termo_desistencia,
    }
    for campo, coluna in bool_map.items():
        if filtros[campo] in ('sim', 'nao'):
            query = query.filter(coluna.is_(filtros[campo] == 'sim'))

    registros = query.order_by(ControleConvocacao.id.asc()).all()

    data = []
    for c in registros:
        data.append({
            'Classificação': c.classificacao,
            'Inscrição': c.inscricao,
            'Nome': c.nome,
            'Nota Final': c.nota_final,
            'Ordem Convocação': c.ordem_de_convocacao,
            'Apresentou': 'Sim' if c.apresentou else 'Não',
            'Situação': c.situacao.situacao if c.situacao else '-',
            'Matrícula': 'Sim' if c.matricula else 'Não',
            'Nº Mat. DOE': c.numero_da_matricula_doe,
            'BG Mat. DOE': c.bg_matricula_doe,
            'Portaria Conv.': c.portaria_convocacao,
            'BG Portaria': c.bg_portaria_convocacao,
            'DOE Portaria': c.doe_portaria_convocacao,
            'Notif. Pessoal': 'Sim' if c.notificacao_pessoal else 'Não',
            'Termo Desist.': 'Sim' if c.termo_desistencia else 'Não',
            'SIGED Desist.': c.siged_desistencia,
            'Criado em': c.data_criacao.strftime('%d/%m/%Y') if c.data_criacao else '-'
        })

    df = pd.DataFrame(data)

    # Criar buffer na memória para o arquivo Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=convocacoes_filtradas.xlsx"
    response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response


@app.route('/atualizar-campo-convocacao', methods=['POST'])
@login_required
def atualizar_campo_convocacao():
    dados = request.get_json()

    token = request.headers.get("X-CSRFToken", "")
    try:
        validate_csrf(token)
    except Exception:
        return jsonify({'sucesso': False, 'erro': 'CSRF inválido'}), 400

    convoc_id = dados.get('id')
    campo = dados.get('campo')
    valor = dados.get('valor', '')

    # campos que podem ser editados inline
    campos_permitidos = {
        'ordem_de_convocacao': str,
        'apresentou': bool,
        'situacao_convocacao_id': int,
        'matricula': bool,
        'numero_da_matricula_doe': str,
        'bg_matricula_doe': str,
        'portaria_convocacao': str,
        'bg_portaria_convocacao': str,
        'doe_portaria_convocacao': str,
        'notificacao_pessoal': bool,
        'termo_desistencia': bool,
        'siged_desistencia': str
    }

    if campo not in campos_permitidos:
        return jsonify({'sucesso': False, 'erro': 'Campo não permitido'}), 400

    conv = ControleConvocacao.query.get_or_404(convoc_id)

    tipo = campos_permitidos[campo]

    try:
        if tipo is bool:
            valor = str(valor).strip().lower() in ('1', 'true', 'sim', 'on')
        elif tipo is int:
            valor = int(valor)
        else:
            valor = valor.strip()
    except Exception:
        return jsonify({'sucesso': False, 'erro': 'Erro ao converter valor'}), 400

    setattr(conv, campo, valor)
    database.session.commit()

    return jsonify({'sucesso': True})
