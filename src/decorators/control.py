from functools import wraps
from flask import abort, flash, redirect, url_for, session
from flask_login import current_user
from src.formatar_cpf import get_militar_por_user
from src import app
from datetime import datetime, date, time
from src.models import DeclaracaoAcumulo, database as db, Militar, Obm, MilitarObmFuncao
import re


@app.before_request
def inject_pg_id_into_session():
    if not current_user.is_authenticated:
        session.pop('pg_id', None)
        return
    if 'pg_id' in session:
        return
    try:
        # importa aqui pra evitar import circular
        mil = get_militar_por_user(current_user)
        session['pg_id'] = getattr(mil, 'posto_grad_id', None)
    except Exception:
        session['pg_id'] = None


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


# helpers_perm.py (ou onde você já mantém permissões)

def _user_obm_ids() -> list[int]:
    """Coleta os OBM ids do usuário (campos diretos e/ou relação many-to-many)."""
    ids = set()
    for attr in ("obm_id_1", "obm_id_2"):
        v = getattr(current_user, attr, None)
        if v:
            ids.add(v)
    # se tiver relação many-to-many, aproveita
    obms_rel = getattr(current_user, "obms", None)
    if obms_rel:
        try:
            for o in obms_rel:
                oid = getattr(o, "id", None)
                if oid:
                    ids.add(oid)
        except Exception:
            pass
    return list(ids)


def _is_drh_like() -> bool:
    """
    DRH-like = SUPER USER OU (é DIRETOR pela FuncaoUser/ocupacao e tem
    pelo menos uma OBM cuja sigla contenha 'DRH').
    """
    if _is_super_user():
        return True

    # 1) Descobrir ocupação via FuncaoUser (pode ser escalar ou lista)
    ocup = None
    try:
        fu = getattr(current_user, "user_funcao", None)
        # se a relação foi criada com uselist=True (lista)
        if isinstance(fu, (list, tuple)):
            for f in fu:
                o = getattr(f, "ocupacao", None)
                if o:
                    ocup = o
                    break
        elif fu is not None:
            ocup = getattr(fu, "ocupacao", None)
    except Exception:
        pass

    # fallback para algum campo no próprio User, se existir
    if not ocup:
        ocup = getattr(current_user, "ocupacao", None)

    is_diretor = "DIRETOR" in ((ocup or "").upper())
    if not is_diretor:
        return False

    # 2) Verificar se ele tem alguma OBM com sigla 'DRH'
    obm_ids = _user_obm_ids()
    if not obm_ids:
        return False

    # tenta primeiro via objetos já carregados para evitar roundtrip
    obms_rel = getattr(current_user, "obms", None)
    if obms_rel:
        try:
            for o in obms_rel:
                sigla = (getattr(o, "sigla", "") or "").upper()
                if "DRH" in sigla:
                    return True
        except Exception:
            pass

    # fallback: consulta rápida
    tem_drh = (
        db.session.query(Obm.id)
        .filter(Obm.id.in_(obm_ids), Obm.sigla.ilike("%DRH%"))
        .first()
        is not None
    )
    return tem_drh


def _to_hhmm(s: str) -> str:
    """Normaliza 'HH:MM' ou 'HH:MM:SS' para 'HH:MM'."""
    if not s:
        return ""
    s = str(s)
    if ":" not in s:
        return s
    parts = s.split(":")
    # garante dois dígitos
    h = parts[0].zfill(2)
    m = (parts[1] if len(parts) > 1 else "00").zfill(2)
    return f"{h}:{m}"


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _ymd(s: str) -> str:
    """Aceita 'YYYY-MM-DD' ou 'DD/MM/YYYY' e devolve 'YYYY-MM-DD'.
       Se já estiver OK, devolve como veio."""
    if not s:
        return ""
    s = s.strip()
    try:
        # já no formato correto?
        if "-" in s and len(s.split("-")) == 3:
            datetime.strptime(s, "%Y-%m-%d")
            return s
    except Exception:
        pass
    # tenta converter de DD/MM/YYYY
    try:
        return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return s


def _is_privilegiado() -> bool:
    # SUPER USER sempre é privilegiado
    if _is_super_user():
        return True

    # Tenta ler via relação (pode ser lista ou objeto único)
    ocup = None
    try:
        fu = getattr(current_user, "user_funcao", None)
        if isinstance(fu, (list, tuple)):
            for f in fu:
                o = getattr(f, "ocupacao", None)
                if o:
                    ocup = o
                    break
        elif fu is not None:
            ocup = getattr(fu, "ocupacao", None)
    except Exception:
        pass

    # Fallback: campo simples no User
    if not ocup:
        ocup = getattr(current_user, "ocupacao", None)

    up = (ocup or "").upper()
    # marque aqui todos os cargos “VIP” que devem ver TUDO
    return ("SUPER USER" in up) or ("DIRETOR DRH" in up)


ANO_ATUAL = date.today().year


def _prazo_envio_ate() -> date:
    # Prazo final fixo (inclusive) para envio em 2025
    return date(2025, 9, 22)


def _prazo_fechado() -> bool:
    return date.today() > _prazo_envio_ate()


# Decorador para verificar a ocupação do usuário


def checar_ocupacao(*ocupacoes_permitidas):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verifica se o usuário tem uma ocupação associada
            if not current_user.user_funcao or current_user.user_funcao.ocupacao not in ocupacoes_permitidas:
                flash('Acesso negado', 'alert-danger')
                return redirect(url_for('acesso_negado'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# >>> Whitelist de usuários que podem analisar (ex: id=394)
USERS_ANALISE_VINCULO = {394}


def _is_auditor_vinculo() -> bool:
    try:
        return getattr(current_user, "id", None) in USERS_ANALISE_VINCULO
    except Exception:
        return False


def _can_analise_vinculo() -> bool:
    """Permite análise de declarações por perfil OU por whitelist de user.id."""
    try:
        if getattr(current_user, "id", None) in USERS_ANALISE_VINCULO:
            return True
    except Exception:
        pass

    # Mantém sua regra atual (DRH-like, super, etc.)
    # Ajuste aqui se quiser ser mais/menos permissivo.
    if _is_super_user():
        return True
    if _is_drh_like():
        return True

    # Se quiser incluir CHEFE/DIRETOR fora do DRH, deixe:
    ocup = _ocupacao_nome()  # já existe no seu arquivo
    if ocup in {"CHEFE", "DIRETOR"}:
        return True

    return False


def require_analise_vinculo(fn):
    """Decorator para rotas de recebimento/análise."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _can_analise_vinculo():
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def _usuario_ja_tem_declaracao(user_id: int, ano: int) -> bool:
    return db.session.query(DeclaracaoAcumulo.id)\
        .filter(DeclaracaoAcumulo.usuario_id == user_id,
                DeclaracaoAcumulo.ano_referencia == ano).first() is not None
