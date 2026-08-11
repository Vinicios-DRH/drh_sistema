
from flask_login import login_required
from flask import abort, request
from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from src.routes.helpers import somente_numeros
from src import app, database, bcrypt
from src.forms import (FormCriarUsuario)
from src.models import (Militar, Obm, Localidade, User, FuncaoUser)
from src.decorators.control import checar_ocupacao


@app.route("/criar-conta", methods=['GET', 'POST'])
@login_required
def criar_conta():
    if current_user.id != 1:
        abort(403)

    form_criar_usuario = FormCriarUsuario()

    choices = [(funcao_user.id, funcao_user.ocupacao)
               for funcao_user in FuncaoUser.query.all()]
    choices.insert(0, ('', '-- Selecione uma opção --'))

    form_criar_usuario.obm_id_1.choices = [('', '-- Selecione uma opção --')] + [
        (obm.id, obm.sigla) for obm in Obm.query.all()
    ]
    form_criar_usuario.obm_id_2.choices = [('', '-- Selecione uma opção --')] + [
        (obm.id, obm.sigla) for obm in Obm.query.all()
    ]
    form_criar_usuario.localidade_id.choices = [('', '-- Selecione uma opção --')] + [
        (localidade.id, localidade.sigla) for localidade in Localidade.query.all()
    ]
    form_criar_usuario.funcao_user_id.choices = choices

    if form_criar_usuario.validate_on_submit():
        cpf_limpo = somente_numeros(form_criar_usuario.cpf.data)

        militar = Militar.query.filter(
            or_(
                Militar.cpf == cpf_limpo,
                Militar.cpf == form_criar_usuario.cpf.data
            )
        ).first()

        usuario_existente = User.query.filter(
            or_(
                User.cpf == cpf_limpo,
                User.cpf == form_criar_usuario.cpf.data,
                User.cpf_norm == cpf_limpo
            )
        ).first()

        if usuario_existente:
            # Atualiza o usuário já existente
            usuario_existente.nome = form_criar_usuario.nome.data
            usuario_existente.email = form_criar_usuario.email.data
            usuario_existente.cpf = form_criar_usuario.cpf.data
            usuario_existente.cpf_norm = cpf_limpo
            usuario_existente.funcao_user_id = form_criar_usuario.funcao_user_id.data
            usuario_existente.obm_id_1 = form_criar_usuario.obm_id_1.data or None
            usuario_existente.obm_id_2 = form_criar_usuario.obm_id_2.data or None
            usuario_existente.localidade_id = form_criar_usuario.localidade_id.data or None

            if militar:
                usuario_existente.militar_id = militar.id
                militar.usuario_id = usuario_existente.id

            # só atualiza senha se tiver sido preenchida
            if form_criar_usuario.senha.data:
                senha_cript = bcrypt.generate_password_hash(
                    form_criar_usuario.senha.data
                ).decode('utf-8')
                usuario_existente.senha = senha_cript

            database.session.commit()
            flash("Usuário já existia. Dados atualizados com sucesso!",
                  "alert-warning")
            return redirect(url_for('home'))

        # cria novo usuário se não existir
        senha_cript = bcrypt.generate_password_hash(
            form_criar_usuario.senha.data
        ).decode('utf-8')

        novo_usuario = User(
            nome=form_criar_usuario.nome.data,
            email=form_criar_usuario.email.data,
            cpf=cpf_limpo,
            cpf_norm=cpf_limpo,
            funcao_user_id=form_criar_usuario.funcao_user_id.data,
            obm_id_1=form_criar_usuario.obm_id_1.data or None,
            obm_id_2=form_criar_usuario.obm_id_2.data or None,
            localidade_id=form_criar_usuario.localidade_id.data or None,
            senha=senha_cript,
            militar_id=militar.id if militar else None
        )

        database.session.add(novo_usuario)
        database.session.flush()

        if militar:
            militar.usuario_id = novo_usuario.id

        database.session.commit()
        flash("Usuário cadastrado com sucesso!", "alert-success")
        return redirect(url_for('home'))

    return render_template('criar_conta.html', form_criar_usuario=form_criar_usuario)


@app.route("/usuarios", methods=['GET'])
@login_required
def usuarios():
    if current_user.id != 1:
        abort(403)

    usuarios_banco = User.query.join(FuncaoUser).add_columns(
        User.id,
        User.nome,
        User.cpf,
        User.ativo,
        FuncaoUser.ocupacao.label('funcao_ocupacao')
    ).order_by(User.nome.asc()).all()

    return render_template('usuarios.html', usuarios=usuarios_banco)


