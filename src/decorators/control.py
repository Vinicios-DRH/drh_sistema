# src/control.py
from __future__ import annotations
import re

from functools import wraps
from typing import Iterable, Set
from datetime import date, datetime, time as dtime
import os

from flask import flash, redirect, url_for, request, abort, current_app
from flask_login import current_user
from src.models import Militar, MilitarObmFuncao, ObmGestao, User, UserObmAcesso
from src import database
from sqlalchemy.event import listens_for
from sqlalchemy import and_
from src.security.perms import has_perm

ADMIN_FUNCOES = {"DIRETOR", "CHEFE", "SUPER USER", "DIRETOR DRH", "CHEFE DRH"}


def _upper(x) -> str:
    return (str(x).strip().upper()) if x is not None else ""


def _get_user_ocupacoes() -> Set[str]:
    """
    Retorna um SET de ocupações do usuário (sempre em UPPER),
    cobrindo:
      - current_user.funcao_user (objeto)
      - current_user.user_funcao (backref, pode ser lista)
      - fallbacks (ocupacao/perfil direto no user)
    """
    ocupacoes: Set[str] = set()

    # 1) Relação principal (User.funcao_user)
    fu = getattr(current_user, "funcao_user", None)
    if fu is not None:
        oc = getattr(fu, "ocupacao", None) or getattr(fu, "nome", None)
        if oc:
            ocupacoes.add(_upper(oc))

    # 2) Backref (User.user_funcao) - pode ser lista/coleção
    back = getattr(current_user, "user_funcao", None)
    if back:
        if isinstance(back, (list, tuple, set)):
            for item in back:
                oc = getattr(item, "ocupacao", None) or getattr(
                    item, "nome", None)
                if oc:
                    ocupacoes.add(_upper(oc))
        else:
            oc = getattr(back, "ocupacao", None) or getattr(back, "nome", None)
            if oc:
                ocupacoes.add(_upper(oc))

    # 3) Fallbacks no próprio user (se você usa em algum lugar)
    oc_direct = getattr(current_user, "ocupacao", None) or getattr(
        current_user, "perfil", None)
    if oc_direct:
        ocupacoes.add(_upper(oc_direct))

    # remove vazios
    ocupacoes.discard("")
    return ocupacoes


def checar_ocupacao(*permitidas: str):
    """
    Decorator: permite acesso se o usuário tiver QUALQUER ocupação dentro das permitidas.
    Ex: @checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER')
    """
    permitidas_set = {_upper(p) for p in permitidas if p}

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            # se não tiver autenticado, deixa o login_required cuidar
            if not getattr(current_user, "is_authenticated", False):
                return redirect(url_for("login"))

            user_oc = _get_user_ocupacoes()

            # ✅ regra: basta bater uma
            if user_oc.intersection(permitidas_set):
                return view_func(*args, **kwargs)

            flash("Você não tem permissão para acessar esta página.", "alert-danger")
            # escolha um fallback padrão seguro:
            return redirect(url_for("home"))

        return wrapper
    return decorator


def require_perm(codigo: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_perm(codigo):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def user_obm_ids() -> set[int]:
    """
    Retorna OBMs vinculadas ao user (obm_id_1 / obm_id_2) e, se existir, relação user.obms.
    """
    ids = {getattr(current_user, "obm_id_1", None),
           getattr(current_user, "obm_id_2", None)}
    ids.discard(None)

    obms_rel = getattr(current_user, "obms", None)
    if obms_rel:
        for o in obms_rel:
            oid = getattr(o, "id", None)
            if oid:
                ids.add(oid)
    return ids


def _is_super_user() -> bool:
    # tenta chamar o novo se existir; senão cai no fallback por texto
    fn = globals().get("is_super_user")
    if callable(fn):
        return bool(fn())
    return any("SUPER" in oc for oc in _get_user_ocupacoes())


def exigir_obm(*obm_ids: int):
    """
    Decorator: usuário precisa pertencer a pelo menos uma dessas OBMs (ou ser SUPER).
    """
    obm_ids_set = {int(x) for x in obm_ids if x is not None}

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, "is_authenticated", False):
                return redirect(url_for("login"))

            if _is_super_user():
                return view_func(*args, **kwargs)

            user_ids = user_obm_ids()
            if user_ids.intersection(obm_ids_set):
                return view_func(*args, **kwargs)

            flash("Acesso restrito à sua OBM.", "alert-danger")
            return redirect(url_for("home"))

        return wrapper
    return decorator


