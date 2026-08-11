
from flask_login import login_required
from flask import request, jsonify
import pytz
from src.formatar_cpf import formatar_cpf, get_militar_por_user
from flask import render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from src import app, database, bcrypt
from src.forms import (CriarSenhaForm, FormEsqueciSenha, FormResetarSenhaPublica, FormLogin)
from src.models import (Militar, User, FichaAlunos)
from src.querys import login_usuario
from datetime import datetime
from src.decorators.email_utils import send_reset_password_email, verify_password_reset_token

from src.routes.helpers import (
    get_user_ip,
    _somente_numeros,
    _obms_do_militar_por_vinculos,
    _limpa_sessao_validacao,
)


@app.route('/criar-senha/<cpf>', methods=['GET', 'POST'])
def criar_senha(cpf):
    cpf = formatar_cpf(cpf)
    cpf_norm = _somente_numeros(cpf)

    # checagem de fluxo e correspondência
    if not session.get('matricula_validada') or session.get('cpf_em_validacao') != cpf:
        flash("Valide sua identidade antes de criar a senha.", "warning")
        return redirect(url_for('atualizacao_cadastral'))

    pessoa_tipo = session.get('pessoa_tipo')
    pessoa_id = session.get('pessoa_id')

    if not pessoa_tipo or not pessoa_id:
        flash("Sessão expirada ou inválida. Refaça a identificação.", "warning")
        return redirect(url_for('atualizacao_cadastral'))

    form = CriarSenhaForm()

    # Já tem conta?
    usuario_existente = (
        User.query
        .filter(
            (User.cpf == cpf) | (User.cpf_norm == cpf_norm)
        )
        .first()
    )
    if usuario_existente:
        flash("⚠️ Este CPF já possui uma conta ativa. Tente fazer login.", "warning")
        _limpa_sessao_validacao()
        return redirect(url_for('login'))

    # Carrega a pessoa do tipo correto
    if pessoa_tipo == 'militar':
        pessoa = Militar.query.get(pessoa_id)
        if not pessoa:
            flash("❌ Militar não encontrado para este CPF.", "danger")
            _limpa_sessao_validacao()
            return redirect(url_for('atualizacao_cadastral'))

        nome_user = getattr(pessoa, 'nome_completo',
                            getattr(pessoa, 'nome', '')) or ''
    else:
        pessoa = FichaAlunos.query.get(pessoa_id)
        if not pessoa:
            flash("❌ Aluno não encontrado para este CPF.", "danger")
            _limpa_sessao_validacao()
            return redirect(url_for('atualizacao_cadastral'))

        nome_user = getattr(pessoa, 'nome_completo', '') or ''

    if form.validate_on_submit():
        try:
            senha_hash = bcrypt.generate_password_hash(
                form.senha.data
            ).decode('utf-8')

            novo_usuario = User(
                nome=nome_user,
                email=session.get('email_atualizacao'),
                cpf=cpf,                 # com máscara
                cpf_norm=cpf_norm,      # só números
                senha=senha_hash,
                funcao_user_id=12,      # USUÁRIO COMUM
            )

            if pessoa_tipo == 'militar':
                obm_id_1, obm_id_2 = _obms_do_militar_por_vinculos(pessoa)

                novo_usuario.tipo_perfil = "MILITAR"
                novo_usuario.militar_id = pessoa.id
                novo_usuario.obm_id_1 = obm_id_1
                novo_usuario.obm_id_2 = obm_id_2
                novo_usuario.localidade_id = getattr(
                    pessoa, 'localidade_id', None)

                # importante: antes do commit
                if hasattr(pessoa, 'usuario_id'):
                    pessoa.usuario_id = novo_usuario.id  # ainda não existe aqui, então flush abaixo
            else:
                novo_usuario.tipo_perfil = "MILITAR"  # ou "ALUNO", se teu sistema usar isso
                novo_usuario.militar_id = None
                novo_usuario.obm_id_1 = 26
                novo_usuario.obm_id_2 = None
                novo_usuario.localidade_id = None

            database.session.add(novo_usuario)
            database.session.flush()

            if pessoa_tipo == 'militar' and hasattr(pessoa, 'usuario_id'):
                pessoa.usuario_id = novo_usuario.id

            database.session.commit()

            _limpa_sessao_validacao()
            flash("✅ Conta criada com sucesso! Agora você pode fazer login.", "success")
            return redirect(url_for('login_atualizacao'))

        except Exception as e:
            database.session.rollback()
            flash(f"Erro ao criar conta: {str(e)}", "danger")

    return render_template(
        'atualizacao/criar_senha.html',
        form=form,
        cpf=cpf
    )


@app.route('/acesso-negado')
def acesso_negado():
    """Rota para exibir a página de acesso negado."""
    return render_template('acesso_negado.html')