@app.route('/usuario/<int:id_usuario>', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'SUPER USER')
def exibir_usuario(id_usuario):
    # Trava absoluta: Só o ID 1 entra
    if current_user.id != 1:
        abort(403)
    # Carregar o usuário diretamente
    usuario = User.query.get_or_404(id_usuario)

    # Carregar informações extras sobre a função com join para exibição na tabela
    usuario_info = User.query \
        .join(FuncaoUser, User.funcao_user_id == FuncaoUser.id) \
        .add_columns(User.nome, User.cpf, User.id, User.email,
                     FuncaoUser.ocupacao.label('funcao_ocupacao')) \
        .filter(User.id == id_usuario) \
        .first_or_404()

    form = FormCriarUsuario(obj=usuario)
    form.current_user_id = id_usuario
    form.funcao_user_id.choices = [
        (funcao.id, funcao.ocupacao) for funcao in FuncaoUser.query.all()]
    form.obm_id_1.choices = [('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
                                                                   Obm.query.all()]
    form.obm_id_2.choices = [('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
                                                                   Obm.query.all()]
    form.localidade_id.choices = [
        ('', '-- Selecione uma opção --')
    ] + [(localidade.id, localidade.sigla) for localidade in
         Localidade.query.all()]

    if form.validate_on_submit():
        usuario.nome = form.nome.data
        usuario.email = form.email.data
        usuario.cpf = form.cpf.data
        usuario.funcao_user_id = form.funcao_user_id.data
        usuario.obm_id_1 = form.obm_id_1.data
        usuario.obm_id_2 = form.obm_id_2.data
        usuario.localidade_id = form.localidade_id.data

        if form.senha.data:
            usuario.senha = bcrypt.generate_password_hash(
                form.senha.data).decode('utf-8')

        try:
            database.session.commit()
            flash('Usuário atualizado com sucesso!', 'alert-success')
            return redirect(url_for('perfil', id_usuario=id_usuario))
        except Exception as e:
            database.session.rollback()
            flash(
                f'Erro ao atualizar o usuário. Tente novamente. {e}', 'alert-danger')

    return render_template('usuario_detalhes.html', usuario=usuario_info, form=form)


@app.route('/perfil/<int:id_usuario>', methods=['GET', 'POST'])
@login_required
def perfil(id_usuario):
    # Verificar se o usuário logado está acessando seu próprio perfil
    if current_user.id != id_usuario:
        flash('Você não tem permissão para acessar este perfil.', 'alert-danger')
        return redirect(url_for('home'))

    usuario = User.query.get_or_404(id_usuario)

    usuario_info = User.query \
        .join(FuncaoUser, User.funcao_user_id == FuncaoUser.id) \
        .add_columns(User.nome, User.cpf, User.id, User.email,
                     FuncaoUser.ocupacao.label('funcao_ocupacao')) \
        .filter(User.id == id_usuario) \
        .first_or_404()

    form = FormCriarUsuario(obj=usuario)
    form.current_user_id = id_usuario
    form.funcao_user_id.choices = [
        (funcao.id, funcao.ocupacao) for funcao in FuncaoUser.query.all()]
    form.obm_id_1.choices = [('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
                                                                   Obm.query.all()]
    form.obm_id_2.choices = [('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
                                                                   Obm.query.all()]
    form.localidade_id.choices = [
        ('', '-- Selecione uma opção --')
    ] + [(localidade.id, localidade.sigla) for localidade in
         Localidade.query.all()]

    if form.validate_on_submit():
        usuario.nome = form.nome.data
        usuario.email = form.email.data
        usuario.cpf = form.cpf.data
        usuario.funcao_user_id = form.funcao_user_id.data
        usuario.obm_id_1 = form.obm_id_1.data
        usuario.obm_id_2 = form.obm_id_2.data
        usuario.localidade_id = form.localidade_id.data

        if form.senha.data:
            usuario.senha = bcrypt.generate_password_hash(
                form.senha.data).decode('utf-8')

        try:
            database.session.commit()
            flash('Usuário atualizado com sucesso!', 'alert-success')
            return redirect(url_for('perfil', id_usuario=id_usuario))
        except Exception as e:
            database.session.rollback()
            flash(
                f'Erro ao atualizar o usuário. Tente novamente. {e}', 'alert-danger')

    return render_template('perfil.html', usuario=usuario_info, form=form)


@app.route('/usuario/toggle-status/<int:id_usuario>', methods=['POST'])
@login_required
def toggle_status_usuario(id_usuario):
    if current_user.id != 1:
        abort(403)
    usuario = User.query.get_or_404(id_usuario)

    # Impede que o Super User se bloqueie por acidente
    if usuario.id == current_user.id:
        flash("Você não pode desativar sua própria conta!", "alert-warning")
        return redirect(request.referrer)

    usuario.ativo = not usuario.ativo
    database.session.commit()

    status = "ativado" if usuario.ativo else "bloqueado"
    flash(f"Usuário {usuario.nome} foi {status} com sucesso!", "alert-success")
    return redirect(request.referrer)


@app.route('/usuario/<usuario_id>/excluir', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'SUPER USER')
def excluir_usuario(usuario_id):
    usuario = User.query.get(usuario_id)
    if not usuario:
        flash('Usuário não encontrado', 'alert-warning')
        return redirect(url_for('usuarios'))

    # desvincula militares que apontam para esse usuário
    militares = Militar.query.filter_by(usuario_id=usuario.id).all()
    for m in militares:
        m.usuario_id = None
        database.session.add(m)

    database.session.delete(usuario)
    database.session.commit()
    flash('Usuário excluído permanentemente', 'alert-danger')
    return redirect(url_for('usuarios'))
