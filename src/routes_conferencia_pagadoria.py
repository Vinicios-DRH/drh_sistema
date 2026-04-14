# src/routes_conferencia_pagadoria.py
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from src.authz import require_perm
from src import database
from src.models import Militar, MilitarObmFuncao, Obm, PostoGrad, ConferenciaPagadoria
from src.models import now_manaus_naive

bp_conferencia_pagadoria = Blueprint(
    "conferencia_pagadoria",
    __name__,
    url_prefix="/conferencia-pagadoria"
)


@bp_conferencia_pagadoria.route("/", methods=["GET"])
@login_required
@require_perm("NAV_CONFERENCIA_PAGADORIA_PAINEL")
def painel():
    sub_obm_1 = (
        database.session.query(
            MilitarObmFuncao.militar_id.label("militar_id"),
            Obm.sigla.label("obm_1")
        )
        .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .filter(MilitarObmFuncao.data_fim.is_(None))
        .subquery()
    )

    sub_obm_2 = (
        database.session.query(
            MilitarObmFuncao.militar_id.label("militar_id"),
            Obm.sigla.label("obm_2")
        )
        .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .filter(MilitarObmFuncao.data_fim.isnot(None))
        .subquery()
    )

    militares = (
        database.session.query(Militar, ConferenciaPagadoria,
                               sub_obm_1.c.obm_1, sub_obm_2.c.obm_2)
        .outerjoin(ConferenciaPagadoria, ConferenciaPagadoria.militar_id == Militar.id)
        .outerjoin(sub_obm_1, sub_obm_1.c.militar_id == Militar.id)
        .outerjoin(sub_obm_2, sub_obm_2.c.militar_id == Militar.id)
        .options(joinedload(Militar.posto_grad))
        .filter(Militar.inativo.is_(False))
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    return render_template(
        "conferencia_pagadoria/painel.html",
        militares=militares
    )


@bp_conferencia_pagadoria.route("/<int:militar_id>/check", methods=["POST"])
@login_required
@require_perm("CONFERENCIA_PAGADORIA_CHECK")
def marcar_check(militar_id):
    conf = ConferenciaPagadoria.query.filter_by(militar_id=militar_id).first()

    agora = now_manaus_naive()

    if not conf:
        conf = ConferenciaPagadoria(
            militar_id=militar_id,
            conferido=True,
            conferido_por_id=current_user.id,
            conferido_em=agora
        )
        database.session.add(conf)
    else:
        conf.conferido = True
        conf.conferido_por_id = current_user.id
        conf.conferido_em = agora

    database.session.commit()

    return jsonify({
        "ok": True,
        "militar_id": militar_id,
        "conferido": True,
        "conferido_por": current_user.nome,
        "conferido_em": agora.strftime("%d/%m/%Y %H:%M")
    })


@bp_conferencia_pagadoria.route("/<int:militar_id>/toggle", methods=["POST"])
@login_required
@require_perm("CONFERENCIA_PAGADORIA_TOGGLE")
def toggle_check(militar_id):
    conf = ConferenciaPagadoria.query.filter_by(militar_id=militar_id).first()

    if not conf:
        conf = ConferenciaPagadoria(militar_id=militar_id)
        database.session.add(conf)

    if conf.conferido:
        conf.conferido = False
        conf.conferido_por_id = None
        conf.conferido_em = None
    else:
        conf.conferido = True
        conf.conferido_por_id = current_user.id
        conf.conferido_em = now_manaus_naive()

    database.session.commit()

    return jsonify({
        "ok": True,
        "conferido": conf.conferido,
        "conferido_por": conf.conferido_por.nome if conf.conferido_por else "",
        "conferido_em": conf.conferido_em.strftime("%d/%m/%Y %H:%M") if conf.conferido_em else ""
    })
