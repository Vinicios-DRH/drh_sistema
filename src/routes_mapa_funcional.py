from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from src import app, database
from src.models import MilitaresAgregados, MilitaresADisposicao
from src.decorators.control import checar_ocupacao

from src.services.mapa_funcional_service import (
    montar_mapa_funcional,
    gerar_resumo_mapa,
)


@app.route("/mapa-funcional")
@login_required
@checar_ocupacao(
    'DIRETOR',
    'CHEFE',
    'MAPA DA FORÇA',
    'DRH',
    'SUPER USER',
    'DIRETOR DRH'
)
def mapa_funcional():
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")

    filtros = {
        "q": request.args.get("q", ""),
        "destino": request.args.get("destino", ""),
        "status_macro": request.args.get("status_macro", ""),
        "modalidade": request.args.get("modalidade", ""),
        "situacao_principal": request.args.get("situacao_principal", ""),
        "apenas_intersecao": request.args.get("apenas_intersecao", ""),
        "apenas_defesa_civil": request.args.get("apenas_defesa_civil", ""),
        "somente_ferias": request.args.get("somente_ferias", ""),
        "somente_vencidos": request.args.get("somente_vencidos", ""),
    }

    linhas = montar_mapa_funcional(
        data_inicio=data_inicio,
        data_fim=data_fim,
        filtros=filtros
    )

    resumo = gerar_resumo_mapa(linhas)

    return render_template(
        "mapa_funcional.html",
        linhas=linhas,
        resumo=resumo,
        filtros=filtros,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )


STATUS_PERMITIDOS = {
    "Vigente",
    "A iniciar",
    "Venceu",
    "Término de Agregação",
    "Encerrado manualmente",
    "Renovado",
    "Suspenso",
    "Inativo",
}


@app.route("/mapa-funcional/alterar-status", methods=["POST"])
@login_required
@checar_ocupacao(
    'DIRETOR',
    'CHEFE',
    'MAPA DA FORÇA',
    'DRH',
    'SUPER USER',
    'DIRETOR DRH'
)
def alterar_status_mapa_funcional():
    tipo = request.form.get("tipo")
    registro_id = request.form.get("registro_id", type=int)
    novo_status = request.form.get("status")

    if novo_status not in STATUS_PERMITIDOS:
        flash("Status inválido.", "danger")
        return redirect(url_for("mapa_funcional"))

    if tipo == "agregado":
        registro = MilitaresAgregados.query.get_or_404(registro_id)
    elif tipo == "disposicao":
        registro = MilitaresADisposicao.query.get_or_404(registro_id)
    else:
        flash("Tipo de registro inválido.", "danger")
        return redirect(url_for("mapa_funcional"))

    registro.status = novo_status

    database.session.commit()

    flash("Status atualizado com sucesso.", "success")
    return redirect(request.referrer or url_for("mapa_funcional"))
