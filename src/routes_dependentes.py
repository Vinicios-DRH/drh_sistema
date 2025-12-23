import os
from uuid import uuid4
from zoneinfo import ZoneInfo
from flask import (
    Blueprint, flash, redirect, render_template, request, send_file, jsonify, url_for
)
from itsdangerous import URLSafeTimedSerializer, BadSignature
from io import BytesIO
from flask_login import login_required, current_user
from sqlalchemy import func, desc, or_
from sqlalchemy.orm import aliased
from src.decorators.control import checar_ocupacao
from src.decorators.docx_fill import docx_fill_template
from src.decorators.utils_acumulo import b2_presigned_get, b2_upload_fileobj, build_prefix_dependente, _secret_key

from src import database
from src.models import Militar, MilitarObmFuncao, DepProcesso, DepArquivo, DepAcaoLog
from datetime import datetime


bp_dep = Blueprint("dep", __name__, template_folder="templates")

TEMPLATE_DOCX_PATH = os.path.join(
    os.path.dirname(__file__),
    "template",
    "FORMULARIO DE REQUERIMENTO Inclusão de Dependentes.docx"
)

MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def data_manaus_extenso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    dia = dt.day
    mes = MESES_PT[dt.month]
    ano = dt.year
    return f"Manaus, {dia:02d} de {mes} de {ano}"


def get_obm_sigla_from_militar(militar: Militar) -> str:
    """
    Regra:
    1) tenta vínculo ativo (data_fim == None)
    2) se não houver, pega o mais recente (data_criacao desc)
    Retorna sigla ou "".
    """
    vinculo = (
        MilitarObmFuncao.query
        .filter(MilitarObmFuncao.militar_id == militar.id)
        .order_by(
            # primeiro os ativos, depois por mais recente
            (MilitarObmFuncao.data_fim.is_(None)).desc(),
            desc(MilitarObmFuncao.data_criacao)
        )
        .first()
    )

    if not vinculo or not vinculo.obm:
        return ""
    return (vinculo.obm.sigla or "").strip()


def _only_digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def get_militar_from_current_user() -> Militar:
    """
    Link: User.cpf -> Militar.cpf (normalizando pontuação).
    """
    user_cpf = _only_digits(getattr(current_user, "cpf", "")
                            or getattr(current_user, "username", ""))
    if not user_cpf:
        raise ValueError("Usuário logado sem CPF cadastrado.")

    # Se no Militar o CPF está com pontuação, normaliza via replace no SQL (Postgres).
    # Se seu Militar.cpf já estiver só dígitos, pode simplificar para Militar.cpf == user_cpf.
    militar = (
        Militar.query
        .filter(
            func.replace(func.replace(Militar.cpf, ".", ""),
                         "-", "") == user_cpf
        )
        .first()
    )
    if not militar:
        raise ValueError("Militar não encontrado para o CPF do usuário.")
    return militar


def _dep_signer():
    return URLSafeTimedSerializer(_secret_key(), salt="req-dependente")


def make_dep_token(militar_id: int, ano: int, protocolo: str):
    return _dep_signer().dumps({"militar_id": militar_id, "ano": ano, "protocolo": protocolo})


def load_dep_token(token: str, max_age_hours=24):
    return _dep_signer().loads(token, max_age=max_age_hours * 3600)


@bp_dep.get("/dependentes/requerimento")
@login_required
def requerimento_form():
    try:
        militar = get_militar_from_current_user()
    except ValueError as e:
        return str(e), 400

    # pega o processo mais recente do militar
    # ultimo = (
    #     DepProcesso.query
    #     .filter(DepProcesso.militar_id == militar.id)
    #     .order_by(desc(DepProcesso.id))
    #     .first()
    # )

    # if ultimo:
    #     st = (ultimo.status or "ENVIADO").upper()

    #     # bloqueia se estiver "em andamento" ou "pendente de correção"
    #     if st in {"ENVIADO", "EM_ANALISE", "INDEFERIDO"}:
    #         flash(
    #             f"Você já possui um requerimento em andamento ({st}). "
    #             f"Acompanhe por lá para ver status ou reenviar documentos.",
    #             "warning"
    #         )
    #         return redirect(url_for("dep.militar_acompanhar", protocolo=ultimo.protocolo))

    # se não tem processo ou o último está DEFERIDO, deixa criar novo
    from datetime import datetime
    ano_default = datetime.now().year
    obm_sigla = get_obm_sigla_from_militar(militar)

    return render_template(
        "dependentes/requerimento_form.html",
        militar=militar,
        obm_sigla=obm_sigla,
        ano_default=ano_default
    )


