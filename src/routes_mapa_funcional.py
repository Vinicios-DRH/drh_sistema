from flask import render_template, request
from flask_login import login_required
from src.decorators.control import checar_ocupacao
from src import app

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
