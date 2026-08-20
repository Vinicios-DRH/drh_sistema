from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from src import database
from src.authz import require_perm
from src.services.historico_militar_service import (
    buscar_militares_por_texto,
    montar_historico_militar,
)
from src.services.militar_situacao_service import (
    processar_inicio_situacoes_extras,
    processar_fim_de_situacao_militar,
)

bp_historico = Blueprint("historico_militar", __name__, url_prefix="/historico")


def _to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@bp_historico.get("/")
@require_perm("HISTORICO_MILITAR_READ")
def pagina_historico():
    """Linha do tempo funcional completa de um militar: OBMs por onde
    passou, férias por ano, licenças, agregações, disposições, formação e o
    histórico de alterações de situação pela chefia.

    Sem `militar_id` na querystring, mostra só a busca (autocomplete via
    /historico/api/search). Com `militar_id`, já renderiza tudo.
    """
    militar_id = _to_int(request.args.get("militar_id"))

    if militar_id:
        processar_inicio_situacoes_extras(militar_id=militar_id)
        processar_fim_de_situacao_militar(militar_id)
        database.session.commit()

    historico = montar_historico_militar(militar_id) if militar_id else None

    return render_template(
        "historico/historico_militar.html",
        militar_id=militar_id,
        historico=historico,
    )


@bp_historico.get("/api/search")
@require_perm("HISTORICO_MILITAR_READ")
def api_search_militares():
    """Autocomplete de busca por nome/matrícula/CPF.
    /historico/api/search?q=joao
    """
    q = request.args.get("q") or ""
    militares = buscar_militares_por_texto(q)

    results = []
    for m in militares:
        label = f"{m.posto_grad.sigla if m.posto_grad else ''} {m.nome_guerra or m.nome_completo} — ID {m.id}"
        if m.matricula:
            label += f" (Mat: {m.matricula})"
        results.append({"id": m.id, "text": label.strip()})

    return jsonify({"results": results})
