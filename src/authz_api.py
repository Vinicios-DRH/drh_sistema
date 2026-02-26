# src/authz_api.py
from src.models import UserPermissao
from src import database as db


def user_has_perm(user_id: int, codigo: str) -> bool:
    codigo = (codigo or "").strip().upper()
    if not user_id or not codigo:
        return False

    row = (db.session.query(UserPermissao.ativo)
           .filter(UserPermissao.user_id == user_id,
                   UserPermissao.codigo == codigo)
           .scalar())
    return bool(row)
