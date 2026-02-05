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
