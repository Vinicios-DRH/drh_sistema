from io import BytesIO
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required, current_user
from openpyxl import Workbook
from sqlalchemy import exists, or_, and_, func
from src.controller.utils_acumulo import b2_presigned_get, b2_upload_fileobj, b2_check, b2_put_test, build_prefix
from src.models import AuditoriaDeclaracao, database as db, Militar, PostoGrad, Obm, DeclaracaoAcumulo, MilitarObmFuncao, VinculoExterno
from src.controller.control import checar_ocupacao
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime, date, time
from src.controller.formatar_datas import formatar_data_extenso, formatar_data_sem_zero
import re
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from src.controller.helpers_docx import render_docx_from_template


bp_acumulo = Blueprint("acumulo", __name__, url_prefix="/acumulo")

# b2_check()  # Verifica se as credenciais estão corretas no início
# b2_put_test()  # Teste opcional para verificar se o upload funciona

# --- Helpers baseados em User ---


def _is_super_user() -> bool:
    """
    Considera SUPER se current_user.funcao_user.ocupacao (ou .nome) contiver 'SUPER'
    """
    try:
        fu = getattr(current_user, "funcao_user", None)
        ocup = (getattr(fu, "ocupacao", None)
                or getattr(fu, "nome", "") or "").upper()
    except Exception:
        ocup = ""
    return "SUPER" in ocup  # ex.: "SUPER USER"


def _user_obm_ids() -> list[int]:
    """
    OBMs do usuário (User.obm_id_1 e User.obm_id_2). Remove None/duplicados.
    """
    ids = {getattr(current_user, "obm_id_1", None),
           getattr(current_user, "obm_id_2", None)}
    ids.discard(None)
    return list(ids)


def _militar_permitido(militar_id: int) -> bool:
    """Chefe/Diretor só pode mexer em militar cuja OBM ativa ∈ (obm_id_1, obm_id_2). Super vê tudo."""
    if _is_super_user():
        return True
    obm_ids = _user_obm_ids()
    if not obm_ids:
        return False
    MOF = MilitarObmFuncao
    ok = (
        db.session.query(Militar.id)
        .join(MOF, MOF.militar_id == Militar.id)
        .filter(
            Militar.id == militar_id,
            MOF.data_fim.is_(None),
            MOF.obm_id.in_(obm_ids),
        )
        .first()
    )
    return ok is not None


# parse helpers
def _parse_time(s: str | None) -> time | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%H:%M").time()
    except Exception:
        return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except Exception:
            pass
    return None


def _digits(s: str | None) -> str:
    return re.sub(r"\D+", "", s or "")


def _ocupacao_nome() -> str:
    try:
        return (getattr(getattr(current_user, "user_funcao", None), "ocupacao", "") or "").upper()
    except Exception:
        return ""


def _is_super_user() -> bool:
    return "SUPER" in _ocupacao_nome()


def _user_admin_obm_ids() -> set[int]:
    if _ocupacao_nome() not in {"CHEFE", "DIRETOR"}:
        return set()
    ids = {v for v in (getattr(current_user, "obm_id_1", None),
                       getattr(current_user, "obm_id_2", None)) if v}
    return ids


def _militar_obm_ativas_ids(militar_id: int) -> set[int]:
    rows = (db.session.query(MilitarObmFuncao.obm_id)
            .filter(MilitarObmFuncao.militar_id == militar_id,
                    MilitarObmFuncao.data_fim.is_(None))
            .distinct().all())
    return {r.obm_id for r in rows}


def _can_editar_declaracao(militar_id: int) -> bool:
    # SUPER pode tudo
    if _is_super_user():
        return True
    # chefe/diretor somente se administra a OBM ativa do militar
    admin = _user_admin_obm_ids()
    if not admin:
        return False
    return bool(admin & _militar_obm_ativas_ids(militar_id))


def _digits(s):
    import re
    return re.sub(r"\D+", "", s or "")

# --- motor de substituição no estilo que você já usa ---


def _replace_in_paragraph(p, mapping, bold_keys=None, italic_keys=None):
    text = p.text
    if not any(f"{{{k}}}" in text for k in mapping):
        return
    # limpa runs
    for run in list(p.runs):
        p._element.remove(run._element)
    parts = re.split(r'(\{.*?\})', text)
    for part in parts:
        if re.fullmatch(r'\{.*?\}', part or ""):
            key = part[1:-1]
            value = str(mapping.get(key, ""))

            run = p.add_run(value)
            run.font.name = 'Times New Roman'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
            run.font.size = Pt(10)
            if bold_keys and key in bold_keys:
                run.bold = True
            if italic_keys and key in italic_keys:
                run.italic = True
        else:
            run = p.add_run(part)
            run.font.name = 'Times New Roman'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
            run.font.size = Pt(10)

