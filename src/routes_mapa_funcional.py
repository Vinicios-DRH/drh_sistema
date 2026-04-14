from flask import render_template, request
from flask_login import login_required
from src.decorators.control import checar_ocupacao
from src import app
from src.services.mapa_funcional_service import montar_mapa_funcional


from src.services.mapa_funcional_service import (
    montar_mapa_funcional,
    gerar_resumo_mapa
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
    linhas = montar_mapa_funcional()
    resumo = gerar_resumo_mapa(linhas)

    return render_template(
        "mapa_funcional.html",
        linhas=linhas,
        resumo=resumo
    )