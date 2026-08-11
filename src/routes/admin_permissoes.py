
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_

from src import database as db
from src.models import ObmGestao, User, UserPermissao, FuncaoUser, UserObmAcesso, Obm
from src.decorators.control import checar_ocupacao
from src.permissoes import PERMISSOES_CATALOGO

bp_admin_permissoes = Blueprint(
    "admin_permissoes",
    __name__,
    url_prefix="/admin/permissoes"
)


def _catalogo_map():
    return {p["codigo"]: p for p in PERMISSOES_CATALOGO}


@bp_admin_permissoes.get("/")
@login_required
@checar_ocupacao("SUPER USER")
def index():
    q = (request.args.get("q") or "").strip()
    codigo = (request.args.get("codigo") or "").strip().upper()
    page = int(request.args.get("page") or 1)
    per_page = 20

    query = db.session.query(User).outerjoin(
        FuncaoUser, User.funcao_user_id == FuncaoUser.id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                User.nome.ilike(like),
                User.email.ilike(like),
                User.cpf.ilike(like),
            )
        )

    # Puxa permissões de cada usuário (selectin via relationship já ajuda, mas aqui garantimos)
    query = query.order_by(User.nome.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    # Monta um dict {user_id: {codigo: ativo}}
    user_perm = {}
    if users:
        ids = [u.id for u in users]
        rows = (
            db.session.query(UserPermissao)
            .filter(UserPermissao.user_id.in_(ids))
            .all()
        )
        for r in rows:
            user_perm.setdefault(r.user_id, {})[r.codigo] = bool(r.ativo)

    catalogo = PERMISSOES_CATALOGO

    # Se o admin selecionou um "codigo", o template pode filtrar visualmente
    return render_template(
        "admin/permissoes.html", hide_navbar=True,
        users=users,
        pagination=pagination,
        q=q,
        codigo=codigo,
        catalogo=catalogo,
        user_perm=user_perm
    )


@bp_admin_permissoes.post("/toggle")
@login_required
@checar_ocupacao("SUPER USER")
def toggle():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    codigo = (data.get("codigo") or "").strip().upper()
    ativo = data.get("ativo")

    if not user_id or not codigo or ativo is None:
        return jsonify({"ok": False, "error": "Payload inválido."}), 400

    # valida código contra catálogo
    catalogo = _catalogo_map()
    if codigo not in catalogo:
        return jsonify({"ok": False, "error": "Permissão não reconhecida."}), 400

    # (opcional) evita que admin se trave removendo a própria permissão de admin
    # aqui não existe "ADMIN", mas se você criar no futuro, dá pra proteger.
    # if int(user_id) == int(current_user.id) and codigo == "ADMIN":
    #     return jsonify({"ok": False, "error": "Você não pode remover sua própria permissão ADMIN."}), 400

    perm = (
        db.session.query(UserPermissao)
        .filter(UserPermissao.user_id == int(user_id), UserPermissao.codigo == codigo)
        .first()
    )

    if perm is None:
        perm = UserPermissao(user_id=int(user_id),
                             codigo=codigo, ativo=bool(ativo))
        db.session.add(perm)
    else:
        perm.ativo = bool(ativo)

    db.session.commit()

    return jsonify({"ok": True, "user_id": int(user_id), "codigo": codigo, "ativo": bool(ativo)})


@bp_admin_permissoes.post("/grant")
@login_required
@checar_ocupacao("SUPER USER")
def grant_bulk():
    """
    Concede uma permissão para vários usuários de uma vez.
    payload: { codigo: "ANALISE_VINCULO", user_ids: [1,2,3] }
    """
    data = request.get_json(silent=True) or {}
    codigo = (data.get("codigo") or "").strip().upper()
    user_ids = data.get("user_ids") or []

    if not codigo or not isinstance(user_ids, list) or not user_ids:
        return jsonify({"ok": False, "error": "Payload inválido."}), 400

    catalogo = _catalogo_map()
    if codigo not in catalogo:
        return jsonify({"ok": False, "error": "Permissão não reconhecida."}), 400

    # upsert manual (sem depender de ON CONFLICT)
    for uid in user_ids:
        uid = int(uid)
        perm = (
            db.session.query(UserPermissao)
            .filter(UserPermissao.user_id == uid, UserPermissao.codigo == codigo)
            .first()
        )
        if perm is None:
            db.session.add(UserPermissao(
                user_id=uid, codigo=codigo, ativo=True))
        else:
            perm.ativo = True

    db.session.commit()
    return jsonify({"ok": True})


@bp_admin_permissoes.get("/obms/<int:user_id>")
@login_required
@checar_ocupacao("SUPER USER")
def get_obms_user(user_id):
    user = db.session.query(User).get_or_404(user_id)

    # todas as OBMs pra dropdown
    obms = db.session.query(Obm).order_by(Obm.sigla.asc()).all()

    # delegadas ativas
    delegadas = (
        db.session.query(UserObmAcesso)
        .filter(UserObmAcesso.user_id == user_id)
        .order_by(UserObmAcesso.id.desc())
        .all()
    )

    return jsonify({
        "ok": True,
        "user": {"id": user.id, "nome": user.nome},
        "obms": [{"id": o.id, "sigla": o.sigla} for o in obms],
        "delegadas": [{
            "id": d.id,
            "obm_id": d.obm_id,
            "obm_sigla": d.obm.sigla if d.obm else "",
            "tipo": d.tipo,
            "ativo": bool(d.ativo),
        } for d in delegadas]
    })


@bp_admin_permissoes.post("/obms/add")
@login_required
@checar_ocupacao("SUPER USER")
def add_obm_delegada():
    data = request.get_json(silent=True) or {}
    user_id = int(data.get("user_id") or 0)
    obm_id = int(data.get("obm_id") or 0)
    tipo = (data.get("tipo") or "DELEGADO").strip().upper()

    if not user_id or not obm_id:
        return jsonify({"ok": False, "error": "Dados inválidos."}), 400

    row = (
        db.session.query(UserObmAcesso)
        .filter(UserObmAcesso.user_id == user_id, UserObmAcesso.obm_id == obm_id)
        .first()
    )

    if row is None:
        row = UserObmAcesso(user_id=user_id, obm_id=obm_id,
                            tipo=tipo, ativo=True)
        db.session.add(row)
    else:
        row.tipo = tipo
        row.ativo = True

    db.session.commit()
    return jsonify({"ok": True})


@bp_admin_permissoes.post("/obms/toggle")
@login_required
@checar_ocupacao("SUPER USER")
def toggle_obm_delegada():
    data = request.get_json(silent=True) or {}
    delegacao_id = int(data.get("id") or 0)
    ativo = data.get("ativo")

    if not delegacao_id or ativo is None:
        return jsonify({"ok": False, "error": "Dados inválidos."}), 400

    row = db.session.query(UserObmAcesso).get(delegacao_id)
    if not row:
        return jsonify({"ok": False, "error": "Delegação não encontrada."}), 404

    row.ativo = bool(ativo)
    db.session.commit()
    return jsonify({"ok": True})
