from datetime import date, datetime, timedelta
from encodings import aliases
from flask import Blueprint, render_template, request, redirect, send_file, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import case, exists, func, and_, literal, or_, select, text
from src import database
from src.formatar_cpf import get_militar_por_user
from src.services.paf_service import conta_envia_paf, pode_enviar_paf
from src.models import MilitarObmFuncao, NovoPaf, Obm, PafCapacidade, Militar, PafFeriasPlano, PostoGrad, User
from src.utils.utils import registrar_log_download
from zoneinfo import ZoneInfo
from functools import lru_cache
from math import ceil
from sqlalchemy.orm import aliased
from io import BytesIO
import pandas as pd


bp_paf = Blueprint("paf", __name__, url_prefix="/paf")
MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _ocupacao_nome() -> str:
    # tenta via relação user_funcao.ocupacao (ou nome); fallback para campos soltos
    try:
        fu = getattr(current_user, "user_funcao", None) or getattr(
            current_user, "funcao_user", None)
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
    ids = {getattr(current_user, "obm_id_1", None),
           getattr(current_user, "obm_id_2", None)}
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
    tree = select(Obm.id).where(Obm.id == root_id).cte(
        "obm_tree", recursive=True)
    O2 = aliases(Obm)
    tree = tree.union_all(select(O2.id).where(
        getattr(O2, parent_col) == tree.c.id))
    ids = [r[0] for r in database.session.execute(select(tree.c.id)).all()]
    return ids or [root_id]


# DIRETOR, CHEFE, DRH/DP, SUPER USER, DIRETOR DRH — mesma regra do menu "PAF do Efetivo"
FUNCOES_PAF_EFETIVO = {1, 2, 5, 6, 7}


def _pode_ver_efetivo() -> bool:
    """Tela do efetivo (/paf/recebimento), Excel e aprovação: só chefia e DP.
    A conta pessoal do militar (ATUALIZACAO CADASTRAL) não entra."""
    return _is_drh_like() or int(getattr(current_user, "funcao_user_id", 0) or 0) in FUNCOES_PAF_EFETIVO


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


def _mes_ocupado_expr():
    # Cada PAF do ano ocupa 1 vaga: no mês que a DP definiu ou, enquanto ela
    # não define, na 1ª opção do militar (quem envia primeiro garante o mês).
    return func.coalesce(NovoPaf.mes_definido, NovoPaf.opcao_1)


def _ocupacao_por_mes(ano: int, excluir_paf_id: int | None = None) -> dict[int, int]:
    mes_expr = _mes_ocupado_expr()
    q = (database.session.query(mes_expr, func.count(NovoPaf.id))
         .filter(NovoPaf.ano_referencia == ano, mes_expr.isnot(None)))
    if excluir_paf_id:
        q = q.filter(NovoPaf.id != excluir_paf_id)
    return {int(m): int(c) for m, c in q.group_by(mes_expr).all()}


def _vagas_por_mes(ano: int, excluir_paf_id: int | None = None) -> dict[int, dict]:
    """{mes: {limite, ocupadas, restantes}} — limite None = mês sem capacidade
    cadastrada, tratado como sem limite na escolha do militar."""
    limites = {r.mes: r.limite for r in database.session.query(PafCapacidade)
               .filter(PafCapacidade.ano == ano)}
    ocup = _ocupacao_por_mes(ano, excluir_paf_id)
    vagas = {}
    for m in range(1, 13):
        lim = limites.get(m)
        oc = ocup.get(m, 0)
        vagas[m] = {"limite": lim, "ocupadas": oc,
                    "restantes": None if lim is None else max(lim - oc, 0)}
    return vagas


def _travar_mes(ano: int, mes: int) -> None:
    # Serializa quem disputa a última vaga do mesmo mês; solta no commit/rollback.
    database.session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :k)"), {"ns": 7230, "k": ano * 100 + mes})


def _tem_vaga_1a_opcao(ano: int, mes: int, excluir_paf_id: int | None = None) -> bool:
    """Confere (com trava) se ainda há vaga para o militar escolher `mes` como 1ª opção."""
    _travar_mes(ano, mes)
    restantes = _vagas_por_mes(ano, excluir_paf_id)[mes]["restantes"]
    return restantes is None or restantes > 0


