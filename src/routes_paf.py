from datetime import datetime, timedelta
from encodings import aliases
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import case, exists, func, and_, literal, or_, select
from src import database
from src.formatar_cpf import get_militar_por_user
from src.models import MilitarObmFuncao, NovoPaf, Obm, PafCapacidade, Militar, PafFeriasPlano, PostoGrad, User
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
        justificativa_usuario = (request.form.get("observacoes") or "").strip()

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
            justificativa=justificativa_usuario,
            updated_at=agora_manaus,
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

    # opções (NovoPaf)
    pafs = (database.session.query(NovoPaf)
            .filter(NovoPaf.militar_id == militar.id, NovoPaf.ano_referencia == ano)
            .order_by(NovoPaf.created_at.desc())
            .all())

    # plano de férias (PafFeriasPlano) — pega o mais recente do ano
    plano = (database.session.query(PafFeriasPlano)
             .filter(PafFeriasPlano.militar_id == militar.id,
                     PafFeriasPlano.ano_referencia == ano)
             .order_by(PafFeriasPlano.id.desc())
             .first())

    return render_template(
        "paf/paf_minhas.html",
        pafs=pafs, ano=ano, militar=militar, plano=plano
    )


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

    acao = (request.form.get("acao") or "").lower()            # "aprovar" | "reprovar"
    motivo = (request.form.get("justificativa") or "").strip() # texto do modal na reprovação
    agora_manaus = datetime.now(ZoneInfo("America/Manaus"))

    if acao == "aprovar":
        # Aprovado pela chefia — NÃO mexe em paf.justificativa (vem do usuário)
        paf.status = "aprovado_chefe"
        paf.aprovado_por_user_id = current_user.id
        paf.aprovado_em = agora_manaus

    elif acao == "reprovar":
        # Obriga motivo e salva em OBSERVACOES (justificativa da chefia)
        if not motivo:
            flash("Informe a justificativa da reprovação.", "warning")
            return redirect(request.referrer or url_for("paf.minhas"))

        paf.status = "reprovado_chefe"
        paf.observacoes = motivo                  # << justificativa do chefe
        paf.aprovado_por_user_id = current_user.id
        paf.aprovado_em = agora_manaus

    else:
        flash("Ação inválida.", "warning")
        return redirect(request.referrer or url_for("paf.minhas"))

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
    PFP = PafFeriasPlano

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
            D.justificativa,     # << adicionar
            D.observacoes,       # << adicionar
            rn
        )
        .filter(D.ano_referencia == ano)
        .subquery()
    )

    rn_plano = func.row_number().over(
        partition_by=PFP.militar_id,
        order_by=(PFP.updated_at.desc().nullslast(), PFP.id.desc())
    ).label("rn")

    ultimo_plano_sq = (
        database.session.query(
            PFP.militar_id.label("m_id"),
            PFP.id.label("plano_id"),
            PFP.status.label("plano_status"),
            PFP.direito_total_dias,
            PFP.qtd_dias_p1, PFP.inicio_p1, PFP.fim_p1,
            PFP.qtd_dias_p2, PFP.inicio_p2, PFP.fim_p2,
            PFP.qtd_dias_p3, PFP.inicio_p3, PFP.fim_p3,
            rn_plano
        )
        .filter(PFP.ano_referencia == ano)
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
            # PAF
            ultimo_paf_sq.c.paf_id,
            ultimo_paf_sq.c.paf_status,
            ultimo_paf_sq.c.opcao_1,
            ultimo_paf_sq.c.opcao_2,
            ultimo_paf_sq.c.opcao_3,
            ultimo_paf_sq.c.mes_definido,
            ultimo_paf_sq.c.recebido_em,
            ultimo_paf_sq.c.created_at,
            ultimo_paf_sq.c.updated_at,
            # PLANO
            ultimo_plano_sq.c.plano_id,
            ultimo_plano_sq.c.plano_status,
            ultimo_plano_sq.c.direito_total_dias,
            ultimo_plano_sq.c.qtd_dias_p1, ultimo_plano_sq.c.inicio_p1, ultimo_plano_sq.c.fim_p1,
            ultimo_plano_sq.c.qtd_dias_p2, ultimo_plano_sq.c.inicio_p2, ultimo_plano_sq.c.fim_p2,
            ultimo_plano_sq.c.qtd_dias_p3, ultimo_plano_sq.c.inicio_p3, ultimo_plano_sq.c.fim_p3,
            ultimo_paf_sq.c.justificativa,
            ultimo_paf_sq.c.observacoes,
        )
        .join(base_cte, base_cte.c.m_id == M.id)
        .join(MOF, and_(MOF.militar_id == M.id, MOF.data_fim.is_(None)))
        .join(O, O.id == MOF.obm_id)
        .outerjoin(PG, PG.id == M.posto_grad_id)
        .outerjoin(ultimo_paf_sq, and_(ultimo_paf_sq.c.m_id == M.id, ultimo_paf_sq.c.rn == 1))
        .outerjoin(ultimo_plano_sq, and_(ultimo_plano_sq.c.m_id == M.id, ultimo_plano_sq.c.rn == 1))
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
        is_drh=True if (IS_DRH_LIKE or IS_SUPER) else False,
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


def date_from_str(s):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

def end_inclusive(start_date, days):
    return start_date + timedelta(days=days-1)

