from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import exists, func, and_, literal, or_
from src import database
from src.formatar_cpf import get_militar_por_user
from src.models import MilitarObmFuncao, NovoPaf, Obm, PafCapacidade, Militar, PostoGrad, User
from zoneinfo import ZoneInfo

bp_paf = Blueprint("paf", __name__, url_prefix="/paf")


def _ano_atual_manaus():
    return datetime.now(ZoneInfo("America/Manaus")).year


def _funcao_nome():
    # Usa o nome da função se existir; senão tenta um atributo 'perfil' (se você já injeta isso em algum lugar)
    return (getattr(getattr(current_user, "funcao_user", None), "nome", None) or
            getattr(current_user, "perfil", "") or "").upper()


def _is_drh_like():
    # Mesmos papéis usados nas declarações
    return _funcao_nome() in {"DRH", "DIRETOR DRH", "DRH CHEFE", "CHEFE DRH", "SUPER USER"}


def _is_super_user():
    return _funcao_nome() == "SUPER USER"


def _obms_do_usuario():
    obms = []
    if getattr(current_user, "obm_id_1", None):
        obms.append(current_user.obm_id_1)
    if getattr(current_user, "obm_id_2", None):
        obms.append(current_user.obm_id_2)
    return set(obms)


def _eh_chefe_do(militar_id: int) -> bool:
    # DRH-like pode tudo; caso contrário, tem de compartilhar OBM ativa com o militar
    if _is_drh_like():
        return True
    obms = _obms_do_usuario()
    if not obms:
        return False
    return bool(database.session.query(
        exists().where(and_(
            MilitarObmFuncao.militar_id == militar_id,
            MilitarObmFuncao.obm_id.in_(obms),
            MilitarObmFuncao.data_fim.is_(None),
        ))
    ).scalar())


@bp_paf.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    # militar padrão é o próprio
    militar = get_militar_por_user(current_user)
    if not militar:
        flash("Não foi possível localizar seus dados.", "danger")
        return redirect(url_for("home"))

    ano = request.values.get("ano", type=int) or _ano_atual_manaus()

    # checagem: já existe PAF deste militar neste ano?
    ja_tem = database.session.query(
        database.session.query(NovoPaf.id)
        .filter(NovoPaf.militar_id == militar.id, NovoPaf.ano_referencia == ano)
        .exists()
    ).scalar()

    if ja_tem:
        flash(
            "Você já enviou um PAF para este ano. Não é possível enviar outro.", "warning")
        return redirect(url_for("paf.minhas", ano=ano))

    if request.method == "POST":
        o1 = request.form.get("opcao_1", type=int)
        o2 = request.form.get("opcao_2", type=int)
        o3 = request.form.get("opcao_3", type=int)

        if not all([o1, o2, o3]) or any(m < 1 or m > 12 for m in [o1, o2, o3]):
            flash("Escolha 3 meses válidos (1 a 12).", "warning")
            return redirect(request.url)
        if len({o1, o2, o3}) != 3:
            flash("As três opções devem ser diferentes.", "warning")
            return redirect(request.url)

        # 1 por militar/ano
        existe = database.session.query(NovoPaf.id).filter_by(
            militar_id=militar.id, ano_referencia=ano).first()
        if existe:
            flash("Você já enviou uma solicitação para este ano.", "warning")
            return redirect(url_for("paf.minhas", ano=ano))

        paf = NovoPaf(
            militar_id=militar.id,
            ano_referencia=ano,
            opcao_1=o1, opcao_2=o2, opcao_3=o3,
            status="enviado"
        )
        database.session.add(paf)
        database.session.commit()
        flash("Solicitação enviada ao seu chefe para avaliação.", "success")
        return redirect(url_for("paf.minhas", ano=ano))

    return render_template("paf/paf_novo.html", militar=militar, ano=ano)