def _capacidade_disponivel(ano: int, mes: int, excluir_paf_id: int | None = None) -> tuple[int, int, int]:
    """retorna (limite, ocupadas, disponíveis)"""
    v = _vagas_por_mes(ano, excluir_paf_id)[mes]
    cap = v["limite"] or 0
    return cap, v["ocupadas"], max(cap - v["ocupadas"], 0)


def _homologar(paf: NovoPaf, mes: int) -> None:
    """Homologa o mês de recebimento. As datas de usufruto NÃO são lançadas
    aqui — continuam no módulo de Férias (/ferias-chefe)."""
    paf.mes_definido = mes
    paf.status = "validado_drh"
    paf.validado_por_user_id = current_user.id
    paf.validado_em = func.now()


def _alocar_automaticamente(paf: NovoPaf) -> bool:
    """tenta alocar no 1º mês disponível dentre as 3 opções; retorna True se alocou"""
    for mes in [paf.opcao_1, paf.opcao_2, paf.opcao_3]:
        cap, ocup, disp = _capacidade_disponivel(paf.ano_referencia, mes, paf.id)
        if cap == 0:
            continue  # sem configuração ou zero de limite => considere indisponível
        if disp > 0:
            _homologar(paf, mes)
            return True
    return False


def _pode_editar_paf(paf) -> bool:
    # super sempre pode
    try:
        if _is_super_user():
            current_app.logger.warning(
                "[PAF EDITAR] SUPER liberado (paf_id=%s)", getattr(paf, "id", None))
            return True
    except Exception:
        pass

    uid = getattr(current_user, "id", None)

    # compara direto no relacionamento já ligado ao PAF
    try:
        paf_owner_uid = int(
            getattr(getattr(paf, "militar", None), "usuario_id", 0) or 0)
        cur_uid = int(uid or 0)
        current_app.logger.warning("[PAF EDITAR] owner check: paf.militar.usuario_id=%s  current_user.id=%s  paf_id=%s",
                                   paf_owner_uid, cur_uid, getattr(paf, "id", None))
        return paf_owner_uid == cur_uid
    except Exception as e:
        current_app.logger.warning("[PAF EDITAR] owner check exception: %r", e)
        return False


# cache simples em memória para itens raramente mutáveis (ajuste TTL se quiser)
@lru_cache(maxsize=1)
def _cached_obms_postos():
    obms = database.session.query(Obm.id, Obm.sigla).order_by(Obm.sigla).all()
    postos = database.session.query(PostoGrad.id, PostoGrad.sigla).order_by(PostoGrad.id).all()
    return obms, postos


@bp_paf.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    # militar padrão é o próprio
    militar = get_militar_por_user(current_user)
    if not militar:
        flash("Não foi possível localizar seus dados.", "danger")
        return redirect(url_for("home"))

    # conta ATUALIZACAO CADASTRAL ou de comando + posto liberado na etapa atual; vale pro GET e pro POST
    if not pode_enviar_paf(current_user, militar):
        if not conta_envia_paf(current_user):
            flash("O PAF deve ser enviado pela sua conta pessoal (Atualização Cadastral) "
                  "ou pela conta de chefe/diretor/comandante.", "warning")
        else:
            flash("O preenchimento do PAF ainda não foi liberado para o seu posto/graduação.", "warning")
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

        if not _tem_vaga_1a_opcao(ano, o1):
            database.session.rollback()
            flash("O mês escolhido como 1ª opção não tem mais vagas. Escolha outro.", "warning")
            return redirect(request.url)

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

    return render_template("paf/paf_novo.html", militar=militar, ano=ano, vagas=_vagas_por_mes(ano))


