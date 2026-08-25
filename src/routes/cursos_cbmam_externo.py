"""Home e autoatendimento do público externo (civil ou militar de outra
força) em Cursos CBMAM: dados do cadastro, cursos abertos ao público
externo, inscrição com PDF e acompanhamento do parecer da BM-3.

Espelha o autoatendimento militar em src.routes.cursos_cbmam (meus_cursos e
afins), mas ancorado em PessoaExterna — ver
src.services.cursos_cbmam_externo_service.
"""
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from src import app, database
from src.authz import eh_publico_externo
from src.models import PessoaExterna
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
