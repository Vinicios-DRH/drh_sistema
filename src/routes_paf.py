from datetime import datetime
from encodings import aliases
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import case, exists, func, and_, literal, or_, select
from src import database
from src.formatar_cpf import get_militar_por_user
from src.models import MilitarObmFuncao, NovoPaf, Obm, PafCapacidade, Militar, PostoGrad, User
from zoneinfo import ZoneInfo

bp_paf = Blueprint("paf", __name__, url_prefix="/paf")


def _ocupacao_nome() -> str:
    # tenta via relação user_funcao.ocupacao (ou nome); fallback para campos soltos
    try:
        fu = getattr(current_user, "user_funcao", None) or getattr(current_user, "funcao_user", None)
        if isinstance(fu, (list, tuple)):
            for f in fu:
                oc = getattr(f, "ocupacao", None) or getattr(f, "nome", None)
                if oc:
                    return str(oc).upper()
        elif fu is not None:
            oc = getattr(fu, "ocupacao", None) or getattr(fu, "nome", None)
            if oc:
                return str(oc).upper()
    except Exception:
        pass
    # fallbacks possíveis no próprio user
    val = (getattr(current_user, "ocupacao", None)
           or getattr(current_user, "perfil", None)
           or "").upper()
    return val


def _is_super_user() -> bool:
    return "SUPER" in _ocupacao_nome()


def _user_obm_ids() -> set[int]:
    ids = {getattr(current_user, "obm_id_1", None), getattr(current_user, "obm_id_2", None)}
    ids.discard(None)
    # se existir relação many-to-many, agrega
    obms_rel = getattr(current_user, "obms", None)
    if obms_rel:
        for o in obms_rel:
            oid = getattr(o, "id", None)
            if oid:
                ids.add(oid)
    return ids


def _funcao_nome():
    # Usa o nome da função se existir; senão tenta um atributo 'perfil' (se você já injeta isso em algum lugar)
    return (getattr(getattr(current_user, "funcao_user", None), "nome", None) or
            getattr(current_user, "perfil", "") or "").upper()


def _is_drh_like() -> bool:
    # SUPER já é DRH-like
    if _is_super_user():
        return True
    up = _ocupacao_nome()
    return any(tag in up for tag in ("DRH", "DIRETOR DRH", "CHEFE DRH"))


def _obm_parent_col():
    # ajuste os possíveis nomes de coluna hierárquica
    for name in ("pai_id", "obm_pai_id", "superior_id", "id_pai"):
        if hasattr(Obm, name):
            return name
    return None


def _obm_subtree_ids(root_id: int) -> list[int]:
    parent_col = _obm_parent_col()
    if not parent_col:
        return [root_id]
    # WITH RECURSIVE
    tree = select(Obm.id).where(Obm.id == root_id).cte("obm_tree", recursive=True)
    O2 = aliases(Obm)
    tree = tree.union_all(select(O2.id).where(getattr(O2, parent_col) == tree.c.id))
    ids = [r[0] for r in database.session.execute(select(tree.c.id)).all()]
    return ids or [root_id]