# ---------- /acumulo/lista ----------


@bp_acumulo.route("/lista", methods=["GET"])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER', 'DIRETOR DRH')
def lista():
    # filtros
    ano = request.args.get("ano", type=int)
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    ano_ref = ano or datetime.now().year

    MOF = MilitarObmFuncao

    # Base: Militar -> PostoGrad -> (função ativa) -> OBM
    qry = (
        db.session.query(Militar)
        .select_from(Militar)
        .outerjoin(PostoGrad, Militar.posto_grad_id == PostoGrad.id)
        .outerjoin(MOF, and_(MOF.militar_id == Militar.id, MOF.data_fim.is_(None)))
        .outerjoin(Obm, Obm.id == MOF.obm_id)
        .distinct(Militar.id)  # DISTINCT ON (militar.id) no Postgres
    )

    # 🔒 Escopo por OBM via User (só super vê tudo)
    if not _is_super_user():
        obm_ids = _user_obm_ids()
        if obm_ids:
            qry = qry.filter(Obm.id.in_(obm_ids))
        else:
            # sem OBM atribuída no usuário → nada a mostrar
            qry = qry.filter(db.text("1=0"))

    # Busca
    if q:
        ilike = f"%{q}%"
        qry = qry.filter(or_(
            Militar.nome_completo.ilike(ilike),
            Militar.matricula.ilike(ilike),
            PostoGrad.sigla.ilike(ilike),
            Obm.sigla.ilike(ilike),
        ))

    # Postgres exige que ORDER BY comece pelo campo do DISTINCT ON
    qry = qry.order_by(Militar.id.asc(), Militar.nome_completo.asc())

    # Paginação
    pagination = qry.paginate(page=page, per_page=per_page, error_out=False)
    militares = pagination.items

    # OBM "ativa" para exibir no template
    ids = [m.id for m in militares]
    obm_map = {}
    if ids:
        rows = (
            db.session.query(MOF.militar_id, Obm.sigla)
            .join(Obm, Obm.id == MOF.obm_id)
            .filter(MOF.militar_id.in_(ids), MOF.data_fim.is_(None))
            .all()
        )
        for mid, sigla in rows:
            obm_map.setdefault(mid, sigla)  # primeira OBM ativa encontrada
    for m in militares:
        m.obm_sigla = obm_map.get(m.id, "-")

    # "Última declaração" por militar
    ultima_por_militar = {}
    if ids:
        if ano:  # do ano filtrado
            decls = (
                db.session.query(DeclaracaoAcumulo)
                .filter(
                    DeclaracaoAcumulo.militar_id.in_(ids),
                    DeclaracaoAcumulo.ano_referencia == ano
                )
                .all()
            )
            ultima_por_militar = {d.militar_id: d for d in decls}
        else:    # mais recente
            sub = (
                db.session.query(
                    DeclaracaoAcumulo.militar_id,
                    func.max(DeclaracaoAcumulo.ano_referencia).label(
                        "max_ano"),
                )
                .filter(DeclaracaoAcumulo.militar_id.in_(ids))
                .group_by(DeclaracaoAcumulo.militar_id)
                .subquery()
            )
            decls = (
                db.session.query(DeclaracaoAcumulo)
                .join(
                    sub,
                    and_(
                        DeclaracaoAcumulo.militar_id == sub.c.militar_id,
                        DeclaracaoAcumulo.ano_referencia == sub.c.max_ano,
                    ),
                )
                .all()
            )
            ultima_por_militar = {d.militar_id: d for d in decls}
    for m in militares:
        m.ultima_declaracao = ultima_por_militar.get(m.id)

    # KPIs (mesmo escopo da lista)
    base_total = (
        db.session.query(Militar.id)
        .select_from(Militar)
        .outerjoin(PostoGrad, Militar.posto_grad_id == PostoGrad.id)
        .outerjoin(MOF, and_(MOF.militar_id == Militar.id, MOF.data_fim.is_(None)))
        .outerjoin(Obm, Obm.id == MOF.obm_id)
        .distinct(Militar.id)
    )
    if not _is_super_user():
        obm_ids = _user_obm_ids()
        if obm_ids:
            base_total = base_total.filter(Obm.id.in_(obm_ids))
        else:
            base_total = base_total.filter(db.text("1=0"))

    total_militares_visiveis = base_total.count()

    entregues = 0
    if total_militares_visiveis:
        base_decl = (
            db.session.query(DeclaracaoAcumulo.militar_id)
            .join(Militar, Militar.id == DeclaracaoAcumulo.militar_id)
            .join(MOF, and_(MOF.militar_id == Militar.id, MOF.data_fim.is_(None)), isouter=True)
            .join(Obm, Obm.id == MOF.obm_id, isouter=True)
            .distinct()
        )
        if not _is_super_user():
            obm_ids = _user_obm_ids()
            if obm_ids:
                base_decl = base_decl.filter(Obm.id.in_(obm_ids))
            else:
                base_decl = base_decl.filter(db.text("1=0"))

        entregues = (
            base_decl
            .filter(DeclaracaoAcumulo.ano_referencia == ano_ref)
            .count()
        )

    pendentes = max(total_militares_visiveis - entregues, 0)
    adesao = f"{(entregues / total_militares_visiveis * 100):.0f}%" if total_militares_visiveis else "0%"

    # Paginação HTML
    def render_pagination(p):
        if p.pages <= 1:
            return ""
        items = []
        for num in range(1, p.pages + 1):
            cls = "active" if num == p.page else ""
            href = f"?page={num}&per_page={per_page}&ano={ano or ''}&q={q}"
            items.append(
                f'<li class="page-item {cls}"><a class="page-link" href="{href}">{num}</a></li>')
        return '<nav><ul class="pagination pagination-sm justify-content-end mt-3">' + "".join(items) + "</ul></nav>"

    pagination_html = render_pagination(pagination)

    return render_template(
        "acumulo_lista.html",
        ano=ano,
        militares=militares,
        entregues=entregues,
        pendentes=pendentes,
        adesao=adesao,
        pagination=pagination_html,
        tem_permissao=True,
    )