# Se tu quiser, preenche isso com IDs de users auditores.
# Por enquanto deixa vazio pra não quebrar o import.
USERS_ANALISE_VINCULO = set()  # type: set[int]

ANO_ATUAL = date.today().year

# -----------------------------------------------------------------------------
# Aliases pro teu "control novo" (mantém compat com imports antigos)
# Se tu já tem is_super_user() e user_obm_ids() definidos acima,
# esses aliases vão funcionar.
# -----------------------------------------------------------------------------


def _user_obm_ids() -> set[int]:
    fn = globals().get("user_obm_ids")
    if callable(fn):
        return set(fn())
    # fallback básico
    ids = {getattr(current_user, "obm_id_1", None),
           getattr(current_user, "obm_id_2", None)}
    ids.discard(None)
    return ids


# -----------------------------------------------------------------------------
# Regras de perfil (ajusta depois conforme tua realidade)
# -----------------------------------------------------------------------------

def _is_auditor_vinculo() -> bool:
    uid = getattr(current_user, "id", None)
    if not uid:
        return False

    # SUPER/DRH etc seguem valendo
    oc = _get_user_ocupacoes()
    if any("SUPER" in x for x in oc):
        return True

    try:
        from src.models import database as db, UserPermissao
        return db.session.query(UserPermissao.id).filter(
            UserPermissao.user_id == uid,
            UserPermissao.codigo == "ANALISE_VINCULO",
            UserPermissao.ativo.is_(True),
        ).first() is not None
    except Exception:
        return False


def _is_drh_like() -> bool:
    if _is_super_user() or _is_auditor_vinculo():
        return True
    oc = _get_user_ocupacoes()
    # qualquer coisa com DRH entra como DRH-like
    return any("DRH" in x for x in oc)


def _is_privilegiado() -> bool:
    if _is_super_user() or _is_auditor_vinculo():
        return True
    oc = _get_user_ocupacoes()
    # Ajusta conforme teus nomes reais:
    priv = {
        "DIRETOR DRH",
        "CHEFE DRH",
        "DRH CHEFE",
        "CHEMG",
        "DIRETOR",
        "CHEFE",
    }
    return bool(oc.intersection(priv))


def _can_analise_vinculo() -> bool:
    # quem pode entrar no recebimento/análise
    if _is_drh_like() or _is_privilegiado():
        return True
    # se você quiser permitir DIRETOR/CHEFE da OBM:
    oc = _get_user_ocupacoes()
    return bool(oc.intersection({"DIRETOR", "CHEFE"}))


def _militar_permitido(militar_id: int) -> bool:
    """
    Regra de escopo por OBM: super/auditor vê tudo.
    Caso contrário, só permite se o militar tiver OBM ativa dentro das OBMs do usuário.
    """
    if _is_super_user() or _is_auditor_vinculo() or _is_drh_like():
        return True

    user_obms = _user_obm_ids()
    if not user_obms:
        return False

    # Importa models dentro pra evitar circular import
    try:
        from src.models import database as db, MilitarObmFuncao
        from sqlalchemy import and_
        rows = (
            db.session.query(MilitarObmFuncao.obm_id)
            .filter(
                MilitarObmFuncao.militar_id == militar_id,
                MilitarObmFuncao.data_fim.is_(None),
            )
            .all()
        )
        mil_obms = {oid for (oid,) in rows if oid}
        return bool(mil_obms.intersection(user_obms))
    except Exception:
        # se der ruim no DB, por segurança nega
        return False


def _can_editar_declaracao(militar_id: int) -> bool:
    # DRH-like e privilegiado pode; chefia só dentro do escopo
    if _is_drh_like() or _is_privilegiado() or _is_super_user():
        return True
    return _militar_permitido(militar_id)


# -----------------------------------------------------------------------------
# Prazo (configurável)
# -----------------------------------------------------------------------------