def _ano_atual_manaus():
    return datetime.now(ZoneInfo("America/Manaus")).year + 1


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

        agora_manaus = datetime.now(ZoneInfo("America/Manaus"))
        paf = NovoPaf(
            militar_id=militar.id,
            ano_referencia=ano,
            opcao_1=o1, opcao_2=o2, opcao_3=o3,
            status="enviado",
            updated_at=agora_manaus,         # <— evita NULL no INSERT
            created_at=agora_manaus,
            data_entrega=agora_manaus
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

    # ---- efetivo total da corporação (militares com vínculo ativo em alguma OBM)
    MOF = MilitarObmFuncao
    efetivo_total = (database.session.query(func.count(func.distinct(MOF.militar_id)))
                     .filter(MOF.data_fim.is_(None))
                     .scalar() or 0)

    # Ação: distribuir automaticamente 1/12
    if request.method == "POST" and (request.form.get("acao") == "auto"):
        base = efetivo_total // 12
        resto = efetivo_total % 12
        for m in range(1, 13):
            sugestao = base + (1 if m <= resto else 0)
            row = (database.session.query(PafCapacidade)
                   .filter_by(ano=ano, mes=m).first())
            if not row:
                row = PafCapacidade(ano=ano, mes=m, limite=max(sugestao, 0))
                database.session.add(row)
            else:
                row.limite = max(sugestao, 0)
        database.session.commit()
        flash("Capacidade distribuída automaticamente (1/12 do efetivo).", "success")
        return redirect(url_for("paf.capacidade", ano=ano))

    # Ação: salvar edição manual
    if request.method == "POST":
        for m in range(1, 13):
            lim = request.form.get(f"limite_{m}", type=int)
            if lim is None:
                continue
            row = database.session.query(PafCapacidade).filter_by(ano=ano, mes=m).first()
            if not row:
                row = PafCapacidade(ano=ano, mes=m, limite=max(lim, 0))
                database.session.add(row)
            else:
                row.limite = max(lim, 0)
        database.session.commit()
        flash("Capacidade salva.", "success")
        return redirect(url_for("paf.capacidade", ano=ano))

    # ---- carregar dados para exibir
    rows = (database.session.query(PafCapacidade)
            .filter(PafCapacidade.ano == ano).all())
    limite_map = {r.mes: r.limite for r in rows}

    usados = (database.session.query(NovoPaf.mes_definido, func.count(NovoPaf.id))
              .filter(NovoPaf.ano_referencia == ano,
                      NovoPaf.status == 'validado_drh',
                      NovoPaf.mes_definido.isnot(None))
              .group_by(NovoPaf.mes_definido).all())
    usado_map = {m: c for m, c in usados}

    soma_limites = sum(limite_map.values()) if limite_map else 0
    diferenca = max(efetivo_total - soma_limites, 0)

    return render_template(
        "paf/paf_capacidade.html",
        ano=ano,
        limite_map=limite_map,
        usado_map=usado_map,
        efetivo_total=efetivo_total,
        soma_limites=soma_limites,
        diferenca=diferenca,
    )


@bp_paf.route("/recebimento", methods=["GET"])
@login_required
def recebimento():
    ano     = request.args.get("ano", type=int) or _ano_atual_manaus()
    status  = (request.args.get("status") or "todos").lower()  # pendente, aprovado_chefe, reprovado_chefe, aguardando_drh, validado_drh, nao_enviou, todos
    q       = (request.args.get("q") or "").strip()
    obm_id  = request.args.get("obm_id", type=int)

    D, M, PG, MOF, O = NovoPaf, Militar, PostoGrad, MilitarObmFuncao, Obm

    IS_SUPER    = _is_super_user()
    IS_DRH_LIKE = _is_drh_like()
    USER_OBMS   = _user_obm_ids()

    # ---- SUBQUERY: último PAF do ano por militar ----
    rn = func.row_number().over(
        partition_by=D.militar_id,
        order_by=(D.updated_at.desc().nullslast(), D.id.desc())
    ).label("rn")

    ultimo_paf_sq = (
        database.session.query(
            D.militar_id.label("m_id"),
            D.id.label("paf_id"),
            D.status.label("paf_status"),
            D.opcao_1, D.opcao_2, D.opcao_3,
            D.mes_definido,
            D.recebido_em, D.created_at, D.updated_at,
            rn
        )
        .filter(D.ano_referencia == ano)
        .subquery()
    )

    # ---- BASE: militares com vínculo ativo (escopo + filtros) ----
    base_q = (
        database.session.query(M.id.label("m_id"))
        .join(MOF, and_(MOF.militar_id == M.id, MOF.data_fim.is_(None)))
    )

    # Filtro por OBM selecionada (sempre por subárvore)
    if obm_id:
        base_q = base_q.filter(MOF.obm_id.in_(_obm_subtree_ids(obm_id)))

    # Escopo do usuário: Chefia/Diretor restringe às próprias OBMs; DRH-like e SUPER veem tudo
    if not (IS_DRH_LIKE or IS_SUPER):
        if USER_OBMS:
            base_q = base_q.filter(MOF.obm_id.in_(USER_OBMS))
        else:
            base_q = base_q.filter(literal(False))  # sem OBM vinculada → nada

    # Busca livre
    if q:
        ilike = f"%{q}%"
        base_q = (base_q.join(PG, PG.id == M.posto_grad_id, isouter=True)
                        .join(O, O.id == MOF.obm_id)
                        .filter(or_(M.nome_completo.ilike(ilike),
                                    M.matricula.ilike(ilike),
                                    PG.sigla.ilike(ilike),
                                    O.sigla.ilike(ilike))))

    base_cte = base_q.distinct().cte("base_militares")

    # ---- KPIs (agregações) ----
    kpi_row = (
        database.session.query(
            func.count().label("total_militares"),
            func.sum(case((ultimo_paf_sq.c.paf_id.is_(None), 1), else_=0)).label("nao_enviaram"),
            func.sum(case((ultimo_paf_sq.c.paf_status.in_(["pendente","enviado"]), 1), else_=0)).label("pendentes_chefe"),
            func.sum(case((ultimo_paf_sq.c.paf_status == "aguardando_drh", 1), else_=0)).label("aguardando_drh"),
            func.sum(case((ultimo_paf_sq.c.paf_status == "validado_drh", 1), else_=0)).label("validados_drh"),
            func.sum(case((ultimo_paf_sq.c.paf_status == "reprovado_chefe", 1), else_=0)).label("reprovados"),
        )
        .select_from(base_cte)
        .outerjoin(ultimo_paf_sq, and_(ultimo_paf_sq.c.m_id == base_cte.c.m_id,
                                       ultimo_paf_sq.c.rn == 1))
    ).one()

    kpi = dict(
        total       = int(kpi_row.total_militares or 0),
        nao_enviaram= int(kpi_row.nao_enviaram or 0),
        pendentes   = int(kpi_row.pendentes_chefe or 0),
        aguardando  = int(kpi_row.aguardando_drh or 0),
        validados   = int(kpi_row.validados_drh or 0),
        reprovados  = int(kpi_row.reprovados or 0),
    )

    # ---- Linhas (1 por militar) ----
    rows_q = (
        database.session.query(
            M,
            PG.sigla.label("pg_sigla"),
            O.sigla.label("obm_sigla"),
            ultimo_paf_sq.c.paf_id,
            ultimo_paf_sq.c.paf_status,
            ultimo_paf_sq.c.opcao_1,
            ultimo_paf_sq.c.opcao_2,
            ultimo_paf_sq.c.opcao_3,
            ultimo_paf_sq.c.mes_definido,
            ultimo_paf_sq.c.recebido_em,
            ultimo_paf_sq.c.created_at,
            ultimo_paf_sq.c.updated_at,
        )
        .join(base_cte, base_cte.c.m_id == M.id)
        .join(MOF, and_(MOF.militar_id == M.id, MOF.data_fim.is_(None)))
        .join(O, O.id == MOF.obm_id)
        .outerjoin(PG, PG.id == M.posto_grad_id)
        .outerjoin(ultimo_paf_sq, and_(ultimo_paf_sq.c.m_id == M.id,
                                       ultimo_paf_sq.c.rn == 1))
    )

    # Filtro de status
    if status == "nao_enviou":
        rows_q = rows_q.filter(ultimo_paf_sq.c.paf_id.is_(None))
    elif status == "pendente":
        rows_q = rows_q.filter(ultimo_paf_sq.c.paf_status.in_(["pendente", "enviado"]))
    elif status != "todos":
        rows_q = rows_q.filter(ultimo_paf_sq.c.paf_status == status)

    rows = rows_q.order_by(M.nome_completo.asc()).all()

    obms = database.session.query(Obm).order_by(Obm.sigla).all()

    return render_template(
        "paf/paf_recebimento.html",
        linhas=rows,
        ano=ano,
        q=q,
        status=status,
        obm_id=obm_id,
        obms=obms,
        is_drh=True if (IS_DRH_LIKE or IS_SUPER) else False,  # SUPER também vê botões de validação
        kpi=kpi,
    )


@bp_paf.route("/detalhe/<int:paf_id>", methods=["GET"])
@login_required
def detalhe(paf_id):
    paf = database.session.get(NovoPaf, paf_id)
    if not paf:
        flash("PAF não encontrado.", "danger")
        return redirect(url_for("paf.minhas"))

    # Permissão: DRH/SUPER, chefe do militar, ou o próprio militar
    is_drh = _is_drh_like() or _is_super_user()
    sou_dono = False
    try:
        meu_militar = get_militar_por_user(current_user)
        sou_dono = bool(meu_militar and meu_militar.id == paf.militar_id)
    except Exception:
        pass
    pode_ver = is_drh or sou_dono or _eh_chefe_do(paf.militar_id)
    if not pode_ver:
        flash("Você não tem permissão para ver este PAF.", "warning")
        return redirect(url_for("paf.minhas"))

    # Dados do militar/PG/OBM (atuais)
    M, PG, MOF, O = Militar, PostoGrad, MilitarObmFuncao, Obm
    m_row = (database.session.query(M, PG.sigla.label("pg_sigla"), O.sigla.label("obm_sigla"))
             .outerjoin(PG, PG.id == M.posto_grad_id)
             .outerjoin(MOF, and_(MOF.militar_id == M.id, MOF.data_fim.is_(None)))
             .outerjoin(O, O.id == MOF.obm_id)
             .filter(M.id == paf.militar_id)
             .first())
    militar, pg_sigla, obm_sigla = (m_row or (None, None, None))

    return render_template(
        "paf/paf_detalhe.html",
        paf=paf, militar=militar, pg_sigla=pg_sigla, obm_sigla=obm_sigla
    )


@bp_paf.route("/novo-periodo", methods=["GET", "POST"])
@login_required
def novo_periodo():
    pass