@bp_paf.route("/minhas")
@login_required
def minhas():
    militar = get_militar_por_user(current_user)
    if not militar:
        flash("Não foi possível localizar seus dados.", "danger")
        return redirect(url_for("home"))

    ano = request.args.get("ano", type=int) or _ano_atual_manaus()
    pafs = (database.session.query(NovoPaf)
            .filter(NovoPaf.militar_id == militar.id, NovoPaf.ano_referencia == ano)
            .order_by(NovoPaf.created_at.desc())
            .all())
    return render_template("paf/paf_minhas.html", pafs=pafs, ano=ano, militar=militar)


@bp_paf.route("/aprovar/<int:paf_id>", methods=["POST"])
@login_required
def aprovar(paf_id):
    paf = database.session.get(NovoPaf, paf_id)
    if not paf:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("paf.minhas"))
    if not _eh_chefe_do(paf.militar_id):
        flash("Você não pode aprovar este PAF.", "danger")
        return redirect(url_for("paf.minhas"))

    acao = request.form.get("acao")  # "aprovar" ou "reprovar"
    just = request.form.get("justificativa", "")
    if acao == "aprovar":
        paf.status = "aprovado_chefe"
    else:
        paf.status = "reprovado_chefe"
    paf.aprovado_por_user_id = current_user.id
    paf.aprovado_em = func.now()
    paf.justificativa = just or paf.justificativa
    database.session.commit()
    flash("Avaliação registrada.", "success")
    return redirect(request.referrer or url_for("paf.minhas"))


def _capacidade_disponivel(ano: int, mes: int) -> tuple[int, int, int]:
    """retorna (limite, ocupadas, disponíveis)"""
    cap = database.session.query(PafCapacidade.limite).filter_by(
        ano=ano, mes=mes).scalar() or 0
    ocup = database.session.query(func.count(NovoPaf.id)).filter(
        NovoPaf.ano_referencia == ano,
        NovoPaf.mes_definido == mes,
        NovoPaf.status.in_(["validado_drh"])
    ).scalar() or 0
    return cap, ocup, max(cap - ocup, 0)


def _alocar_automaticamente(paf: NovoPaf) -> bool:
    """tenta alocar no 1º mês disponível dentre as 3 opções; retorna True se alocou"""
    for mes in [paf.opcao_1, paf.opcao_2, paf.opcao_3]:
        cap, ocup, disp = _capacidade_disponivel(paf.ano_referencia, mes)
        if cap == 0:
            continue  # sem configuração ou zero de limite => considere indisponível
        if disp > 0:
            paf.mes_definido = mes
            paf.status = "validado_drh"
            paf.validado_por_user_id = current_user.id
            paf.validado_em = func.now()
            return True
    return False


@bp_paf.route("/validar/<int:paf_id>", methods=["GET", "POST"])
@login_required
def validar(paf_id):
    if not _is_drh_like():
        flash("Apenas DRH pode validar.", "danger")
        return redirect(url_for("paf.minhas"))

    paf = database.session.get(NovoPaf, paf_id)
    if not paf:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("paf.minhas"))

    ano = paf.ano_referencia
    # mapa de capacidade pra tela
    caps = {m: _capacidade_disponivel(ano, m) for m in range(1, 13)}

    if request.method == "POST":
        if request.form.get("acao") == "auto":
            if _alocar_automaticamente(paf):
                database.session.commit()
                flash("Alocado automaticamente.", "success")
                return redirect(url_for("paf.validar", paf_id=paf.id))
            paf.status = "aguardando_drh"
            database.session.commit()
            flash("Todas as opções estão cheias. Selecione manualmente.", "warning")
            return redirect(url_for("paf.validar", paf_id=paf.id))

        # manual
        mes_sel = request.form.get("mes_definido", type=int)
        if not mes_sel or mes_sel < 1 or mes_sel > 12:
            flash("Selecione um mês válido.", "warning")
            return redirect(request.url)

        cap, ocup, disp = _capacidade_disponivel(ano, mes_sel)
        if cap and disp <= 0:
            flash("Esse mês está cheio.", "danger")
            return redirect(request.url)

        paf.mes_definido = mes_sel
        paf.status = "validado_drh"
        paf.validado_por_user_id = current_user.id
        paf.validado_em = func.now()
        database.session.commit()
        flash("Alocado com sucesso.", "success")
        return redirect(url_for("paf.validar", paf_id=paf.id))

    return render_template("paf/paf_validar.html", paf=paf, caps=caps)


