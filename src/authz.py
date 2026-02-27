# src/authz.py  (ou control.py, mas prefiro separar autorização)
from flask_login import current_user
from src.models import UserPermissao
from src import database as db


def has_perm(codigo: str) -> bool:
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return False

    # super "real" sempre vence
    if getattr(current_user, "funcao_user_id", None) == 6:
        return True

    # override tipo super via painel
    if codigo != "SYS_SUPER":
        # se ele tiver SYS_SUPER, ele vira super pra tudo
        if _has_perm_db("SYS_SUPER"):
            return True

    return _has_perm_db(codigo)


def _has_perm_db(codigo: str) -> bool:
    uid = getattr(current_user, "id", None)
    if not uid:
        return False
    row = (db.session.query(UserPermissao.ativo)
           .filter(UserPermissao.user_id == uid,
                   UserPermissao.codigo == codigo)
           .scalar())
    return bool(row)


def is_super() -> bool:
    return getattr(current_user, "funcao_user_id", None) == 6


def is_super_or_perm(codigo: str) -> bool:
    # super real sempre passa
    return is_super() or has_perm(codigo)


def can_ferias_bypass_janela() -> bool:
    return is_super() or has_perm("FERIAS_EDITAR_FORA_JANELA") or has_perm("FERIAS_SUPER")


OBM_BM3_ID = 10
FUNCOES_CHEFE_DIRETOR = {1, 2}  # DIRETOR=1, CHEFE=2


def can_see_taf_panel() -> bool:
    # SUPER sempre
    if is_super():
        return True

    # Liberação explícita via painel admin (permissão)
    if has_perm("TAF_PAINEL_READ") or has_perm("NAV_TAF_PAINEL") or has_perm("NAV_TAF"):
        return True

    # Padrão BM-3: CHEFE/DIRETOR lotados na OBM 10
    funcao_id = int(getattr(current_user, "funcao_user_id", 0) or 0)
    obm1 = int(getattr(current_user, "obm_id_1", 0) or 0)
    if funcao_id in FUNCOES_CHEFE_DIRETOR and obm1 == OBM_BM3_ID:
        return True

    return False