@bp_paf.route("/minhas")
@login_required
def minhas():
    militar = get_militar_por_user(current_user)
    if not militar:
        flash("Não foi possível localizar seus dados.", "danger")
        return redirect(url_for("home"))

    ano = request.args.get("ano", type=int) or _ano_atual_manaus()

    # quem ainda não foi liberado só entra se já tiver PAF no ano (ex.: corrigir um reprovado)
    ja_tem = database.session.query(NovoPaf.id).filter_by(militar_id=militar.id, ano_referencia=ano).first()
    if not (pode_enviar_paf(current_user, militar) or ja_tem):
        flash("O preenchimento do PAF ainda não foi liberado para o seu posto/graduação.", "warning")
        return redirect(url_for("home"))

    # opções (NovoPaf)
    pafs = (database.session.query(NovoPaf)
            .filter(NovoPaf.militar_id == militar.id, NovoPaf.ano_referencia == ano)
            .order_by(NovoPaf.created_at.desc())
            .all())

    return render_template(
        "paf/paf_minhas.html",
        pafs=pafs, ano=ano, militar=militar
    )


@bp_paf.route("/aprovar/<int:paf_id>", methods=["POST"])
@login_required
def aprovar(paf_id):
    if not _pode_ver_efetivo():
        flash("Você não pode aprovar/reprovar PAF.", "danger")
        return redirect(url_for("home"))

    paf = database.session.get(NovoPaf, paf_id)
    if not paf:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("paf.minhas"))

    # permitir chefe do militar OU DRH-like OU super
    if not (_eh_chefe_do(paf.militar_id) or _is_drh_like() or _is_super_user()):
        flash("Você não pode aprovar/reprovar este PAF.", "danger")
        return redirect(url_for("paf.minhas"))

    acao = (request.form.get("acao") or "").lower()
    motivo = (request.form.get("justificativa") or "").strip()
    agora_manaus = datetime.now(ZoneInfo("America/Manaus"))

    if acao == "aprovar":
        paf.status = "aprovado_chefe"
        paf.aprovado_por_user_id = current_user.id
        paf.aprovado_em = agora_manaus

    elif acao == "reprovar":
        if not motivo:
            flash("Informe a justificativa da reprovação.", "warning")
            return redirect(request.referrer or url_for("paf.minhas"))
        # (mantém o mesmo status; mude se quiser diferenciar)
        paf.status = "reprovado_chefe"
        paf.observacoes = motivo
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
        flash("Apenas a DP pode homologar.", "danger")
        return redirect(url_for("paf.minhas"))

    paf = database.session.get(NovoPaf, paf_id)
    if not paf:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("paf.minhas"))

    ano = paf.ano_referencia
    # mapa de capacidade pra tela (sem contar a vaga que este PAF já ocupa)
    caps = {m: _capacidade_disponivel(ano, m, paf.id) for m in range(1, 13)}

    if request.method == "POST":
        # homologação feita direto da lista (/paf/recebimento) volta pra lista
        nxt = request.form.get("next") or ""
        destino = nxt if (nxt.startswith("/") and not nxt.startswith("//")) \
            else url_for("paf.validar", paf_id=paf.id)
        nome = paf.militar.nome_completo if paf.militar else f"PAF #{paf.id}"

        if request.form.get("acao") == "auto":
            if _alocar_automaticamente(paf):
                database.session.commit()
                flash("Alocado automaticamente.", "success")
                return redirect(destino)
            paf.status = "aguardando_drh"
            database.session.commit()
            flash("Todas as opções estão cheias. Selecione manualmente.", "warning")
            return redirect(destino)

        # manual
        mes_sel = request.form.get("mes_definido", type=int)
        if not mes_sel or mes_sel < 1 or mes_sel > 12:
            flash("Selecione um mês válido.", "warning")
            return redirect(destino)

        # A DP tem a palavra final: pode alocar mesmo em mês cheio (só avisa).
        v = _vagas_por_mes(ano, paf.id)[mes_sel]
        acima_limite = v["restantes"] is not None and v["restantes"] <= 0

        _homologar(paf, mes_sel)
        database.session.commit()
        mes_txt = MESES_PT[mes_sel]
        if acima_limite:
            flash(f"{nome}: homologado em {mes_txt}, acima do limite do mês "
                  f"({v['ocupadas'] + 1}/{v['limite']}).", "warning")
        else:
            flash(f"{nome}: homologado em {mes_txt}.", "success")
        return redirect(destino)

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

    # ---- carregar dados para exibir
    rows = (database.session.query(PafCapacidade)
            .filter(PafCapacidade.ano == ano).all())
    limite_map = {r.mes: r.limite for r in rows}

    usado_map = _ocupacao_por_mes(ano)

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