# 2) Form para nova declaração (chefe seleciona um militar e entra aqui)

# ----------------- /acumulo/novo -----------------


@bp_acumulo.route("/novo/<int:militar_id>", methods=["GET", "POST"])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER', 'DIRETOR DRH')
def novo(militar_id):
    if not _militar_permitido(militar_id):
        flash("Você não tem permissão para lançar declaração para este militar (fora da sua(s) OBM(s)).", "alert-danger")
        return redirect(url_for("acumulo.lista"))

    ano = request.values.get("ano", type=int) or datetime.now().year

    MOF = MilitarObmFuncao
    row = (
        db.session.query(Militar, PostoGrad.sigla.label(
            "pg_sigla"), Obm.sigla.label("obm_sigla"))
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(MOF, and_(MOF.militar_id == Militar.id, MOF.data_fim.is_(None)))
        .outerjoin(Obm, Obm.id == MOF.obm_id)
        .filter(Militar.id == militar_id)
        .first()
    )
    if not row:
        abort(404)
    militar, pg_sigla, obm_sigla = row

    if request.method == "GET":
        return render_template(
            "acumulo_novo.html",
            militar_id=militar.id,
            militar=militar,
            posto_grad_sigla=pg_sigla or "-",
            obm_sigla=obm_sigla or "-",
            ano=ano,
        )

    # ----------------- POST -----------------
    tipo = (request.form.get("tipo") or "").strip().lower()
    if tipo not in {"positiva", "negativa"}:
        flash("Informe o tipo de declaração (positiva/negativa).", "alert-danger")
        return redirect(request.url)

    meio_entrega = (request.form.get("meio_entrega")
                    or "digital").strip().lower()
    if meio_entrega not in {"digital", "presencial"}:
        meio_entrega = "digital"

    observacoes = (request.form.get("observacoes") or "").strip()

    # arquivo obrigatório
    arquivo_fs = request.files.get("arquivo_declaracao")
    if not arquivo_fs or not (arquivo_fs.filename or "").strip():
        flash("Anexe o arquivo da declaração (PDF/JPG/PNG).", "alert-danger")
        return redirect(request.url)

    # vínculo único (apenas se positiva)
    vinculo_row = None
    if tipo == "positiva":
        emp_nome = (request.form.get("empregador_nome") or "").strip()
        emp_tipo = (request.form.get("empregador_tipo") or "").strip().lower()
        emp_doc = _digits(request.form.get("empregador_doc") or "")
        natureza = (request.form.get("natureza_vinculo") or "").strip().lower()
        cargo = (request.form.get("cargo_funcao") or "").strip()
        try:
            carga = int(
                (request.form.get("carga_horaria_semanal") or "0").strip() or "0")
        except Exception:
            carga = 0
        h_ini = _parse_time(request.form.get("horario_inicio"))
        h_fim = _parse_time(request.form.get("horario_fim"))
        d_ini = _parse_date(request.form.get("data_inicio"))

        if emp_tipo not in {"publico", "privado", "cooperativa", "autonomo"}:
            flash("Tipo de empregador inválido.", "alert-danger")
            return redirect(request.url)
        if natureza not in {"efetivo", "contratado", "prestacao_servicos", "autonomo"}:
            flash("Natureza do vínculo inválida.", "alert-danger")
            return redirect(request.url)
        if not (emp_nome and emp_doc and cargo and carga > 0 and h_ini and h_fim and d_ini):
            flash("Preencha todos os campos do vínculo externo.", "alert-danger")
            return redirect(request.url)

        vinculo_row = dict(
            empregador_nome=emp_nome,
            empregador_tipo=emp_tipo,
            empregador_doc=emp_doc,
            natureza_vinculo=natureza,
            cargo_funcao=cargo,
            carga_horaria_semanal=carga,
            horario_inicio=h_ini,
            horario_fim=h_fim,
            data_inicio=d_ini,
        )

    # upload Backblaze
    try:
        object_key = b2_upload_fileobj(
            arquivo_fs, key_prefix=f"acumulo/{ano}/{militar_id}")
    except Exception as e:
        db.session.rollback()
        flash(f"Falha no upload do arquivo: {e}", "alert-danger")
        return redirect(request.url)

    # UPSERT
    try:
        decl = (
            db.session.query(DeclaracaoAcumulo)
            .filter(
                DeclaracaoAcumulo.militar_id == militar_id,
                DeclaracaoAcumulo.ano_referencia == ano
            ).first()
        )

        if decl:
            de_status = decl.status
            decl.tipo = tipo
            decl.meio_entrega = meio_entrega
            decl.observacoes = observacoes or None
            decl.arquivo_declaracao = object_key
            decl.status = "pendente"
            decl.updated_at = datetime.utcnow()
        else:
            de_status = None
            decl = DeclaracaoAcumulo(
                militar_id=militar_id,
                ano_referencia=ano,
                tipo=tipo,
                meio_entrega=meio_entrega,
                arquivo_declaracao=object_key,
                observacoes=observacoes or None,
                status="pendente",
                created_at=datetime.utcnow(),
            )
            db.session.add(decl)
            db.session.flush()

        # zera vínculos antigos (uma vez só)
        for v in list(getattr(decl, "vinculos", [])):
            db.session.delete(v)

        # insere vínculo único se positiva
        if tipo == "positiva" and vinculo_row:
            db.session.add(VinculoExterno(
                declaracao_id=decl.id, **vinculo_row))

        # auditoria opcional se mudou
        if de_status and de_status != decl.status:
            db.session.add(AuditoriaDeclaracao(
                declaracao_id=decl.id,
                de_status=de_status,
                para_status=decl.status,
                motivo="Reenvio/atualização de declaração.",
                alterado_por_user_id=getattr(current_user, "id", None),
                data_alteracao=datetime.utcnow()
            ))

        db.session.commit()
        flash("Declaração salva com sucesso!", "alert-success")
        return redirect(url_for("acumulo.lista", ano=ano))

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao salvar a declaração: {e}", "alert-danger")
        return redirect(request.url)

