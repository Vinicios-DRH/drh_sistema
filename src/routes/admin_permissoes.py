
from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_login import login_required
from sqlalchemy import or_, and_, func

from src import database as db
from src.models import User, UserPermissao, FuncaoUser, UserObmAcesso, Obm
from src.decorators.control import checar_ocupacao
from src.permissoes import PERMISSOES_CATALOGO
from src.utils.utils import registrar_log_download

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

    if codigo:
        query = query.join(
            UserPermissao,
            and_(
                UserPermissao.user_id == User.id,
                UserPermissao.codigo == codigo,
                UserPermissao.ativo == True,
            ),
        )

    # Puxa permissões de cada usuário (selectin via relationship já ajuda, mas aqui garantimos)
    query = query.order_by(User.nome.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    # Conta apenas as permissões ATIVAS por usuário, só da página atual
    ids = [u.id for u in users]
    perm_counts = dict(
        db.session.query(UserPermissao.user_id, func.count(UserPermissao.id))
        .filter(UserPermissao.user_id.in_(ids), UserPermissao.ativo == True)
        .group_by(UserPermissao.user_id)
        .all()
    )

    catalogo = sorted(_catalogo_map().values(), key=lambda p: p["nome"])

    # Se o admin selecionou um "codigo", o template pode filtrar visualmente
    return render_template(
        "admin/permissoes.html", hide_navbar=True,
        users=users,
        pagination=pagination,
        q=q,
        codigo=codigo,
        catalogo=catalogo,
        perm_counts=perm_counts,
        catalogo_map=_catalogo_map(),
    )


@bp_admin_permissoes.get("/user/<int:user_id>")
@login_required
@checar_ocupacao("SUPER USER")
def get_user_permissoes(user_id):
    user = db.session.query(User).get_or_404(user_id)

    catalogo = sorted(_catalogo_map().values(), key=lambda p: p["nome"])
    ativos = {
        p.codigo: bool(p.ativo)
        for p in db.session.query(UserPermissao).filter(UserPermissao.user_id == user_id).all()
    }

    # "Super" real (função 6) OU override via permissão SYS_SUPER ativa —
    # is_super() de src.authz opera sobre o current_user (o admin logado),
    # não serve pra checar o usuário-alvo aqui, então a regra é replicada
    # localmente em cima dos dados já carregados.
    is_super_flag = bool(user.funcao_user_id == 6) or bool(ativos.get("SYS_SUPER", False))

    return jsonify({
        "ok": True,
        "user": {
            "id": user.id,
            "nome": user.nome,
            "email": user.email,
            "cpf": user.cpf,
            "funcao": user.funcao_user.ocupacao if user.funcao_user else None,
        },
        "is_super": is_super_flag,
        "permissoes": [
            {"codigo": p["codigo"], "nome": p["nome"], "ativo": ativos.get(p["codigo"], False)}
            for p in catalogo
        ],
    })


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


@bp_admin_permissoes.post("/export")
@login_required
@checar_ocupacao("SUPER USER")
def export_permissoes():
    codigo = (request.args.get("codigo") or "").strip().upper()
    q = (request.args.get("q") or "").strip()
    incluir_inativos = request.form.get("incluir_inativos") == "on"

    catalogo_map = _catalogo_map()
    if not codigo or codigo not in catalogo_map:
        flash("Selecione uma permissão válida para exportar.", "alert-danger")
        return redirect(url_for("admin_permissoes.index", q=q, codigo=codigo))

    query = (
        db.session.query(User, UserPermissao, FuncaoUser)
        .join(UserPermissao, UserPermissao.user_id == User.id)
        .outerjoin(FuncaoUser, User.funcao_user_id == FuncaoUser.id)
        .filter(UserPermissao.codigo == codigo)
    )
    if not incluir_inativos:
        query = query.filter(UserPermissao.ativo == True)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                User.nome.ilike(like),
                User.email.ilike(like),
                User.cpf.ilike(like),
            )
        )
    query = query.order_by(User.nome.asc())

    nome_permissao = catalogo_map[codigo]["nome"]
    rows = []
    for user, perm, funcao in query.all():
        rows.append({
            "Nome": user.nome or "N/A",
            "CPF": user.cpf or "N/A",
            "Email": user.email or "N/A",
            "Função": funcao.ocupacao if funcao else "N/A",
            "Permissão": nome_permissao,
            "Código": codigo,
            "Status": "Ativa" if perm.ativo else "Inativa",
            "Concedido em": perm.created_at.strftime("%d/%m/%Y %H:%M") if perm.created_at else "N/A",
        })

    colunas = ["Nome", "CPF", "Email", "Função", "Permissão", "Código", "Status", "Concedido em"]
    df = pd.DataFrame(rows, columns=colunas)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Permissoes")
        workbook = writer.book
        worksheet = writer.sheets["Permissoes"]
        header_format = workbook.add_format({
            "bg_color": "#0b2e4f", "font_color": "#FFFFFF", "bold": True,
            "border": 1, "align": "center", "valign": "vcenter",
        })
        body_format = workbook.add_format({"text_wrap": True, "valign": "top", "border": 1})
        larguras = {"Nome": 32, "CPF": 16, "Email": 30, "Função": 20, "Permissão": 34,
                    "Código": 26, "Status": 12, "Concedido em": 18}
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, larguras.get(value, 20), body_format)
        worksheet.freeze_panes(1, 0)
        if len(df) > 0:
            worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
    output.seek(0)

    registrar_log_download(
        nome_relatorio=f"Permissões: {nome_permissao}",
        colunas_lista=colunas,
        filtros_dict={
            "codigo": codigo,
            "q": q or "Nenhum",
            "incluir_inativos": incluir_inativos,
        },
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"permissoes_{codigo}_{date.today().isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