@app.errorhandler(403)
def erro_acesso_proibido(e):
    """
    Sempre que qualquer parte do sistema gritar 'abort(403)', 
    o Flask intercepta e joga o usuário para a rota acesso_negado.
    """
    return redirect(url_for('acesso_negado'))


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()

    cpf = data.get("cpf")
    senha = data.get("senha")

    if not cpf or not senha:
        return jsonify({"status": "erro", "mensagem": "CPF e senha são obrigatórios"}), 400

    user = login_usuario(cpf, senha)

    if user:
        return jsonify({
            "status": "sucesso",
            "mensagem": "Login realizado com sucesso",
            "usuario": {
                "id": user.id,
                "nome": user.nome,
                "cpf": user.cpf,
                "email": user.email,
                "obm1": user.obm1.sigla if user.obm1 else None,
                "obm2": user.obm2.sigla if user.obm2 else None,
                "funcao_user_id": user.funcao_user_id,
            }
        }), 200
    else:
        return jsonify({"status": "erro", "mensagem": "CPF ou senha inválidos"}), 401

# RESET DE SENHA - ROTA PÚBLICA PARA SOLICITAÇÃO DE LINK POR E-MAIL, SEM REQUERER LOGIN


@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha_admin():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = FormEsqueciSenha()

    if form.validate_on_submit():
        cpf_informado = form.cpf.data.strip()

        # mesma lógica do login admin
        usuario = User.query.filter_by(cpf=cpf_informado).first()

        # resposta genérica para não ficar revelando conta válida/inválida
        if usuario and usuario.email and usuario.funcao_user_id != 12:
            try:
                send_reset_password_email(usuario, area="admin")
            except Exception as e:
                print(f"Erro ao enviar e-mail admin: {e}")

        flash("Se existir uma conta com esse CPF e e-mail válido, enviaremos um link de recuperação.", "info")
        return redirect(url_for("login"))

    return render_template("auth/esqueci_senha_admin.html", form=form)


@app.route("/esqueci-senha-militar", methods=["GET", "POST"])
def esqueci_senha_militar():
    if current_user.is_authenticated:
        return redirect(url_for("home_atualizacao"))

    form = FormEsqueciSenha()

    if form.validate_on_submit():
        cpf_formatado = form.cpf.data.strip()

        # mesma lógica do login militar
        usuario = User.query.filter_by(
            cpf=cpf_formatado, funcao_user_id=12).first()

        if usuario and usuario.email:
            try:
                send_reset_password_email(usuario, area="militar")
            except Exception as e:
                print(f"Erro ao enviar e-mail militar: {e}")

        flash("Se existir uma conta com esse CPF e e-mail válido, enviaremos um link de recuperação.", "info")
        return redirect(url_for("login_atualizacao"))

    return render_template("auth/esqueci_senha_militar.html", form=form)


@app.route("/resetar-senha/<token>", methods=["GET", "POST"])
def resetar_senha_publica(token):
    if current_user.is_authenticated:
        logout_user()

    data = verify_password_reset_token(token)

    if not data:
        flash("Este link é inválido ou expirou.", "danger")
        return redirect(url_for("login"))

    user_id = data.get("user_id")
    area = data.get("area")

    usuario = User.query.get(user_id)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("login"))

    form = FormResetarSenhaPublica()

    if form.validate_on_submit():
        usuario.senha = bcrypt.generate_password_hash(
            form.senha.data).decode("utf-8")
        database.session.commit()

        flash(
            "Sua senha foi redefinida com sucesso. Faça login com a nova senha.", "success")

        if area == "militar":
            return redirect(url_for("login_atualizacao"))
        return redirect(url_for("login"))

    return render_template("auth/resetar_senha_publica.html", form=form, area=area)


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        militar = get_militar_por_user(current_user)
        session['militar_id'] = militar.id
        flash('Você já está logado.', 'alert-info')
        return redirect(url_for('home'))

    form_login = FormLogin()
    if form_login.validate_on_submit() and 'botao_submit_login' in request.form:
        cpf = User.query.filter_by(cpf=form_login.cpf.data).first()

        if cpf and bcrypt.check_password_hash(cpf.senha, form_login.senha.data):
            login_user(cpf, remember=form_login.lembrar_dados.data)
            flash('Login feito com sucesso!', 'alert-success')

            fuso_horario = pytz.timezone('America/Manaus')
            cpf.data_ultimo_acesso = datetime.now(fuso_horario)
            cpf.ip_address = get_user_ip()

            database.session.commit()

            # Agora a verificação de função refinada
            if cpf.funcao_user_id in [1, 2]:  # Diretor ou Chefe
                return redirect(url_for('home'))
            else:
                return redirect(url_for('home'))
        else:
            flash('Falha no Login, CPF ou senha incorretos.', 'alert-danger')

    return render_template('login.html', form_login=form_login)


@app.route('/sair')
@login_required
def sair():
    logout_user()
    flash('Faça o Login para continuar', 'alert-success')
    return redirect(url_for('login'))