# 3) (Opcional) Edição de uma declaração existente (quando implementarmos)


@bp_acumulo.route("/editar/<int:decl_id>", methods=["GET", "POST"])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER', 'DIRETOR DRH')
def editar(decl_id):
    # carrega a declaração com militar e vínculos
    decl = (db.session.query(DeclaracaoAcumulo)
            .options(
                joinedload(DeclaracaoAcumulo.militar).joinedload(
                    Militar.posto_grad),
                selectinload(DeclaracaoAcumulo.vinculos)
    ).get(decl_id))
    if not decl:
        abort(404)
    if not _can_editar_declaracao(decl.militar_id):
        flash("Somente o chefe/diretor da OBM do militar (ou SUPER USER) pode editar.", "alert-danger")
        return redirect(url_for("acumulo.detalhe", decl_id=decl.id))

    # SIGLA da OBM ativa (só pra exibir)
    MOF = MilitarObmFuncao
    obm_sigla = (db.session.query(Obm.sigla)
                 .join(MOF, Obm.id == MOF.obm_id)
                 .filter(MOF.militar_id == decl.militar_id, MOF.data_fim.is_(None))
                 .limit(1).scalar()) or "-"

    if request.method == "GET":
        # link temporário do arquivo atual (se houver)
        url_arquivo = None
        if decl.arquivo_declaracao:
            url_arquivo = b2_presigned_get(
                decl.arquivo_declaracao, expires_seconds=600)
        return render_template(
            "acumulo_editar.html",
            decl=decl,
            militar=decl.militar,
            posto_grad_sigla=getattr(decl.militar.posto_grad, "sigla", "-"),
            obm_sigla=obm_sigla,
            ano=decl.ano_referencia,
            url_arquivo=url_arquivo,
        )

    # -------- POST: salvar alterações --------
    tipo = (request.form.get("tipo") or "").strip().lower()
    if tipo not in {"positiva", "negativa"}:
        flash("Informe o tipo de declaração.", "alert-danger")
        return redirect(request.url)

    meio_entrega = (request.form.get("meio_entrega")
                    or "digital").strip().lower()
    if meio_entrega not in {"digital", "presencial"}:
        meio_entrega = "digital"

    observacoes = (request.form.get("observacoes") or "").strip()

    # arquivo: opcional (só troca se vier)
    arquivo_fs = request.files.get("arquivo_declaracao")
    if arquivo_fs and (arquivo_fs.filename or "").strip():
        try:
            key_prefix = build_prefix(decl.ano_referencia, decl.militar_id)
            new_key = b2_upload_fileobj(arquivo_fs, key_prefix=key_prefix)
            decl.arquivo_declaracao = new_key
        except Exception as e:
            db.session.rollback()
            current_user.logger.exception("B2 upload failed")
            flash(f"Falha no upload do arquivo: {e}", "alert-danger")
            return redirect(request.url)

    # atualiza cabeçalho
    decl.tipo = tipo
    decl.meio_entrega = meio_entrega
    decl.observacoes = (observacoes or None)
    # reabre para conferência sempre que editar
    decl.status = "pendente"

    # vínculos
    # limpa os antigos
    for v in list(decl.vinculos):
        db.session.delete(v)

    if tipo == "positiva":
        # reconstrói pelos arrays do form
        nomes = request.form.getlist("empregador_nome[]")
        tipos = request.form.getlist("empregador_tipo[]")
        docs = request.form.getlist("empregador_doc[]")
        natur = request.form.getlist("natureza_vinculo[]")
        cargos = request.form.getlist("cargo_funcao[]")
        cargas = request.form.getlist("carga_horaria_semanal[]")
        h_ini = request.form.getlist("horario_inicio[]")
        h_fim = request.form.getlist("horario_fim[]")
        d_ini = request.form.getlist("data_inicio[]")

        def _digits(s):
            import re
            return re.sub(r"\D+", "", s or "")
        n = max(len(nomes), len(tipos), len(docs), len(natur), len(
            cargos), len(cargas), len(h_ini), len(h_fim), len(d_ini))
        added = 0
        for i in range(n):
            nome = (nomes[i] if i < len(nomes) else "").strip()
            if not nome:
                continue
            v = VinculoExterno(
                declaracao_id=decl.id,
                empregador_nome=nome,
                empregador_tipo=(tipos[i] if i < len(
                    tipos) else "").strip().lower(),
                empregador_doc=_digits(docs[i] if i < len(docs) else ""),
                natureza_vinculo=(natur[i] if i < len(
                    natur) else "").strip().lower(),
                cargo_funcao=(cargos[i] if i < len(cargos) else "").strip(),
                carga_horaria_semanal=int(
                    (cargas[i] if i < len(cargas) else "0") or "0"),
                horario_inicio=_parse_time(
                    h_ini[i] if i < len(h_ini) else None),
                horario_fim=_parse_time(h_fim[i] if i < len(h_fim) else None),
                data_inicio=_parse_date(d_ini[i] if i < len(d_ini) else None),
            )
            db.session.add(v)
            added += 1
        if added == 0:
            db.session.rollback()
            flash("Inclua ao menos um vínculo para declaração positiva.",
                  "alert-danger")
            return redirect(request.url)

    try:
        db.session.commit()
        flash("Declaração atualizada com sucesso!", "alert-success")
        return redirect(url_for("acumulo.lista", ano=decl.ano_referencia))
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao salvar alterações: {e}", "alert-danger")
        return redirect(request.url)

