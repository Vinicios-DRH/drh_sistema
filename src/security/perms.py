from flask_login import current_user
from src import database as db
from src.models import UserPermissao

# defaults por função (do seu FuncaoUser). Ajuste como você quiser.
ROLE_DEFAULTS = {
    "DRH": {"MILITAR_READ", "MILITAR_CREATE", "MILITAR_UPDATE", "MILITAR_DELETE",
            "FERIAS_READ", "FERIAS_CREATE", "FERIAS_UPDATE", "FERIAS_DELETE"},
    "MAPA DA FORÇA": {"MILITAR_READ", "MILITAR_UPDATE"},
    "SUPER USER": {"*"},
    "DIRETOR DRH": {"*"},
    "CHEFE DRH": {"*"},
}


def _role_name():
    fu = getattr(current_user, "funcao_user", None)
    if not fu:
        return ""
    # ajuste o atributo conforme seu model FuncaoUser
    nome = getattr(fu, "funcao", None) or getattr(
        fu, "nome", None) or getattr(fu, "ocupacao", None) or ""
    return str(nome).strip().upper()


def has_perm(codigo: str) -> bool:
    if not current_user.is_authenticated:
        return False

    codigo = (codigo or "").strip().upper()

    # 1) SUPER/chefias com wildcard
    role = _role_name()
    defaults = ROLE_DEFAULTS.get(role, set())
    if "*" in defaults:
        return True

    # 2) Se existir override explícito (ativo True/False), ele manda
    row = (db.session.query(UserPermissao)
           .filter(UserPermissao.user_id == current_user.id,
                   UserPermissao.codigo == codigo)
           .first())
    if row is not None:
        return bool(row.ativo)

    # 3) Senão, cai no padrão por função (DRH etc.)
    return codigo in defaults
