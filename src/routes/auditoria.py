
from flask_login import login_required
from flask import request
from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required
from src import app, database
from src.models import (LogAcesso)
from src.decorators.control import checar_ocupacao
from datetime import datetime, timedelta



@app.route("/auditoria/acessos", methods=["GET"])
@login_required
@checar_ocupacao('SUPER USER')  # Ou sua validação de permissão preferida
def auditoria_acessos():
    try:
        # Pega a página atual (padrão 1) e carrega 500 registros por vez para não travar
        page = request.args.get('page', 1, type=int)

        # Paginação direto no banco: rápido e indolor
        logs_paginados = LogAcesso.query.order_by(
            LogAcesso.data_acesso.desc()
        ).paginate(page=page, per_page=500, error_out=False)

        # Conta o total geral só pra exibir no painel
        total_logs = LogAcesso.query.count()

        return render_template(
            "auditoria_acessos.html",
            logs=logs_paginados,
            total_logs=total_logs
        )
    except Exception as e:
        app.logger.error(f"Erro ao carregar auditoria de acessos: {str(e)}")
        flash("Erro ao carregar os dados de acessos.", "error")
        return redirect(url_for('home'))


@app.route("/auditoria/acessos/limpar", methods=["POST"])
@login_required
@checar_ocupacao('SUPER USER')
def limpar_logs_acesso():
    try:
        dias = int(request.form.get('dias', 30))
        data_corte = datetime.now() - timedelta(days=dias)

        # Deleta direto no banco tudo que for mais antigo que a data de corte
        apagados = LogAcesso.query.filter(
            LogAcesso.data_acesso < data_corte).delete()
        database.session.commit()

        flash(
            f"Faxina concluída! {apagados} registros antigos (mais de {dias} dias) foram apagados.", "success")
    except Exception as e:
        database.session.rollback()
        app.logger.error(f"Erro ao limpar logs: {str(e)}")
        flash("Erro ao tentar limpar os logs.", "error")

    return redirect(url_for('auditoria_acessos'))