STATUS_LABEL = {
    "nao_enviou": "Não enviou",
    "enviado": "Pendente (chefia)",
    "pendente": "Pendente (chefia)",
    "aprovado_chefe": "Aprovado (chefia)",
    "reprovado_chefe": "Reprovado (chefia)",
    "aguardando_drh": "Aguardando DP",
    "validado_drh": "Homologado (DP)",
}
# PAF enviado que a DP ainda não homologou (reprovado volta pro militar corrigir)
STATUS_A_HOMOLOGAR = ["enviado", "pendente", "aprovado_chefe", "aguardando_drh"]


def _recebimento_filtros() -> dict:
    a = request.args
    return dict(
        ano=a.get("ano", type=int) or _ano_atual_manaus(),
        status=(a.get("status") or "todos").lower(),
        q=(a.get("q") or "").strip(),
        obm_id=a.get("obm_id", type=int),
        pg_id=a.get("pg_id", type=int),
        mes=a.get("mes", type=int),
        sort=(a.get("sort") or "chegada").lower(),
        dir=(a.get("dir") or "desc").lower(),
    )


def _recebimento_consulta(f: dict):
    """Monta (rows_q já ordenada, kpi) respeitando filtros e escopo do usuário.
    Usada pela tela e pelo Excel, pra os dois mostrarem exatamente o mesmo recorte."""
    ano = f["ano"]
    D, M, PG, MOF, O = NovoPaf, Militar, PostoGrad, MilitarObmFuncao, Obm

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
            D.validado_em,
            D.justificativa,
            D.observacoes,
            rn
        )
        .filter(D.ano_referencia == ano)
        .subquery()
    )

    # OBMs ativas agregadas numa linha só (quem tem 2 vínculos não duplica)
    obm_sq = (
        database.session.query(
            MOF.militar_id.label("m_id"),
            func.string_agg(func.distinct(O.sigla), literal(" / ")).label("obm_sigla"),
        )
        .join(O, O.id == MOF.obm_id)
        .filter(MOF.data_fim.is_(None))
        .group_by(MOF.militar_id)
        .subquery()
    )

    # ---- BASE: militares com vínculo ativo (escopo + filtros) ----
    base_q = (
        database.session.query(M.id.label("m_id"))
        .join(MOF, and_(MOF.militar_id == M.id, MOF.data_fim.is_(None)))
        .filter(M.inativo.is_(False))
    )
    if f["obm_id"]:
        base_q = base_q.filter(MOF.obm_id.in_(_obm_subtree_ids(f["obm_id"])))
    if f["pg_id"]:
        base_q = base_q.filter(M.posto_grad_id == f["pg_id"])
    if not (_is_drh_like() or _is_super_user()):
        user_obms = _user_obm_ids()
        if user_obms:
            base_q = base_q.filter(MOF.obm_id.in_(user_obms))
        else:
            base_q = base_q.filter(literal(False))
    if f["q"]:
        ilike = f"%{f['q']}%"
        base_q = (
            base_q
            .join(PG, PG.id == M.posto_grad_id, isouter=True)
            .join(O, O.id == MOF.obm_id)
            .filter(or_(
                M.nome_completo.ilike(ilike),
                M.matricula.ilike(ilike),
                PG.sigla.ilike(ilike),
                O.sigla.ilike(ilike)
            ))
        )
    base_cte = base_q.distinct().cte("base_militares")

    paf_join = and_(ultimo_paf_sq.c.m_id == base_cte.c.m_id, ultimo_paf_sq.c.rn == 1)
    st = ultimo_paf_sq.c.paf_status
    kpi_row = (
        database.session.query(
            func.count().label("total"),
            func.sum(case((ultimo_paf_sq.c.paf_id.is_(None), 1), else_=0)).label("nao_enviaram"),
            func.sum(case((st.in_(["pendente", "enviado"]), 1), else_=0)).label("pendentes"),
            func.sum(case((st == "aprovado_chefe", 1), else_=0)).label("aprovados_chefe"),
            func.sum(case((st == "aguardando_drh", 1), else_=0)).label("aguardando"),
            func.sum(case((st == "validado_drh", 1), else_=0)).label("validados"),
            func.sum(case((st == "reprovado_chefe", 1), else_=0)).label("reprovados"),
            func.sum(case((st.in_(STATUS_A_HOMOLOGAR), 1), else_=0)).label("a_homologar"),
        )
        .select_from(base_cte)
        .outerjoin(ultimo_paf_sq, paf_join)
    ).one()
    kpi = {k: int(getattr(kpi_row, k) or 0) for k in (
        "total", "nao_enviaram", "pendentes", "aprovados_chefe", "aguardando",
        "validados", "reprovados", "a_homologar")}

    # mês em que o militar ocupa vaga: definido pela DP ou 1ª opção
    mes_vaga = func.coalesce(ultimo_paf_sq.c.mes_definido, ultimo_paf_sq.c.opcao_1)

    cols = [
        M,
        PG.sigla.label("pg_sigla"),
        obm_sq.c.obm_sigla,
        ultimo_paf_sq.c.paf_id,
        ultimo_paf_sq.c.paf_status,
        ultimo_paf_sq.c.opcao_1,
        ultimo_paf_sq.c.opcao_2,
        ultimo_paf_sq.c.opcao_3,
        ultimo_paf_sq.c.mes_definido,
        mes_vaga.label("mes_vaga"),
        ultimo_paf_sq.c.recebido_em,
        ultimo_paf_sq.c.created_at,
        ultimo_paf_sq.c.validado_em,
        ultimo_paf_sq.c.justificativa,
        ultimo_paf_sq.c.observacoes,
    ]
    rows_q = (
        database.session.query(*cols)
        .join(base_cte, base_cte.c.m_id == M.id)
        .outerjoin(obm_sq, obm_sq.c.m_id == M.id)
        .outerjoin(PG, PG.id == M.posto_grad_id)
        .outerjoin(ultimo_paf_sq, and_(ultimo_paf_sq.c.m_id == M.id, ultimo_paf_sq.c.rn == 1))
    )

    status = f["status"]
    if status == "nao_enviou":
        rows_q = rows_q.filter(ultimo_paf_sq.c.paf_id.is_(None))
    elif status == "pendente":
        rows_q = rows_q.filter(st.in_(["pendente", "enviado"]))
    elif status == "a_homologar":
        rows_q = rows_q.filter(st.in_(STATUS_A_HOMOLOGAR))
    elif status != "todos":
        rows_q = rows_q.filter(st == status)

    if f["mes"] and 1 <= f["mes"] <= 12:
        rows_q = rows_q.filter(mes_vaga == f["mes"])

    desc = f["dir"] == "desc"
    chegada = func.coalesce(ultimo_paf_sq.c.recebido_em, ultimo_paf_sq.c.created_at, ultimo_paf_sq.c.updated_at)
    ordem = {
        "chegada": chegada,
        "nome": M.nome_completo,
        "pg": PG.id,
        "obm": obm_sq.c.obm_sigla,
        "status": st,
        "mes": mes_vaga,
        "paf": ultimo_paf_sq.c.paf_id,
    }.get(f["sort"], M.nome_completo)
    ob = ordem.desc().nullslast() if desc else ordem.asc().nullslast()
    rows_q = rows_q.order_by(ob, M.nome_completo.asc())

    return rows_q, kpi