# 4) DRH/Recebimento – visão geral (quando implementarmos)


@bp_acumulo.route("/recebimento", methods=["GET"])
@login_required
@checar_ocupacao('DRH', 'DIRETOR DRH', 'DRH CHEFE', 'CHEFE DRH', 'SUPER USER')
def recebimento():
    ano = request.args.get("ano", type=int) or datetime.now().year
    status = (request.args.get("status") or "todos").lower()
    q = (request.args.get("q") or "").strip()
    obm_id = request.args.get("obm_id", type=int)
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = max(request.args.get("per_page", 20, type=int), 1)

    D, M, PG = DeclaracaoAcumulo, Militar, PostoGrad

    # base sem JOIN; carrega relações via eager load
    qry = (
        db.session.query(D)
        .options(
            joinedload(D.militar).joinedload(M.posto_grad),
            selectinload(D.vinculos),
        )
        .filter(D.ano_referencia == ano)
    )

    # filtro por OBM via EXISTS
    if obm_id is not None and obm_id != 0:
        qry = qry.filter(
            exists().where(and_(
                MilitarObmFuncao.militar_id == D.militar_id,
                MilitarObmFuncao.obm_id == obm_id,
                MilitarObmFuncao.data_fim.is_(None),
            ))
        )

    # filtro por status
    if status in {"pendente", "validado", "inconforme"}:
        qry = qry.filter(D.status == status)

    # busca livre
    if q:
        ilike = f"%{q}%"
        qry = qry.filter(or_(
            D.militar.has(M.nome_completo.ilike(ilike)),
            D.militar.has(M.matricula.ilike(ilike)),
            D.militar.has(M.posto_grad.has(PG.sigla.ilike(ilike))),
        ))

    qry = qry.order_by(D.data_entrega.desc(), D.id.desc())

    # ---------- paginação manual (robusta) ----------
    total = qry.order_by(None).count()
    items = qry.limit(per_page).offset((page - 1) * per_page).all()
    declaracoes = items

    print(
        f"[DRH] list_count={total} page={page} per_page={per_page} items={len(declaracoes)}")

    # OBM ativa para exibir
    obm_map = {}
    if declaracoes:
        mids = [d.militar_id for d in declaracoes]
        rows = (
            db.session.query(MilitarObmFuncao.militar_id, Obm.sigla)
            .join(Obm, Obm.id == MilitarObmFuncao.obm_id)
            .filter(MilitarObmFuncao.militar_id.in_(mids),
                    MilitarObmFuncao.data_fim.is_(None))
            .all()
        )
        for mid, sigla in rows:
            obm_map.setdefault(mid, sigla)

    # URLs temporárias
    url_map = {}
    for d in declaracoes:
        if d.arquivo_declaracao:
            url_map[d.id] = b2_presigned_get(d.arquivo_declaracao, 600)

    # KPIs (respeita obm_id se aplicado)
    kpi_q = db.session.query(D.status, func.count(
        D.id)).filter(D.ano_referencia == ano)
    if obm_id is not None and obm_id != 0:
        kpi_q = kpi_q.filter(
            exists().where(and_(
                MilitarObmFuncao.militar_id == D.militar_id,
                MilitarObmFuncao.obm_id == obm_id,
                MilitarObmFuncao.data_fim.is_(None),
            ))
        )
    c_por_status = {s: n for s, n in kpi_q.group_by(D.status).all()}
    total_ano = sum(c_por_status.values())
    total_pendentes = c_por_status.get("pendente", 0)
    total_validados = c_por_status.get("validado", 0)
    total_inconformes = c_por_status.get("inconforme", 0)

    # dropdown de OBMs
    obms = db.session.query(Obm).order_by(Obm.sigla.asc()).all()

    # paginação html simples
    def render_pagination(total, page, per_page):
        pages = max((total + per_page - 1) // per_page, 1)
        if pages <= 1:
            return ""
        items = []
        for num in range(1, pages + 1):
            cls = "active" if num == page else ""
            params = f"page={num}&per_page={per_page}&ano={ano}&status={status}&q={q}&obm_id={(obm_id or '')}"
            items.append(
                f'<li class="page-item {cls}"><a class="page-link" href="?{params}">{num}</a></li>')
        return '<nav><ul class="pagination pagination-sm justify-content-end mt-3">' + "".join(items) + "</ul></nav>"

    pagination_html = render_pagination(total, page, per_page)
    pode_editar_map = {d.id: (_is_super_user() or _can_editar_declaracao(d.militar_id))
                       for d in declaracoes}

    return render_template(
        "acumulo_recebimento.html",
        ano=ano, status=status, q=q, obm_id=obm_id, obms=obms,
        declaracoes=declaracoes, obm_map=obm_map, url_map=url_map,
        total_ano=total_ano, total_pendentes=total_pendentes,
        total_validados=total_validados, total_inconformes=total_inconformes,
        pagination=pagination_html,
        pode_editar_map=pode_editar_map,
    )


@bp_acumulo.route("/recebimento/<int:decl_id>/status", methods=["POST"])
@login_required
@checar_ocupacao('DRH', 'DIRETOR DRH', 'SUPER USER')
def recebimento_mudar_status(decl_id):
    # validado|inconforme|pendente
    novo = (request.form.get("status") or "").lower()
    if novo not in {"validado", "inconforme", "pendente"}:
        flash("Status inválido.", "alert-danger")
        return redirect(url_for("acumulo.recebimento"))

    decl = db.session.get(DeclaracaoAcumulo, decl_id)
    if not decl:
        abort(404)

    de = decl.status
    decl.status = novo

    aud = AuditoriaDeclaracao(
        declaracao_id=decl.id,
        de_status=de, para_status=novo,
        motivo=(request.form.get("motivo") or None),
        alterado_por_user_id=current_user.id
    )
    db.session.add(aud)

    try:
        db.session.commit()
        flash("Status atualizado.", "alert-success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao atualizar status: {e}", "alert-danger")

    return redirect(url_for(
        "acumulo.recebimento",
        ano=request.args.get("ano"),
        status=request.args.get("status"),
        q=request.args.get("q"),
        obm_id=request.args.get("obm_id"),
        page=request.args.get("page"),
        per_page=request.args.get("per_page"),
    ))


@bp_acumulo.route("/arquivo/<int:decl_id>", methods=["GET"])
@login_required
@checar_ocupacao('DRH', 'DIRETOR DRH', 'SUPER USER')
def arquivo(decl_id):
    decl = db.session.get(DeclaracaoAcumulo, decl_id)
    if not decl or not decl.arquivo_declaracao:
        abort(404)
    return redirect(b2_presigned_get(decl.arquivo_declaracao, expires_seconds=600))


@bp_acumulo.route("/recebimento/export", methods=["GET"])
@login_required
@checar_ocupacao('DRH', 'DIRETOR DRH', 'DRH CHEFE', 'CHEFE DRH', 'SUPER USER')
def recebimento_export():
    from io import BytesIO
    from openpyxl import Workbook

    ano = request.args.get("ano", type=int) or datetime.now().year
    status = (request.args.get("status") or "todos").lower()
    q = (request.args.get("q") or "").strip()
    obm_id = request.args.get("obm_id", type=int)

    D, M, PG = DeclaracaoAcumulo, Militar, PostoGrad

    qry = (
        db.session.query(D, M, PG.sigla.label("pg_sigla"))
        .join(M, M.id == D.militar_id)
        .outerjoin(PG, PG.id == M.posto_grad_id)
        .filter(D.ano_referencia == ano)
    )
    if obm_id:
        qry = qry.filter(exists().where(and_(
            MilitarObmFuncao.militar_id == D.militar_id,
            MilitarObmFuncao.obm_id == obm_id,
            MilitarObmFuncao.data_fim.is_(None),
        )))
    if status in {"pendente", "validado", "inconforme"}:
        qry = qry.filter(D.status == status)
    if q:
        ilike = f"%{q}%"
        qry = qry.filter(or_(
            M.nome_completo.ilike(ilike),
            M.matricula.ilike(ilike),
            PG.sigla.ilike(ilike),
        ))

    rows = qry.order_by(D.data_entrega.desc(), D.id.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = f"Declarações {ano}"
    ws.append(["Ano", "Status", "Tipo", "Meio", "Data entrega",
              "Militar", "Matrícula", "Posto/Grad.", "Qtd vínculos", "Obs"])
    for d, m, pg_sigla in rows:
        ws.append([
            d.ano_referencia, d.status, d.tipo, d.meio_entrega,
            d.data_entrega.strftime(
                "%d/%m/%Y %H:%M") if d.data_entrega else "",
            m.nome_completo, m.matricula, pg_sigla or "",
            len(d.vinculos), d.observacoes or ""
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"declaracoes_{ano}_{status if status!='todos' else 'todos'}{f'_obm{obm_id}' if obm_id else ''}.xlsx"
    return send_file(bio, as_attachment=True, download_name=fname,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp_acumulo.route("/detalhe/<int:decl_id>", methods=["GET"])
@login_required
@checar_ocupacao('DRH', 'DIRETOR DRH', 'DRH CHEFE', 'CHEFE DRH', 'SUPER USER', 'DIRETOR', 'CHEFE')
def detalhe(decl_id):
    D = DeclaracaoAcumulo
    decl = (db.session.query(D)
            .options(
                joinedload(D.militar).joinedload(Militar.posto_grad),
                selectinload(D.vinculos),
    ).get(decl_id))
    if not decl:
        abort(404)

    # OBMs ativas (pode haver mais de uma)
    siglas = (db.session.query(Obm.sigla)
              .join(MilitarObmFuncao, Obm.id == MilitarObmFuncao.obm_id)
              .filter(MilitarObmFuncao.militar_id == decl.militar_id,
                      MilitarObmFuncao.data_fim.is_(None))
              .all())
    obm_siglas = ", ".join(s for (s,) in siglas) or "-"

    url_arquivo = b2_presigned_get(
        decl.arquivo_declaracao, 600) if decl.arquivo_declaracao else None
    pode_editar = _can_editar_declaracao(decl.militar_id)

    return render_template(
        "acumulo_detalhe.html",
        decl=decl,
        militar=decl.militar,
        posto_grad_sigla=getattr(decl.militar.posto_grad, "sigla", "-"),
        obm_siglas=obm_siglas,
        ano=decl.ano_referencia,
        url_arquivo=url_arquivo,
        pode_editar=pode_editar,
    )


@bp_acumulo.route("/modelo_docx/<int:militar_id>", methods=["POST"])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER', 'DIRETOR DRH')
def modelo_docx(militar_id):
    if not (_is_super_user() or _militar_permitido(militar_id)):
        flash("Sem permissão para este militar.", "alert-danger")
        return redirect(url_for("acumulo.lista"))

    # Cabeçalho do militar
    MOF = MilitarObmFuncao
    row = (
        db.session.query(Militar, PostoGrad.sigla.label(
            "pg_sigla"), Obm.sigla.label("obm_sigla"))
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(MOF, and_(MOF.militar_id == Militar.id, MOF.data_fim.is_(None)))
        .outerjoin(Obm, Obm.id == MOF.obm_id)
        .filter(Militar.id == militar_id)
        .first()
    )
    if not row:
        abort(404)
    militar, pg_sigla, obm_sigla = row

    ano = request.form.get("ano") or datetime.now().year
    tipo = (request.form.get("tipo") or "").lower()

    # Campos do vínculo (1 vínculo)
    emp_nome = (request.form.get("empregador_nome") or "").strip()
    emp_doc = _digits(request.form.get("empregador_doc") or "")
    natureza = (request.form.get("natureza_vinculo")
                or "").strip().replace("_", " ")
    cargo = (request.form.get("cargo_funcao") or "").strip()
    carga = (request.form.get("carga_horaria_semanal") or "").strip()
    hi = (request.form.get("horario_inicio") or "").strip()
    hf = (request.form.get("horario_fim") or "").strip()
    dinicio_raw = request.form.get("data_inicio") or ""
    dinicio = formatar_data_sem_zero(dinicio_raw) if dinicio_raw else ""
    horario = f"{hi} – {hf}" if (hi and hf) else ""

    # Mapeamento exatamente com os placeholders do DOCX
    mapping = {
        "posto_grad": pg_sigla or "-",
        "nome":       militar.nome_completo,
        "obm":        obm_sigla or "-",
        "ano":        str(ano),
        "x_sim": "X" if tipo == "positiva" else "",
        "x_nao": "X" if tipo == "negativa" else "",
        "empregador_nome":       emp_nome if tipo == "positiva" else "",
        "empregador_doc":        emp_doc if tipo == "positiva" else "",
        "natureza_vinculo":      natureza if tipo == "positiva" else "",
        "cargo_funcao":          cargo if tipo == "positiva" else "",
        "carga_horaria_semanal": carga if tipo == "positiva" else "",
        "horario":               (f"{hi} – {hf}" if (hi and hf) else "") if tipo == "positiva" else "",
        "data_inicio":           dinicio if tipo == "positiva" else "",
        "data_atual":            datetime.today().strftime("%d/%m/%Y"),
    }

    template_path = "src/template/declaracao_vinculo.docx"
    buf = render_docx_from_template(template_path, mapping)

    filename = f"Declaracao_{(militar.nome_guerra or militar.nome_completo).replace(' ', '_')}_{ano}.docx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