@bp_dep.post("/dependentes/api/gerar-docx")
@login_required
def gerar_docx_api():
    try:
        militar = get_militar_from_current_user()
    except ValueError as e:
        return str(e), 400

    # ultimo = (DepProcesso.query
    #           .filter(DepProcesso.militar_id == militar.id)
    #           .order_by(desc(DepProcesso.id)).first())

    # if ultimo and (ultimo.status or "ENVIADO").upper() in {"ENVIADO", "EM_ANALISE", "INDEFERIDO"}:
    #     return jsonify({
    #         "ok": False,
    #         "message": "Você já possui um requerimento em andamento. Vá para o acompanhamento.",
    #         "redirect": url_for("dep.militar_acompanhar", protocolo=ultimo.protocolo)
    #     }), 409

    ano = int(request.form.get("ano") or 0) or __import__(
        "datetime").datetime.now().year

    protocolo = f"DEP-{uuid4().hex[:10].upper()}"
    token = make_dep_token(militar.id, ano, protocolo)

    x_ir = "X" if request.form.get("fim_imposto_renda") == "on" else " "
    x_cfpp = "X" if request.form.get("fim_cadastro_sistema") == "on" else " "

    obm_sigla = get_obm_sigla_from_militar(militar)

    mapping = {
        "{nome_completo}": (militar.nome_completo or "").strip(),
        "{rg}": (militar.rg or "").strip(),
        "{cpf}": (militar.cpf or "").strip(),
        "{matricula}": (militar.matricula or "").strip(),
        "{obm}": (obm_sigla or "").strip(),

        "{nome_dependente}": request.form.get("nome_dependente", "").strip(),
        "{grau_parentesco}": request.form.get("grau_parentesco", "").strip(),
        "{idade_dependente}": request.form.get("idade_dependente", "").strip(),

        "({x_imposto_renda})": f"({x_ir})",
        "({x_cadastro_sistema})": f"({x_cfpp})",
    }

    dia = request.form.get("dia", "....")
    mes = request.form.get("mes", "........................")
    ano_str = request.form.get("ano", "....")
    mapping["Manaus, ........ de ........................ de ...."] = data_manaus_extenso()

    docx_bytes = docx_fill_template(TEMPLATE_DOCX_PATH, mapping)

    filename = f"REQUERIMENTO_INCLUSAO_DEPENDENTE_{protocolo}.docx"
    bio = BytesIO(docx_bytes)
    bio.seek(0)

    resp = send_file(
        bio,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    resp.headers["X-DEP-TOKEN"] = token
    resp.headers["X-DEP-PROTOCOLO"] = protocolo
    return resp


@bp_dep.get("/dependentes/upload")
def upload_page():
    """
    Página de upload — token vem por querystring (?t=...)
    """
    token = request.args.get("t", "")
    return render_template("dependentes/upload_dependente.html", token=token)


MANAUS_TZ = ZoneInfo("America/Manaus")


def now_manaus():
    return datetime.now(MANAUS_TZ)


def get_client_ip():
    # Se tiver proxy/reverse, o IP real pode vir no X-Forwarded-For
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


@bp_dep.get("/dependentes/acompanhar")
@login_required
def militar_acompanhar():
    """
    Mostra o último processo do militar (ou o mais recente).
    Se quiser, dá pra passar ?protocolo=DEP-XXXX e achar específico.
    """
    militar = get_militar_from_current_user()

    protocolo = (request.args.get("protocolo") or "").strip().upper()

    q = DepProcesso.query.filter(DepProcesso.militar_id == militar.id)

    if protocolo:
        q = q.filter(DepProcesso.protocolo == protocolo)

    p = q.order_by(desc(DepProcesso.enviado_em), desc(DepProcesso.id)).first()

    if not p:
        # ainda não tem processo
        return render_template("dependentes/acompanhar.html", militar=militar, p=None, arquivos=[])

    # arquivos já anexados (sem presigned aqui; só mostrar)
    arquivos = []
    for a in getattr(p, "arquivos", []):
        arquivos.append({
            "id": a.id,
            "nome": getattr(a, "nome_original", None) or "Arquivo",
            "key": a.object_key
        })

    return render_template("dependentes/acompanhar.html", militar=militar, p=p, arquivos=arquivos)


@bp_dep.get("/dependentes/reenvio/<int:processo_id>")
@login_required
def militar_reenvio_page(processo_id):
    militar = get_militar_from_current_user()
    p = DepProcesso.query.get_or_404(processo_id)

    if p.militar_id != militar.id:
        return "Acesso negado.", 403

    if (p.status or "").upper() != "INDEFERIDO":
        flash("Este protocolo não está indeferido.", "warning")
        return redirect(url_for("dep.militar_acompanhar", protocolo=p.protocolo))

    return render_template("dependentes/reenvio.html", p=p)


@bp_dep.post("/dependentes/reenvio/<int:processo_id>")
@login_required
def militar_reenvio_post(processo_id):
    militar = get_militar_from_current_user()
    p = DepProcesso.query.get_or_404(processo_id)

    if p.militar_id != militar.id:
        return "Acesso negado.", 403

    if (p.status or "").upper() != "INDEFERIDO":
        flash("Este protocolo não está indeferido.", "warning")
        return redirect(url_for("dep.militar_acompanhar", protocolo=p.protocolo))

    files = request.files.getlist("arquivos")
    if not files or all(f.filename.strip() == "" for f in files):
        flash("Nenhum arquivo enviado.", "danger")
        return redirect(url_for("dep.militar_reenvio_page", processo_id=p.id))

    ip = get_client_ip()

    key_prefix = build_prefix_dependente(p.ano, p.militar_id, p.protocolo)

    for f in files:
        if not f or not f.filename:
            continue

        obj_key = b2_upload_fileobj(f, key_prefix=key_prefix)

        ctype = f.mimetype or "application/octet-stream"

        # registra arquivo no banco
        a = DepArquivo(
            processo_id=p.id,
            object_key=obj_key,
            nome_original=f.filename,
            content_type=ctype,
            criado_em=now_manaus(),
        )
        database.session.add(a)

    # volta o processo pra ENVIADO e registra novo envio
    p.status = "ENVIADO"
    p.enviado_em = func.now()
    p.enviado_ip = ip

    database.session.add(DepAcaoLog(
        processo_id=p.id,
        acao="MILITAR_REENVIOU",
        user_id=current_user.id,
        ip=ip,
        detalhes="Reenvio de documentos após indeferimento."
    ))

    database.session.commit()

    flash("Reenvio realizado. Aguarde nova conferência do DRH.", "success")
    return redirect(url_for("dep.militar_acompanhar", protocolo=p.protocolo))


@bp_dep.post("/dependentes/upload")
@login_required
def upload_post():
    token = (request.form.get("token") or "").strip()
    try:
        payload = load_dep_token(token, max_age_hours=24)
    except BadSignature:
        return "Token inválido ou expirado.", 400

    militar_id = payload["militar_id"]
    ano = payload["ano"]
    protocolo = payload["protocolo"]

    files = request.files.getlist("arquivos")
    if not files or all(f.filename.strip() == "" for f in files):
        return "Nenhum arquivo enviado.", 400

    key_prefix = build_prefix_dependente(ano, militar_id, protocolo)

    uploaded = []
    for f in files:
        if not f or not f.filename:
            continue
        obj_key = b2_upload_fileobj(f, key_prefix=key_prefix)
        uploaded.append((obj_key, f.filename, f.mimetype))

    # ====== BANCO: cria/atualiza processo ======
    processo = DepProcesso.query.filter_by(protocolo=protocolo).first()
    if not processo:
        processo = DepProcesso(
            protocolo=protocolo,
            militar_id=militar_id,
            ano=ano,
            status="ENVIADO",
            enviado_em=now_manaus(),
            enviado_ip=get_client_ip(),
        )
        database.session.add(processo)

    # registra arquivos (uma linha por arquivo)
    for obj_key, nome, ctype in uploaded:
        database.session.add(DepArquivo(
            processo=processo,
            object_key=obj_key,
            nome_original=nome,
            content_type=ctype,
            criado_em=now_manaus(),
        ))

    # log de ação do militar
    database.session.add(DepAcaoLog(
        processo=processo,
        acao="MILITAR_ENVIOU",
        user_id=getattr(current_user, "id", None),
        ip=get_client_ip(),
        criado_em=now_manaus(),
        detalhes=f"Enviou {len(uploaded)} arquivo(s).",
    ))

    database.session.commit()

    return render_template("dependentes/upload_sucesso.html", protocolo=protocolo, uploaded=[x[0] for x in uploaded])


@bp_dep.get("/dp/dependentes")
@login_required
@checar_ocupacao('DIRETOR DRH', 'CHEFE DRH', 'SUPER USER', 'DIRETOR', 'CHEFE', 'DRH')
def drh_lista_processos():
    """
    Lista TODOS os militares:
    - Com processo (status real)
    - Sem processo (status = NÃO ENVIADO)
    """

    DP = aliased(DepProcesso)

    resultados = (
        database.session.query(
            Militar,
            DP
        )
        .outerjoin(
            DP,
            DP.militar_id == Militar.id
        )
        .order_by(
            # quem enviou aparece primeiro
            DP.enviado_em.desc().nullslast(),
            Militar.nome_completo.asc()
        )
        .all()
    )

    return render_template(
        "dp/dep_lista.html",
        resultados=resultados
    )


def get_client_ip():
    # se tem proxy/load balancer: X-Forwarded-For
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


@bp_dep.get("/drh/dependentes/<int:processo_id>")
@login_required
@checar_ocupacao('DIRETOR DRH', 'CHEFE DRH', 'SUPER USER', 'DIRETOR', 'CHEFE', 'DRH')
def drh_detalhe_processo(processo_id):
    p = DepProcesso.query.get_or_404(processo_id)

    arquivos = []
    for a in p.arquivos:
        url = b2_presigned_get(
            a.object_key, expires_seconds=3600, download_name=a.nome_original or "arquivo")
        arquivos.append({"id": a.id, "nome": a.nome_original,
                        "url": url, "key": a.object_key})

    return render_template("dp/dep_detalhe.html", p=p, arquivos=arquivos)


@bp_dep.post("/drh/dependentes/<int:processo_id>/conferir")
@login_required
@checar_ocupacao('DIRETOR DRH', 'CHEFE DRH', 'SUPER USER', 'DIRETOR', 'CHEFE', 'DRH')
def drh_conferir_processo(processo_id):
    p = DepProcesso.query.get_or_404(processo_id)

    ip = get_client_ip()
    # marca como conferido + coloca em análise (ou mantém status atual, você decide)
    if (p.status or "ENVIADO").upper() == "ENVIADO":
        p.status = "EM_ANALISE"

    # timestamptz no banco (melhor seria server_default, mas ok)
    p.conferido_em = datetime.now()
    p.conferido_ip = ip
    p.conferido_por_id = current_user.id

    # log
    log = DepAcaoLog(
        processo_id=p.id,
        acao="DRH_CONFERIU",
        user_id=current_user.id,
        ip=ip,
        detalhes="CHECK DRH realizado."
    )
    database.session.add(log)
    database.session.commit()

    flash("Check registrado com sucesso.", "success")
    return redirect(request.referrer or url_for("dep.drh_detalhe_processo", processo_id=p.id))


@bp_dep.post("/drh/dependentes/<int:processo_id>/indeferir")
@login_required
@checar_ocupacao('DIRETOR DRH', 'CHEFE DRH', 'SUPER USER', 'DIRETOR', 'CHEFE', 'DRH')
def drh_indeferir_processo(processo_id):
    p = DepProcesso.query.get_or_404(processo_id)

    motivo = (request.form.get("motivo") or "").strip()
    if not motivo:
        flash("Informe o motivo do indeferimento.", "warning")
        return redirect(url_for("dep.drh_detalhe_processo", processo_id=p.id))

    ip = get_client_ip()

    p.status = "INDEFERIDO"
    p.indeferido_motivo = motivo
    p.indeferido_em = func.now()
    p.indeferido_por_id = current_user.id
    p.indeferido_ip = ip

    log = DepAcaoLog(
        processo_id=p.id,
        acao="DRH_INDEFERIU",
        user_id=current_user.id,
        ip=ip,
        detalhes=motivo
    )
    database.session.add(log)
    database.session.commit()

    flash("Protocolo indeferido e registrado no log.", "danger")
    return redirect(url_for("dep.drh_detalhe_processo", processo_id=p.id))


@bp_dep.post("/drh/dependentes/<int:processo_id>/deferir")
@login_required
@checar_ocupacao('DIRETOR DRH', 'CHEFE DRH', 'SUPER USER', 'DIRETOR', 'CHEFE', 'DRH')
def drh_deferir_processo(processo_id):
    p = DepProcesso.query.get_or_404(processo_id)

    ip = get_client_ip()

    p.status = "DEFERIDO"
    p.conferido_em = datetime.now()
    p.conferido_ip = ip
    p.conferido_por_id = current_user.id

    log = DepAcaoLog(
        processo_id=p.id,
        acao="DRH_DEFERIU",
        user_id=current_user.id,
        ip=ip,
        detalhes="Deferido pelo DRH."
    )
    database.session.add(log)
    database.session.commit()

    flash("Protocolo deferido com sucesso.", "success")
    return redirect(url_for("dep.drh_detalhe_processo", processo_id=p.id))