@bp_paf.route("/capacidade", methods=["GET", "POST"])
@login_required
def capacidade():
    if not _is_drh_like():
        flash("Apenas DRH pode alterar capacidade.", "danger")
        return redirect(url_for("paf.minhas"))

    ano = request.values.get("ano", type=int) or _ano_atual_manaus()
    if request.method == "POST":
        for m in range(1, 13):
            lim = request.form.get(f"limite_{m}", type=int)
            if lim is None:
                continue
            row = database.session.query(
                PafCapacidade).filter_by(ano=ano, mes=m).first()
            if not row:
                row = PafCapacidade(ano=ano, mes=m, limite=max(lim, 0))
                database.session.add(row)
            else:
                row.limite = max(lim, 0)
        database.session.commit()
        flash("Capacidade salva.", "success")
        return redirect(url_for("paf.capacidade", ano=ano))

    rows = (database.session.query(PafCapacidade)
            .filter(PafCapacidade.ano == ano).all())
    limite_map = {r.mes: r.limite for r in rows}
    usados = (database.session.query(NovoPaf.mes_definido, func.count(NovoPaf.id))
              .filter(NovoPaf.ano_referencia == ano, NovoPaf.status == 'validado_drh', NovoPaf.mes_definido.isnot(None))
              .group_by(NovoPaf.mes_definido).all())
    usado_map = {m: c for m, c in usados}
    return render_template("paf/paf_capacidade.html", ano=ano, limite_map=limite_map, usado_map=usado_map)


@bp_paf.route("/recebimento", methods=["GET"])
@login_required
def recebimento():
    ano = request.args.get("ano", type=int) or _ano_atual_manaus()
    # pendente, aprovado_chefe, reprovado_chefe, aguardando_drh, validado_drh, todos
    status = (request.args.get("status") or "todos").lower()
    q = (request.args.get("q") or "").strip()
    obm_id = request.args.get("obm_id", type=int)

    D, M, PG, MOF, O = NovoPaf, Militar, PostoGrad, MilitarObmFuncao, Obm

    is_drh_like = _is_drh_like()
    is_super = _is_super_user()
    user_obms = _obms_do_usuario()

    qry = (database.session.query(
        D, M,
        PG.sigla.label("pg_sigla"),
        O.sigla.label("obm_sigla"))
        .join(M, M.id == D.militar_id)
        .outerjoin(PG, PG.id == M.posto_grad_id)
        .join(MOF, and_(MOF.militar_id == M.id, MOF.data_fim.is_(None)))
        .join(O, O.id == MOF.obm_id)
        .filter(D.ano_referencia == ano))

    # Filtro por OBM escolhido no filtro
    if obm_id:
        qry = qry.filter(MOF.obm_id == obm_id)

    # Escopo do usuário (chefia só vê as próprias OBMs; DRH/SUPER vê tudo)
    if not is_drh_like:
        if user_obms:
            qry = qry.filter(MOF.obm_id.in_(user_obms))
        else:
            qry = qry.filter(literal(False))  # sem OBM vinculada → não vê nada

    # Busca livre
    if q:
        ilike = f"%{q}%"
        qry = qry.filter(or_(
            M.nome_completo.ilike(ilike),
            M.matricula.ilike(ilike),
            PG.sigla.ilike(ilike),
            O.sigla.ilike(ilike),
        ))

    # Filtro de status
    if status != "todos":
        qry = qry.filter(D.status == status)

    rows = (qry
            .order_by(D.created_at.desc(), M.nome_completo.asc(), D.id.desc())
            .all())

    # Para o template decidir botões/ações
    return render_template(
        "paf/paf_recebimento.html",
        rows=rows,
        ano=ano,
        q=q,
        status=request.args.get("status", "todos").lower(),
        obm_id=request.args.get("obm_id", type=int),
        obms=database.session.query(Obm).order_by(Obm.sigla).all(),
        is_drh=_is_drh_like(),
    )