def valida_combo(direito, q1,q2,q3):
    vals = [q for q in [q1,q2,q3] if q]
    s = sum(vals)
    if direito == 40:
        return (vals == [20,20]) or (sorted(vals)==[20,20])
    # 30
    if s != 30: return False
    vals_sorted = sorted(vals)
    return (vals_sorted==[30]) or (vals_sorted==[10,20]) or (vals_sorted==[15,15]) or (vals_sorted==[10,10,10])

@bp_paf.route("/salvar-plano", methods=["POST"])
@login_required
def salvar_plano():
    militar = get_militar_por_user(current_user)
    if not militar:
        flash("Não foi possível localizar seus dados.", "danger")
        return redirect(url_for("home"))

    ano = request.form.get("ano_referencia", type=int) or (datetime.now(ZoneInfo("America/Manaus")).year+1)
    direito = request.form.get("direito_total_dias", type=int) or 30

    # também salva as 3 opções de pagamento, se vierem no POST
    o1 = request.form.get("opcao_1", type=int)
    o2 = request.form.get("opcao_2", type=int)
    o3 = request.form.get("opcao_3", type=int)

    if o1 and o2 and o3:
        ja_tem = database.session.query(
            database.session.query(NovoPaf.id)
            .filter(NovoPaf.militar_id == militar.id, NovoPaf.ano_referencia == ano)
            .exists()
        ).scalar()
        if not ja_tem:
            agora_manaus = datetime.now(ZoneInfo("America/Manaus"))
            database.session.add(NovoPaf(
                militar_id=militar.id,
                ano_referencia=ano,
                opcao_1=o1, opcao_2=o2, opcao_3=o3,
                status="enviado",
                updated_at=agora_manaus,
                created_at=agora_manaus,
                data_entrega=agora_manaus
            ))
            database.session.commit()

    # lê período 1
    q1 = request.form.get("qtd1", type=int)
    i1 = date_from_str(request.form.get("inicio1"))
    f1 = date_from_str(request.form.get("fim1"))
    m1 = request.form.get("mes1", type=int)

    # período 2
    q2 = request.form.get("qtd2", type=int)
    i2 = date_from_str(request.form.get("inicio2"))
    f2 = date_from_str(request.form.get("fim2"))
    m2 = request.form.get("mes2", type=int)

    # período 3
    q3 = request.form.get("qtd3", type=int)
    i3 = date_from_str(request.form.get("inicio3"))
    f3 = date_from_str(request.form.get("fim3"))
    m3 = request.form.get("mes3", type=int)

    # validações básicas
    if not q1 or not i1:
        flash("Informe quantidade e data de início do 1º período.", "warning")
        return redirect(request.referrer or url_for("paf.novo"))

    # recalcula fim para garantir consistência
    f1_calc = end_inclusive(i1, q1)
    if f1 != f1_calc: f1 = f1_calc
    if not m1: m1 = i1.month

    if q2 and i2:
        f2_calc = end_inclusive(i2, q2)
        if f2 != f2_calc: f2 = f2_calc
        if not m2: m2 = i2.month
    else:
        q2=i2=f2=m2=None

    if q3 and i3:
        f3_calc = end_inclusive(i3, q3)
        if f3 != f3_calc: f3 = f3_calc
        if not m3: m3 = i3.month
    else:
        q3=i3=f3=m3=None

    # regras de combinação
    if not valida_combo(direito, q1,q2,q3):
        flash("Combinação de períodos inválida para o seu direito de dias.", "danger")
        return redirect(request.referrer or url_for("paf.novo"))

    # regra dos 40 dias: gap 6 meses entre inícios
    if direito == 40 and (not q2 or not i2 or q1!=20 or q2!=20):
        flash("Para 40 dias, os períodos devem ser 20 + 20 e com 6 meses de intervalo.", "danger")
        return redirect(request.referrer or url_for("paf.novo"))
    if direito == 40 and i1 and i2:
        min_i2 = (i1.replace(day=1) + timedelta(days=31*6))  # aproxima 6 meses
        # versão exata (sem aproximação) se preferir usar relativedelta
        from dateutil.relativedelta import relativedelta
        if i2 < (i1 + relativedelta(months=+6)):
            flash("Precisa de 6 meses entre o início do 1º e 2º períodos.", "danger")
            return redirect(request.referrer or url_for("paf.novo"))

    # 1 por militar/ano
    existe = database.session.query(PafFeriasPlano.id).filter_by(militar_id=militar.id, ano_referencia=ano).first()
    if existe:
        flash("Você já cadastrou um plano de férias para este ano.", "warning")
        return redirect(url_for("paf.minhas", ano=ano))

    plano = PafFeriasPlano(
        militar_id=militar.id,
        usuario_id=current_user.id,
        ano_referencia=ano,
        direito_total_dias=direito,
        qtd_dias_p1=q1, inicio_p1=i1, fim_p1=f1, mes_usufruto_p1=m1,
        qtd_dias_p2=q2, inicio_p2=i2, fim_p2=f2, mes_usufruto_p2=m2,
        qtd_dias_p3=q3, inicio_p3=i3, fim_p3=f3, mes_usufruto_p3=m3,
        status="enviado"
    )
    database.session.add(plano)
    database.session.commit()
    flash("Plano de férias enviado para avaliação.", "success")
    return redirect(url_for("paf.minhas", ano=ano))