def _anos_paf() -> list[int]:
    anos = {_ano_atual_manaus()}
    anos.update(a for (a,) in database.session.query(NovoPaf.ano_referencia).distinct())
    anos.update(a for (a,) in database.session.query(PafCapacidade.ano).distinct())
    return sorted(anos, reverse=True)


@bp_paf.route("/recebimento", methods=["GET"])
@login_required
def recebimento():
    if not _pode_ver_efetivo():
        flash("Acesso restrito à chefia e à DP.", "danger")
        return redirect(url_for("home"))

    f = _recebimento_filtros()
    page = max(1, request.args.get("page", type=int) or 1)
    per_page = min(200, request.args.get("per_page", type=int) or 50)

    rows_q, kpi = _recebimento_consulta(f)
    total = database.session.execute(
        rows_q.order_by(None).statement.with_only_columns(func.count())).scalar() or 0
    rows_page = rows_q.limit(per_page).offset((page - 1) * per_page).all()
    total_pages = max(ceil(total / per_page), 1)

    is_drh = _is_drh_like() or _is_super_user()
    obms, postos = _cached_obms_postos()

    # filtros ativos (sem page) pra montar links de paginação, cards e Excel
    qs = {k: v for k, v in dict(f, per_page=per_page).items() if v not in (None, "", "todos")}

    return render_template(
        "paf/paf_recebimento.html",
        linhas=rows_page,
        f=f, qs=qs,
        ano=f["ano"], anos=_anos_paf(),
        obms=obms, postos=postos,
        is_drh=is_drh,
        kpi=kpi,
        vagas=_vagas_por_mes(f["ano"]) if is_drh else None,
        meses=MESES_PT,
        status_label=STATUS_LABEL,
        page=page, per_page=per_page, total=total, total_pages=total_pages,
    )


