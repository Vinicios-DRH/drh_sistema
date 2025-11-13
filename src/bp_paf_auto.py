# bp_paf_auto.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from src import database
from src.models import Militar, NovoPaf, PafFeriasPlano, PafCapacidade
from src.decorators.utils_paf_auto import montar_propostas, aplicar_propostas, _capacidade_por_mes

bp_paf_auto = Blueprint("paf_auto", __name__, url_prefix="/paf/auto")

@bp_paf_auto.route("/alocar", methods=["GET", "POST"])
@login_required
def alocar():
    ano = request.args.get("ano", type=int) or request.form.get("ano", type=int) or 2026

    if request.method == "POST":
        # refaz as propostas na hora de aplicar, para reduzir race
        propostas = montar_propostas(database.session, ano, current_user.id)
        aplicados = aplicar_propostas(database.session, ano, current_user.id, propostas)
        flash(f"Alocação aplicada para {aplicados} militar(es).", "success")
        return redirect(url_for("paf_auto.alocar", ano=ano))

    # GET — prévia
    propostas = montar_propostas(database.session, ano, current_user.id)
    caps = _capacidade_por_mes(database.session, ano)

    # contagens do topo (iguais às do teu painel)
    total_sem_envio = len(propostas)
    return render_template(
        "paf/auto_alocar_preview.html",
        ano=ano,
        propostas=propostas,
        caps=caps,
        total_sem_envio=total_sem_envio
    )
