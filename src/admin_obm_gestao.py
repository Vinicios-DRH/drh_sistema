from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import and_

from src import database as db
from src.models import Obm, ObmGestao
from src.decorators.control import checar_ocupacao

bp_admin_obm_gestao = Blueprint(
    "admin_obm_gestao",
    __name__,
    url_prefix="/admin/obm-gestao"
)


@bp_admin_obm_gestao.get("/")
@login_required
@checar_ocupacao("SUPER USER")
def index():
    # Todas as OBMs para seleção
    obms = db.session.query(Obm).order_by(Obm.sigla.asc()).all()

    # Lista de OBMs que já são gestoras (têm pelo menos uma relação ativa)
    gestoras_ids = (
        db.session.query(ObmGestao.obm_gestora_id)
        .filter(ObmGestao.ativo.is_(True))
        .distinct()
        .all()
    )
    gestoras_ids = {gid for (gid,) in gestoras_ids if gid}

    return render_template(
        "admin/obm_gestao.html", hide_navbar=True,
        obms=obms,
        gestoras_ids=gestoras_ids,
    )


@bp_admin_obm_gestao.get("/api/gestora/<int:obm_gestora_id>")
@login_required
@checar_ocupacao("SUPER USER", "DIRETOR", "DIRETOR DRH", "CHEFE", "CHEFE DRH")
def api_relacao(obm_gestora_id: int):
    # OBMs geridas ativas
    rows = (
        db.session.query(ObmGestao, Obm)
        .join(Obm, Obm.id == ObmGestao.obm_gerida_id)
        .filter(
            ObmGestao.obm_gestora_id == obm_gestora_id,
            ObmGestao.ativo.is_(True)
        )
        .order_by(Obm.sigla.asc())
        .all()
    )

    geridas = [{"id": obm.id, "sigla": obm.sigla} for _, obm in rows]

    return jsonify({
        "ok": True,
        "obm_gestora_id": obm_gestora_id,
        "geridas": geridas
    })


@bp_admin_obm_gestao.post("/salvar")
@login_required
@checar_ocupacao("SUPER USER", "DIRETOR", "DIRETOR DRH", "CHEFE", "CHEFE DRH")
def salvar():
    """
    Recebe:
      - obm_gestora_id: int
      - obms_geridas: list[int]
    e faz sync:
      - ativa as selecionadas
      - desativa as que saíram
      - cria as novas
    """
    data = request.get_json(silent=True) or {}
    obm_gestora_id = int(data.get("obm_gestora_id") or 0)
    obms_geridas = data.get("obms_geridas") or []

    if not obm_gestora_id:
        return jsonify({"ok": False, "error": "Selecione uma OBM gestora."}), 400

    # normaliza lista
    try:
        obms_geridas_ids = {int(x) for x in obms_geridas if str(x).strip()}
    except Exception:
        return jsonify({"ok": False, "error": "Lista de OBMs geridas inválida."}), 400

    # não deixa auto-relacionar
    obms_geridas_ids.discard(obm_gestora_id)

    # valida se gestora existe
    gestora = db.session.query(Obm).get(obm_gestora_id)
    if not gestora:
        return jsonify({"ok": False, "error": "OBM gestora não encontrada."}), 404

    # valida se geridas existem
    if obms_geridas_ids:
        existentes = (
            db.session.query(Obm.id)
            .filter(Obm.id.in_(list(obms_geridas_ids)))
            .all()
        )
        existentes = {oid for (oid,) in existentes}
        faltando = obms_geridas_ids - existentes
        if faltando:
            return jsonify({"ok": False, "error": f"OBMs geridas inválidas: {sorted(list(faltando))}"}), 400

    # pega relações atuais (inclui ativas e inativas, pra reativar se existir)
    rels = (
        db.session.query(ObmGestao)
        .filter(ObmGestao.obm_gestora_id == obm_gestora_id)
        .all()
    )

    # mapa por obm_gerida_id
    rel_map = {r.obm_gerida_id: r for r in rels if r.obm_gerida_id}

    # 1) desativa as que NÃO foram selecionadas
    for gerida_id, rel in rel_map.items():
        if gerida_id not in obms_geridas_ids and rel.ativo:
            rel.ativo = False
            db.session.add(rel)

    # 2) ativa/cria as selecionadas
    for gerida_id in obms_geridas_ids:
        rel = rel_map.get(gerida_id)
        if rel:
            if not rel.ativo:
                rel.ativo = True
                db.session.add(rel)
        else:
            db.session.add(ObmGestao(
                obm_gestora_id=obm_gestora_id,
                obm_gerida_id=gerida_id,
                ativo=True
            ))

    db.session.commit()

    return jsonify({"ok": True})