@bp_paf.route("/recebimento/excel", methods=["GET"])
@login_required
def recebimento_excel():
    if not _pode_ver_efetivo():
        flash("Acesso restrito à chefia e à DP.", "danger")
        return redirect(url_for("home"))

    f = _recebimento_filtros()
    rows_q, _kpi = _recebimento_consulta(f)
    ano = f["ano"]

    def dt(v, fmt="%d/%m/%Y"):
        return v.strftime(fmt) if v else ""

    def mes(n):
        return MESES_PT[n] if n and 1 <= n <= 12 else ""

    data = []
    for r in rows_q.all():
        m = r[0]
        st = (r.paf_status or "nao_enviou").lower()
        data.append({
            "PAF": r.paf_id or "",
            "Posto/Graduação": r.pg_sigla or "",
            "Nome": m.nome_completo,
            "Matrícula": m.matricula,
            "OBM": r.obm_sigla or "",
            "Status": STATUS_LABEL.get(st, r.paf_status or ""),
            "1ª opção": mes(r.opcao_1),
            "2ª opção": mes(r.opcao_2),
            "3ª opção": mes(r.opcao_3),
            "Mês da vaga": mes(r.mes_vaga),
            "Mês homologado (DP)": mes(r.mes_definido),
            "Homologado em": dt(r.validado_em, "%d/%m/%Y %H:%M"),
            "Enviado em": dt(r.recebido_em or r.created_at, "%d/%m/%Y %H:%M"),
            "Justificativa do militar": r.justificativa or "",
            "Motivo da reprovação": r.observacoes or "",
        })
    colunas = list(data[0].keys()) if data else ["PAF", "Nome"]
    df = pd.DataFrame(data, columns=colunas)

    vagas = _vagas_por_mes(ano)
    df_vagas = pd.DataFrame([{
        "Mês": MESES_PT[m],
        "Limite": v["limite"] if v["limite"] is not None else "sem limite",
        "Ocupadas": v["ocupadas"],
        "Restantes": v["restantes"] if v["restantes"] is not None else "",
    } for m, v in vagas.items()])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for nome_aba, frame in (("PAF", df), ("Vagas por mês", df_vagas)):
            frame.to_excel(writer, index=False, sheet_name=nome_aba)
            ws = writer.sheets[nome_aba]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(frame), 1), len(frame.columns) - 1)
            for i, col in enumerate(frame.columns):
                maior = max([len(str(col))] + [len(str(x)) for x in frame[col].head(500)])
                ws.set_column(i, i, min(maior + 2, 45))
    output.seek(0)

    registrar_log_download(f"PAF Recebimento {ano}", colunas,
                           {k: v for k, v in f.items() if v not in (None, "", "todos")})

    return send_file(
        output,
        download_name=f"paf_recebimento_{ano}.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp_paf.route("/editar/<int:paf_id>", methods=["GET", "POST"])
@login_required
def editar(paf_id):
    paf = database.session.get(NovoPaf, paf_id)
    if not paf:
        flash("Registro não encontrado.", "danger")
        return redirect(url_for("paf.minhas"))

    # Só o próprio militar (ou SUPER) edita o PAF reprovado
    meu_militar = get_militar_por_user(current_user)
    if not (_is_super_user() or (meu_militar and meu_militar.id == paf.militar_id)):
        flash("Você não pode editar este PAF.", "danger")
        return redirect(url_for("paf.minhas"))

    # Somente quando reprovado
    if (paf.status or "").lower() not in ("reprovado_chefe",):
        flash("Este PAF não está disponível para edição.", "warning")
        return redirect(url_for("paf.minhas"))

    if request.method == "POST":
        # --- Meses (pagamento) ---
        opcao_1_anterior = paf.opcao_1
        try:
            paf.opcao_1 = int(request.form.get("opcao_1"))
            paf.opcao_2 = int(request.form.get("opcao_2"))
            paf.opcao_3 = int(request.form.get("opcao_3"))
        except (TypeError, ValueError):
            flash("Selecione as três opções de pagamento.", "warning")
            return redirect(request.url)

        if len({paf.opcao_1, paf.opcao_2, paf.opcao_3}) < 3:
            database.session.rollback()
            flash("As três opções de pagamento devem ser diferentes.", "warning")
            return redirect(request.url)

        # trocou a 1ª opção (e a DP ainda não definiu mês): precisa ter vaga no novo mês
        if (paf.mes_definido is None and paf.opcao_1 != opcao_1_anterior
                and not _tem_vaga_1a_opcao(paf.ano_referencia, paf.opcao_1, paf.id)):
            database.session.rollback()
            flash("O mês escolhido como 1ª opção não tem mais vagas. Escolha outro.", "warning")
            return redirect(request.url)

        paf.justificativa = (request.form.get("observacoes") or "").strip()

        # Reenvia para a esteira
        paf.status = "pendente"
        paf.aprovado_por_user_id = None
        paf.aprovado_em = None
        paf.validado_por_user_id = None
        paf.validado_em = None

        database.session.commit()
        flash("Alterações salvas e reenviadas para aprovação.", "success")
        return redirect(url_for("paf.minhas"))

    # GET — renderiza
    ctx = dict(
        paf=paf,
        ano=paf.ano_referencia,
        militar=paf.militar,
        posto_grad_sigla=(
            paf.militar.posto_grad.sigla if paf.militar and paf.militar.posto_grad else ""),
        opcao_1=paf.opcao_1,
        opcao_2=paf.opcao_2,
        opcao_3=paf.opcao_3,
        observacoes=paf.justificativa or "",
        motivo_reprovacao=paf.observacoes or "",
        vagas=_vagas_por_mes(paf.ano_referencia, paf.id),
    )
    return render_template("paf/paf_editar.html", **ctx)


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
    pode_ver = is_drh or sou_dono or (_pode_ver_efetivo() and _eh_chefe_do(paf.militar_id))
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


@bp_paf.route("/relatorio-geral", methods=["GET"])
@login_required
def relatorio_geral():
    ano = request.args.get("ano", type=int) or 2026

    q = (
        database.session.query(
            Militar,
            NovoPaf.mes_definido.label("mes_definido"),
            PafFeriasPlano.direito_total_dias,
            PafFeriasPlano.qtd_dias_p1, PafFeriasPlano.inicio_p1, PafFeriasPlano.fim_p1, PafFeriasPlano.mes_usufruto_p1,
            PafFeriasPlano.qtd_dias_p2, PafFeriasPlano.inicio_p2, PafFeriasPlano.fim_p2, PafFeriasPlano.mes_usufruto_p2,
            PafFeriasPlano.qtd_dias_p3, PafFeriasPlano.inicio_p3, PafFeriasPlano.fim_p3, PafFeriasPlano.mes_usufruto_p3,
        )
        .outerjoin(NovoPaf, and_(NovoPaf.militar_id==Militar.id, NovoPaf.ano_referencia==ano))
        .outerjoin(PafFeriasPlano, and_(PafFeriasPlano.militar_id==Militar.id, PafFeriasPlano.ano_referencia==ano))
        .order_by(Militar.nome_completo.asc())
    )

    rows = q.all()

    # índice 0 vazio para permitir acesso direto por número do mês (1..12)
    meses_pt = ["", "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

    return render_template("paf/relatorio_geral.html", ano=ano, rows=rows, meses_pt=meses_pt)


@bp_paf.route("/relatorio-geral-excel")
@login_required
def relatorio_geral_excel():
    ano = request.args.get("ano", type=int) or 2026

    # 🔤 Mapeamento dos meses
    meses_pt = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]

    def fmt_dt(d):
        return d.strftime("%d/%m/%Y") if d else ""

    def nome_mes(num):
        try:
            return meses_pt[num] if num and 1 <= num <= 12 else ""
        except Exception:
            return ""

    def cat(status):
        if status is None:
            return "Não enviou"
        if status.lower() == "pendente":
            return "Pendente (chefia)"
        return "Enviou"

    # 🧮 Query base — agora trazendo também o Posto/Grad
    q = (
        database.session.query(
            Militar.nome_completo,
            Militar.matricula,
            PostoGrad.sigla.label("pg_sigla"),      # 🔥 NOVO: posto/grad
            NovoPaf.mes_definido.label("mes_definido"),
            PafFeriasPlano.direito_total_dias,
            PafFeriasPlano.qtd_dias_p1, PafFeriasPlano.inicio_p1, PafFeriasPlano.fim_p1, PafFeriasPlano.mes_usufruto_p1,
            PafFeriasPlano.qtd_dias_p2, PafFeriasPlano.inicio_p2, PafFeriasPlano.fim_p2, PafFeriasPlano.mes_usufruto_p2,
            PafFeriasPlano.qtd_dias_p3, PafFeriasPlano.inicio_p3, PafFeriasPlano.fim_p3, PafFeriasPlano.mes_usufruto_p3,
            NovoPaf.status.label("status_paf"),
        )
        .outerjoin(NovoPaf, and_(NovoPaf.militar_id == Militar.id,
                                 NovoPaf.ano_referencia == ano))
        .outerjoin(PafFeriasPlano, and_(PafFeriasPlano.militar_id == Militar.id,
                                        PafFeriasPlano.ano_referencia == ano))
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)  # 👈 join no PG
        .filter(Militar.inativo == False)  # ✅ só militares ativos
        .order_by(Militar.nome_completo.asc())
    )

    rows = q.all()

    # 🧾 Construção dos dados
    data = []
    for (nome, matricula, pg_sigla, mes_definido, direito_total_dias,
         q1, i1, f1, mu1,
         q2, i2, f2, mu2,
         q3, i3, f3, mu3,
         status_paf) in rows:

        data.append({
            "Posto/Graduação": pg_sigla or "",      # 🔥 NOVO CAMPO
            "Nome": nome,
            "Matrícula": matricula,
            "Categoria": cat(status_paf),
            "Status bruto": status_paf or "",
            "Direito total (dias)": direito_total_dias or "",
            "1º Período - Qtde": q1 or "",
            "1º Período - Início": fmt_dt(i1),
            "1º Período - Fim": fmt_dt(f1),
            "1º Período - Mês usufruto": nome_mes(mu1),
            "2º Período - Qtde": q2 or "",
            "2º Período - Início": fmt_dt(i2),
            "2º Período - Fim": fmt_dt(f2),
            "2º Período - Mês usufruto": nome_mes(mu2),
            "3º Período - Qtde": q3 or "",
            "3º Período - Início": fmt_dt(i3),
            "3º Período - Fim": fmt_dt(f3),
            "3º Período - Mês usufruto": nome_mes(mu3),
            "Mês validado (mes_definido)": nome_mes(mes_definido),
        })

    df = pd.DataFrame(data)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Geral")
        df[df["Categoria"] == "Não enviou"].to_excel(writer, index=False, sheet_name="Não enviou")
        df[df["Categoria"] == "Pendente (chefia)"].to_excel(writer, index=False, sheet_name="Pendente chefia")
        df[df["Categoria"] == "Enviou"].to_excel(writer, index=False, sheet_name="Enviou")

    output.seek(0)
    return send_file(
        output,
        download_name=f"relatorio_geral_{ano}.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
