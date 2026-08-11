
from flask_login import login_required
from flask import request
from src.identificacao import buscar_pessoa_por_cpf, normaliza_matricula
from src.formatar_cpf import formatar_cpf, get_militar_por_user
from flask import render_template, redirect, url_for, request, flash, session
from flask_login import login_user, login_required, current_user
from src import app, database, bcrypt
from src.forms import (AtualizacaoCadastralForm, IdentificacaoForm, FormLogin, MatriculaConfirmForm)
from src.models import (Militar, SegundoVinculo, User, FichaAlunos)

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
