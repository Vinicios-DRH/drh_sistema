"""Home e autoatendimento do público externo (civil ou militar de outra
força) em Cursos CBMAM: dados do cadastro, cursos abertos ao público
externo, inscrição com PDF e acompanhamento do parecer da BM-3.

Espelha o autoatendimento militar em src.routes.cursos_cbmam (meus_cursos e
afins), mas ancorado em PessoaExterna — ver
src.services.cursos_cbmam_externo_service.
"""
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from src import app, bcrypt, database
from src.authz import eh_publico_externo
from src.forms import FormPerfilExterno
from src.models import Forca, PessoaExterna
from src.routes.helpers import _somente_numeros, formatar_telefone
from src.services.cursos_cbmam_service import obter_curso_andamento
from src.services.cursos_cbmam_externo_service import (
    criar_solicitacao_inscricao_externo,
    listar_cursos_disponiveis_para_externo,
    listar_minhas_solicitacoes_externo,
    obter_solicitacao_externo,
)


def _resolver_pessoa_externa_atual():
    return PessoaExterna.query.filter_by(user_id=current_user.id).first()


@app.route("/home-cursos-externo")
@login_required
def home_cursos_externo():
    if not eh_publico_externo():
        abort(403)

    pessoa = _resolver_pessoa_externa_atual()
    if not pessoa:
        flash("Não foi possível localizar seus dados de cadastro.", "alert-warning")
        return redirect(url_for("login_externo"))

    return render_template(
        "cursos_externo/home_cursos_externo.html",
        pessoa=pessoa,
        cursos_disponiveis=listar_cursos_disponiveis_para_externo(pessoa),
        minhas_solicitacoes=listar_minhas_solicitacoes_externo(pessoa.id),
    )