def _prazo_envio_ate() -> date:
    """
    Tenta ler do config/env:
      - PRAZO_DECLARACAO_MM_DD="03-31"  (fallback: 03-31)
      - PRAZO_DECLARACAO_YYYY_MM_DD="2026-03-31" (se quiser fixar)
    """
    # 1) data completa fixa
    full = os.getenv("PRAZO_DECLARACAO_YYYY_MM_DD") or current_app.config.get(
        "PRAZO_DECLARACAO_YYYY_MM_DD")
    if full:
        try:
            return datetime.strptime(full, "%Y-%m-%d").date()
        except Exception:
            pass

    # 2) mês-dia (usa ano atual)
    md = os.getenv("PRAZO_DECLARACAO_MM_DD") or current_app.config.get(
        "PRAZO_DECLARACAO_MM_DD") or "03-31"
    try:
        mm, dd = md.split("-")
        return date(date.today().year, int(mm), int(dd))
    except Exception:
        # fallback seguro
        return date(date.today().year, 3, 31)


def _prazo_fechado() -> bool:
    return date.today() > _prazo_envio_ate()


def _usuario_ja_tem_declaracao(user_id: int, ano: int) -> bool:
    """
    Depende do teu modelo: pelo teu routes_acumulo, Declaração é por militar_id.
    Aqui a gente tenta inferir pelo current_user.militar_id quando fizer sentido.
    """
    try:
        from src.models import database as db, DeclaracaoAcumulo
        mid = getattr(current_user, "militar_id", None)
        if not mid:
            return False
        return db.session.query(DeclaracaoAcumulo.id).filter(
            DeclaracaoAcumulo.militar_id == mid,
            DeclaracaoAcumulo.ano_referencia == ano
        ).first() is not None
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Parsers
# -----------------------------------------------------------------------------

def _parse_date(s) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def _parse_time(s) -> dtime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        hh, mm = s.split(":")
        return dtime(int(hh), int(mm))
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Decorator de permissão usado nas rotas
# -----------------------------------------------------------------------------

