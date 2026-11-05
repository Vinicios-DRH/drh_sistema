
from flask_login import login_required
from flask import abort, request
from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, func, case
from sqlalchemy.orm import joinedload
from src.routes.helpers import somente_numeros
from src import app, database, bcrypt
from src.forms import (FormCriarUsuario)
from src.models import (Militar, Obm, Localidade, User, FuncaoUser, perfil_da_funcao)
from src.decorators.control import checar_ocupacao, _is_super_user
from src.authz import eh_publico_externo


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

        # O mesmo militar pode ter uma conta de gestão (chefe, DP...) e uma de
        # militar (atualização cadastral). Só atualiza se já existir conta do
        # mesmo tipo da função escolhida; senão cria a outra conta.
        perfil = perfil_da_funcao(form_criar_usuario.funcao_user_id.data)
        usuario_existente = next(
            (u for u in User.contas_por_cpf(form_criar_usuario.cpf.data)
             if u.tipo_perfil == perfil),
            None
        )

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
            flash(f"Este CPF já tinha conta {perfil}. Dados atualizados com sucesso!",
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
            tipo_perfil=perfil,
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
        flash(f"Conta {perfil} cadastrada com sucesso!", "alert-success")
        return redirect(url_for('home'))

    return render_template('criar_conta.html', form_criar_usuario=form_criar_usuario)


USUARIOS_POR_PAGINA = 25


def _escapar_like(texto):
    return texto.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


@app.route("/usuarios", methods=['GET'])
@login_required
def usuarios():
    if current_user.id != 1:
        abort(403)

    busca = (request.args.get('q') or '').strip()[:100]
    filtro_perfil = (request.args.get('perfil') or '').upper()
    filtro_status = (request.args.get('status') or '').lower()
    pagina = max(request.args.get('page', 1, type=int) or 1, 1)

    # Só as colunas usadas na listagem; outerjoin p/ não sumir com quem
    # está sem função atribuída.
    consulta = database.session.query(
        User.id,
        User.nome,
        User.cpf,
        User.cpf_norm,
        User.email,
        User.ativo,
        User.tipo_perfil,
        FuncaoUser.ocupacao.label('funcao_ocupacao'),
    ).outerjoin(FuncaoUser, User.funcao_user_id == FuncaoUser.id)

    if busca:
        # Cada palavra precisa aparecer em nome, e-mail, função ou CPF.
        # unaccent (já usado na listagem de militares): "avila" acha "Ávila".
        def sem_acento(coluna):
            return func.lower(func.unaccent(func.coalesce(coluna, '')))

        for palavra in busca.split():
            termo = func.lower(func.unaccent(f"%{_escapar_like(palavra)}%"))
            filtros = [
                sem_acento(User.nome).like(termo, escape='\\'),
                sem_acento(User.email).like(termo, escape='\\'),
                sem_acento(FuncaoUser.ocupacao).like(termo, escape='\\'),
            ]
            digitos = somente_numeros(palavra)
            if digitos:
                filtros.append(User.cpf_norm.like(f"%{digitos}%"))
                filtros.append(User.cpf.like(f"%{digitos}%"))
            consulta = consulta.filter(or_(*filtros))

    if filtro_perfil in ('ADMIN', 'MILITAR', 'EXTERNO'):
        if filtro_perfil == 'ADMIN':
            # Contas antigas podem estar sem tipo_perfil; a listagem sempre
            # as tratou como "Gestão".
            consulta = consulta.filter(or_(
                User.tipo_perfil.is_(None),
                User.tipo_perfil.notin_(('MILITAR', 'EXTERNO'))))
        else:
            consulta = consulta.filter(User.tipo_perfil == filtro_perfil)
    else:
        filtro_perfil = ''

    if filtro_status == 'ativos':
        consulta = consulta.filter(User.ativo.is_(True))
    elif filtro_status == 'bloqueados':
        consulta = consulta.filter(User.ativo.is_(False))
    else:
        filtro_status = ''

    total_filtrado = consulta.order_by(None).count()
    total_paginas = max((total_filtrado + USUARIOS_POR_PAGINA - 1) // USUARIOS_POR_PAGINA, 1)
    pagina = min(pagina, total_paginas)

    lista = (consulta
             .order_by(User.nome.asc(), User.id.asc())
             .offset((pagina - 1) * USUARIOS_POR_PAGINA)
             .limit(USUARIOS_POR_PAGINA)
             .all())

    contexto = dict(
        usuarios=lista,
        busca=busca,
        filtro_perfil=filtro_perfil,
        filtro_status=filtro_status,
        pagina=pagina,
        total_paginas=total_paginas,
        total_filtrado=total_filtrado,
        por_pagina=USUARIOS_POR_PAGINA,
    )

    # Busca dinâmica (fetch) só precisa do bloco de resultados.
    if request.args.get('parcial') == '1':
        return render_template('partials/_usuarios_resultados.html', **contexto)

    total, ativos = database.session.query(
        func.count(User.id),
        func.coalesce(func.sum(case((User.ativo.is_(True), 1), else_=0)), 0),
    ).one()
    total, ativos = int(total or 0), int(ativos or 0)
    contexto['resumo'] = {
        'total': total,
        'ativos': ativos,
        'bloqueados': total - ativos,
    }
    return render_template('usuarios.html', **contexto)


def _choices_formulario_usuario(form):
    """Preenche os selects do FormCriarUsuario buscando só id/rótulo."""
    vazio = [('', '-- Selecione uma opção --')]
    form.funcao_user_id.choices = [
        (f.id, f.ocupacao) for f in database.session.query(
            FuncaoUser.id, FuncaoUser.ocupacao).order_by(FuncaoUser.ocupacao)]
    obms = [(o.id, o.sigla) for o in database.session.query(
        Obm.id, Obm.sigla).order_by(Obm.sigla)]
    form.obm_id_1.choices = vazio + obms
    form.obm_id_2.choices = vazio + obms
    form.localidade_id.choices = vazio + [
        (l.id, l.sigla) for l in database.session.query(
            Localidade.id, Localidade.sigla).order_by(Localidade.sigla)]


@app.route('/usuario/<int:id_usuario>', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'SUPER USER')
def exibir_usuario(id_usuario):
    # Trava absoluta: Só o ID 1 entra
    if current_user.id != 1:
        abort(403)

    usuario = (User.query
               .options(joinedload(User.funcao_user),
                        joinedload(User.obm1),
                        joinedload(User.obm2),
                        joinedload(User.localidade))
               .filter(User.id == id_usuario)
               .first_or_404())
    usuario_info = usuario

    form = FormCriarUsuario(obj=usuario)
    form.current_user_id = id_usuario
    _choices_formulario_usuario(form)

    if form.validate_on_submit():
        # Trocar a função pode mudar o tipo de conta (gestão <-> militar); se
        # o militar já tem conta do outro tipo, a edição é nela.
        perfil = perfil_da_funcao(form.funcao_user_id.data)
        if perfil != usuario.tipo_perfil:
            outra = next(
                (u for u in User.contas_por_cpf(form.cpf.data)
                 if u.id != usuario.id and u.tipo_perfil == perfil),
                None
            )
            if outra:
                flash(
                    f'Este CPF já tem uma conta {perfil} (usuário #{outra.id}). '
                    'Edite aquela conta em vez de trocar a função desta.',
                    'alert-danger')
                return render_template('usuario_detalhes.html', usuario=usuario_info, form=form)
            usuario.tipo_perfil = perfil

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
            # /perfil só aceita o próprio usuário logado; o admin editando
            # outra conta era jogado pra home com "sem permissão".
            return redirect(url_for('exibir_usuario', id_usuario=id_usuario))
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

    # Público externo tem a própria home/perfil em Cursos CBMAM — essa tela
    # é do autoatendimento militar (mexe em OBM/função, que não fazem
    # sentido pra ele).
    if eh_publico_externo():
        return redirect(url_for('home_cursos_externo'))

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
        usuario.localidade_id = form.localidade_id.data

        # Função e OBM 1/2 aparecem desabilitados nesta tela de propósito —
        # não são autoatendimento, são atribuições administrativas. O campo
        # "disabled" é só visual (o navegador não impede alguém de remover
        # o atributo e submeter mesmo assim), então quem decide se esses
        # valores realmente mudam é o servidor, não o HTML: só SUPER
        # USUÁRIO pode alterar a própria função/OBM por aqui — qualquer
        # outra pessoa tem esses campos preservados, não importa o que
        # tenha vindo no POST.
        if _is_super_user():
            usuario.funcao_user_id = form.funcao_user_id.data
            usuario.obm_id_1 = form.obm_id_1.data
            usuario.obm_id_2 = form.obm_id_2.data

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
