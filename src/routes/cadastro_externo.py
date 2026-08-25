"""Cadastro e login do público externo (civil ou militar de outra força —
Exército, Marinha, Aeronáutica, Polícia Militar) que se inscreve em Cursos
CBMAM. Caminho separado do fluxo militar interno (src.routes.auth /
src.routes.atualizacao_publica): aqui não existe matrícula nem registro
prévio pra confirmar — o próprio cadastro já cria a pessoa do zero.
"""
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user
from sqlalchemy.exc import IntegrityError

from src import app, bcrypt, database
from src.authz import FUNCAO_PUBLICO_EXTERNO_ID
from src.forms import FormCadastroExterno, FormLogin
from src.models import Forca, PessoaExterna, User
from src.routes.helpers import _somente_numeros, formatar_telefone
from src.formatar_cpf import formatar_cpf


@app.route('/cadastro-cursos', methods=['GET', 'POST'])
def cadastro_externo():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = FormCadastroExterno()
    form.forca_id.choices = [('', '-- Selecione --')] + [
        (str(f.id), f.nome) for f in Forca.query.order_by(Forca.id.asc()).all()
    ]

    if form.validate_on_submit():
        cpf_norm = _somente_numeros(form.cpf.data)
        if len(cpf_norm) != 11:
            flash("Informe um CPF válido.", "warning")
            return render_template("cursos_externo/cadastro_externo.html", form=form)

        cpf_formatado = formatar_cpf(cpf_norm)

        usuario_existente = User.query.filter(
            (User.cpf == cpf_formatado) | (User.cpf_norm == cpf_norm)
        ).first()
        if usuario_existente:
            flash("⚠️ Este CPF já possui uma conta. Tente fazer login.", "warning")
            return redirect(url_for('login_externo'))

        telefone_norm = _somente_numeros(form.telefone.data)
        if len(telefone_norm) not in (10, 11):
            flash("Informe um telefone válido, com DDD.", "warning")
            return render_template("cursos_externo/cadastro_externo.html", form=form)

        telefone_existente = PessoaExterna.query.filter_by(telefone_norm=telefone_norm).first()
        if telefone_existente:
            flash("⚠️ Este telefone já está cadastrado em outra conta.", "warning")
            return render_template("cursos_externo/cadastro_externo.html", form=form)

        tipo_pessoa = form.tipo_pessoa.data
        forca_id = None
        if tipo_pessoa == "MILITAR":
            if not form.forca_id.data:
                flash("Selecione a força.", "warning")
                return render_template("cursos_externo/cadastro_externo.html", form=form)
            forca_id = int(form.forca_id.data)
            if not (form.posto_graduacao.data or "").strip():
                flash("Informe seu posto/graduação.", "warning")
                return render_template("cursos_externo/cadastro_externo.html", form=form)

        try:
            senha_hash = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')

            novo_usuario = User(
                nome=form.nome_completo.data.strip(),
                email=form.email.data.strip(),
                cpf=cpf_formatado,
                cpf_norm=cpf_norm,
                senha=senha_hash,
                tipo_perfil="EXTERNO",
                funcao_user_id=FUNCAO_PUBLICO_EXTERNO_ID,
                militar_id=None,
            )
            database.session.add(novo_usuario)
            database.session.flush()

            database.session.add(PessoaExterna(
                user_id=novo_usuario.id,
                nome_completo=form.nome_completo.data.strip(),
                cpf=cpf_formatado,
                cpf_norm=cpf_norm,
                telefone=formatar_telefone(telefone_norm),
                telefone_norm=telefone_norm,
                email=form.email.data.strip(),
                instituicao_origem=form.instituicao_origem.data.strip(),
                tipo_pessoa=tipo_pessoa,
                forca_id=forca_id,
                posto_graduacao=(form.posto_graduacao.data or "").strip() or None,
                quadro=(form.quadro.data or "").strip() or None,
            ))

            database.session.commit()
            flash("✅ Conta criada com sucesso! Agora você pode fazer login.", "success")
            return redirect(url_for('login_externo'))
        except IntegrityError:
            database.session.rollback()
            flash("⚠️ Este CPF ou telefone já está cadastrado em outra conta.", "warning")
        except Exception as e:
            database.session.rollback()
            current_app.logger.exception("Erro ao criar conta de público externo")
            flash(f"Erro ao criar conta: {str(e)}", "danger")

    return render_template("cursos_externo/cadastro_externo.html", form=form)


@app.route('/login-externo', methods=['GET', 'POST'])
def login_externo():
    if current_user.is_authenticated:
        if current_user.funcao_user_id == FUNCAO_PUBLICO_EXTERNO_ID:
            return redirect(url_for('home_cursos_externo'))
        return redirect(url_for('home'))

    form_login = FormLogin()

    if form_login.validate_on_submit() and 'botao_submit_login' in request.form:
        cpf_formatado = form_login.cpf.data.strip()
        usuario = User.query.filter_by(cpf=cpf_formatado).first()

        if usuario and bcrypt.check_password_hash(usuario.senha, form_login.senha.data):
            if usuario.funcao_user_id == FUNCAO_PUBLICO_EXTERNO_ID:
                login_user(usuario, remember=form_login.lembrar_dados.data)
                flash('Login realizado com sucesso.', 'success')
                return redirect(url_for('home_cursos_externo'))
            else:
                flash('Esta conta não é de público externo. Use o login correspondente.', 'danger')
        else:
            flash('CPF ou senha incorretos.', 'danger')

    return render_template("cursos_externo/login_externo.html", form_login=form_login)