def require_analise_vinculo(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not getattr(current_user, "is_authenticated", False):
            return redirect(url_for("login"))

        if _can_analise_vinculo():
            return view_func(*args, **kwargs)

        flash("Você não tem permissão para acessar esta página.", "alert-danger")
        return redirect(url_for("home"))
    return wrapper


def obms_base_do_usuario(user) -> Set[int]:
    """
    OBMs "base" do usuário:
      - se tiver militar_id: OBMs ativas do militar (MilitarObmFuncao)
      - obm_id_1 / obm_id_2 (compat)
      - delegadas (UserObmAcesso ativo)
    """
    ids: Set[int] = set()

    # 1) do militar (se existir)
    mid = getattr(user, "militar_id", None)
    if mid:
        rows = (
            database.session.query(MilitarObmFuncao.obm_id)
            .filter(
                MilitarObmFuncao.militar_id == mid,
                MilitarObmFuncao.data_fim.is_(None)
            )
            .all()
        )
        ids.update([oid for (oid,) in rows if oid])

    # 2) compat: colunas do user
    for oid in (getattr(user, "obm_id_1", None), getattr(user, "obm_id_2", None)):
        if oid:
            ids.add(int(oid))

    # 3) delegadas por painel
    delegadas = (
        database.session.query(UserObmAcesso.obm_id)
        .filter(
            UserObmAcesso.user_id == user.id,
            UserObmAcesso.ativo.is_(True)
        )
        .all()
    )
    ids.update([oid for (oid,) in delegadas if oid])

    return ids


def obms_geridas_por(obm_ids: Iterable[int]) -> Set[int]:
    """
    Retorna TODAS as OBMs geridas (transitivas) pelas obms gestoras informadas.
    Ex: A gere B e C; B gere D -> retorna {B,C,D} (além de A se você unir).
    """
    base = {int(x) for x in (obm_ids or []) if x is not None}
    if not base:
        return set()

    visited = set()
    frontier = set(base)

    while frontier:
        rows = (
            database.session.query(ObmGestao.obm_gerida_id)
            .filter(
                ObmGestao.obm_gestora_id.in_(list(frontier)),
                ObmGestao.ativo.is_(True)
            )
            .all()
        )
        next_ids = {oid for (oid,) in rows if oid}
        next_ids -= visited
        visited |= next_ids
        frontier = next_ids

    return visited


def obms_permitidas_para_usuario(user) -> Set[int]:
    """
    ✅ REGRA NOVA:
    - Base do usuário (suas OBMs e delegações)
    - + OBMs geridas (hierarquia ObmGestao) por qualquer OBM da base
    - SUPER USER vê tudo (deixa as rotas tratarem se quiser)
    """
    base = obms_base_do_usuario(user)
    geridas = obms_geridas_por(base)
    return base.union(geridas)


def militar_esta_no_escopo(militar_id: int, permitidas: Set[int]) -> bool:
    if not permitidas:
        return False
    rows = (
        database.session.query(MilitarObmFuncao.obm_id)
        .filter(
            MilitarObmFuncao.militar_id == militar_id,
            MilitarObmFuncao.data_fim.is_(None)
        )
        .all()
    )
    mil_obms = {oid for (oid,) in rows if oid}
    return bool(mil_obms.intersection(permitidas))


def bloquear_obm_fora_do_escopo(obm_id: int):
    if getattr(current_user, "funcao_user_id", None) == 6:  # super
        return None
    permitidas = obms_permitidas_para_usuario(current_user)
    if obm_id not in permitidas:
        return "<div class='alert alert-danger'>Sem permissão para esta OBM.</div>", 403
    return None


def cpf_norm(cpf: str) -> str:
    return re.sub(r"\D", "", cpf or "")


def obms_ativas_do_militar(militar_id: int) -> list[int]:
    rows = (
        database.session.query(MilitarObmFuncao.obm_id)
        .filter(
            MilitarObmFuncao.militar_id == militar_id,
            MilitarObmFuncao.data_fim.is_(None)
        )
        .all()
    )
    return [oid for (oid,) in rows if oid]


def atualizar_user_admin_por_militar(militar_id: int):
    mil = Militar.query.get(militar_id)
    if not mil:
        return

    # acha o perfil ADMIN desse militar
    u_admin = (
        database.session.query(User)
        .filter(
            User.militar_id == militar_id,
            User.tipo_perfil == "ADMIN"
        )
        .first()
    )
    if not u_admin:
        return

    # atualiza nome/email/cpf_norm (se quiser)
    u_admin.nome = mil.nome_completo
    u_admin.cpf_norm = cpf_norm(mil.cpf)

    # se você insistir em manter obm_id_1/2 por compat:
    obms = obms_ativas_do_militar(militar_id)
    u_admin.obm_id_1 = obms[0] if len(obms) > 0 else None
    u_admin.obm_id_2 = obms[1] if len(obms) > 1 else None

    database.session.add(u_admin)


@listens_for(MilitarObmFuncao, "after_insert")
def _sync_user_admin_insert(mapper, connection, target):
    atualizar_user_admin_por_militar(target.militar_id)


@listens_for(MilitarObmFuncao, "after_update")
def _sync_user_admin_update(mapper, connection, target):
    atualizar_user_admin_por_militar(target.militar_id)


# Essa função vai ser chamada lá na rota de atualização do militar (/exibir-militar/<id>)
def sync_user_admin_obms_from_militar(militar_id: int):
    """
    Espelha OBM1/OBM2 vigentes do MilitarObmFuncao (tipo 1/2, data_fim None)
    para o perfil ADMIN do User (tipo_perfil='ADMIN') daquele militar.

    Não mexe em histórico. Só lê os registros ativos.
    """
    admin = (
        User.query
        .filter(User.militar_id == militar_id, User.tipo_perfil == "ADMIN")
        .first()
    )
    if not admin:
        return  # não existe perfil admin pra esse militar

    # pega os ativos
    t1 = (
        MilitarObmFuncao.query
        .filter(
            MilitarObmFuncao.militar_id == militar_id,
            MilitarObmFuncao.tipo == 1,
            MilitarObmFuncao.data_fim.is_(None)
        )
        .order_by(MilitarObmFuncao.id.desc())
        .first()
    )

    t2 = (
        MilitarObmFuncao.query
        .filter(
            MilitarObmFuncao.militar_id == militar_id,
            MilitarObmFuncao.tipo == 2,
            MilitarObmFuncao.data_fim.is_(None)
        )
        .order_by(MilitarObmFuncao.id.desc())
        .first()
    )

    admin.obm_id_1 = t1.obm_id if t1 else None
    admin.obm_id_2 = t2.obm_id if t2 else None

    # opcional (recomendo pelo menos nome)
    # militar = Militar.query.get(militar_id)
    # admin.nome = militar.nome_completo
    # admin.email = militar.email