@app.route("/home-cursos-externo/perfil", methods=["GET", "POST"])
@login_required
def cursos_externo_perfil():
    if not eh_publico_externo():
        abort(403)

    pessoa = _resolver_pessoa_externa_atual()
    if not pessoa:
        flash("Não foi possível localizar seus dados de cadastro.", "alert-warning")
        return redirect(url_for("login_externo"))

    form = FormPerfilExterno(obj=pessoa)
    form.forca_id.choices = [('', '-- Selecione --')] + [
        (str(f.id), f.nome) for f in Forca.query.order_by(Forca.id.asc()).all()
    ]
    if request.method == "GET":
        form.forca_id.data = str(pessoa.forca_id) if pessoa.forca_id else ''

    if form.validate_on_submit():
        telefone_norm = _somente_numeros(form.telefone.data)
        if len(telefone_norm) not in (10, 11):
            flash("Informe um telefone válido, com DDD.", "warning")
            return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)

        telefone_em_uso = PessoaExterna.query.filter(
            PessoaExterna.telefone_norm == telefone_norm,
            PessoaExterna.id != pessoa.id,
        ).first()
        if telefone_em_uso:
            flash("⚠️ Este telefone já está cadastrado em outra conta.", "warning")
            return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)

        # Civil ou militar de outra força é definido no cadastro e não é
        # editável nesta tela (afeta elegibilidade de curso e relatório da
        # BM-3) — usa sempre o valor já gravado, nunca algo vindo do POST.
        # Pra civil, força/posto/quadro ficam sempre None: o template nem
        # mostra esses campos pra ele, mas o formulário ainda os declara
        # (servem pro militar), então alguém poderia mandar esses nomes de
        # campo escondidos num POST direto — por isso a trava é aqui, não
        # só no HTML.
        forca_id = None
        posto_graduacao = None
        quadro = None
        if pessoa.tipo_pessoa == "MILITAR":
            if not form.forca_id.data:
                flash("Selecione a força.", "warning")
                return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)
            forca_id = int(form.forca_id.data)
            posto_graduacao = (form.posto_graduacao.data or "").strip() or None
            if not posto_graduacao:
                flash("Informe seu posto/graduação.", "warning")
                return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)
            quadro = (form.quadro.data or "").strip() or None

        # Troca de senha é tudo-ou-nada: só mexe se a pessoa preencheu
        # alguma coisa nesses campos, e exige a senha atual certa — uma
        # sessão comprometida (cookie roubado, por exemplo) não consegue
        # trocar a senha sem saber a senha de verdade.
        nova_senha_hash = None
        if form.senha_atual.data or form.nova_senha.data or form.confirmar_nova_senha.data:
            if not bcrypt.check_password_hash(current_user.senha, form.senha_atual.data or ""):
                flash("Senha atual incorreta.", "warning")
                return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)
            if not form.nova_senha.data:
                flash("Informe a nova senha.", "warning")
                return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)
            if form.nova_senha.data != form.confirmar_nova_senha.data:
                flash("A confirmação da nova senha não confere.", "warning")
                return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)
            nova_senha_hash = bcrypt.generate_password_hash(form.nova_senha.data).decode('utf-8')

        try:
            nome_completo = form.nome_completo.data.strip()
            email = form.email.data.strip()

            pessoa.nome_completo = nome_completo
            pessoa.telefone = formatar_telefone(telefone_norm)
            pessoa.telefone_norm = telefone_norm
            pessoa.email = email
            pessoa.instituicao_origem = form.instituicao_origem.data.strip()
            pessoa.forca_id = forca_id
            pessoa.posto_graduacao = posto_graduacao
            pessoa.quadro = quadro

            # User.nome/email acompanham PessoaExterna (mesmo padrão do
            # cadastro) — CPF, função e OBM do User não são tocados aqui.
            current_user.nome = nome_completo
            current_user.email = email
            if nova_senha_hash:
                current_user.senha = nova_senha_hash

            database.session.commit()
            flash("✅ Dados atualizados com sucesso!", "success")
            return redirect(url_for("cursos_externo_perfil"))
        except IntegrityError:
            database.session.rollback()
            flash("⚠️ Este telefone já está cadastrado em outra conta.", "warning")
        except Exception as e:
            database.session.rollback()
            current_app.logger.exception("Erro ao atualizar perfil de público externo")
            flash(f"Erro ao atualizar dados: {str(e)}", "danger")

    return render_template("cursos_externo/perfil_externo.html", form=form, pessoa=pessoa)


@app.post("/home-cursos-externo/<int:andamento_id>/inscrever")
@login_required
def cursos_externo_inscrever(andamento_id):
    if not eh_publico_externo():
        abort(403)

    pessoa = _resolver_pessoa_externa_atual()
    if not pessoa:
        flash("Não foi possível localizar seus dados de cadastro.", "alert-warning")
        return redirect(url_for("login_externo"))

    andamento = obter_curso_andamento(andamento_id)
    if not andamento:
        abort(404)

    try:
        criar_solicitacao_inscricao_externo(andamento, pessoa, request.files.get("arquivo_inscricao"))
        database.session.commit()
        flash("Inscrição enviada! Acompanhe o parecer aqui mesmo.", "alert-success")
    except ValueError as e:
        database.session.rollback()
        flash(str(e), "alert-warning")
    except Exception as e:
        database.session.rollback()
        current_app.logger.exception("Erro ao enviar inscrição externa de curso CBMAM")
        flash(f"Erro ao enviar inscrição: {str(e)}", "alert-danger")

    return redirect(url_for("home_cursos_externo"))


@app.route("/home-cursos-externo/solicitacoes/<int:solicitacao_id>/arquivo")
@login_required
def cursos_externo_arquivo(solicitacao_id):
    if not eh_publico_externo():
        abort(403)

    pessoa = _resolver_pessoa_externa_atual()
    solicitacao = obter_solicitacao_externo(solicitacao_id)
    if not solicitacao or not pessoa or solicitacao.pessoa_externa_id != pessoa.id:
        abort(404)

    return redirect(solicitacao.url_arquivo)
