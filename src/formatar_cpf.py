from src.decorators.utils_cpf import so_digitos
from src.models import Militar, TarefaAtualizacaoCadete
from sqlalchemy import func, cast, String


def formatar_cpf(cpf):
    # Transforma 12345678900 em 123.456.789-00
    cpf = ''.join(filter(str.isdigit, cpf))
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def get_militar_por_user(user):
    """Busca Militar pelo CPF do User ignorando pontos/traços e tipo numérico."""
    if not user or not getattr(user, "cpf", None):
        return None

    cpf_num = so_digitos(user.cpf)
    if not cpf_num:
        return None

    # Compara a versão "só dígitos" do campo Militar.cpf
    # - cast para texto: cobre caso Militar.cpf seja numeric
    # - regexp_replace: remove qualquer coisa que não for dígito no BD
    return (Militar.query
            .filter(func.regexp_replace(cast(Militar.cpf, String), r'[^0-9]', '', 'g') == cpf_num)
            .first())


def is_cadete(user):
    mil = get_militar_por_user(user)
    return bool(mil and mil.posto_grad_id == 7)


def cadete_pode_editar_militar(user, militar_id):
    # Só se existir tarefa pendente/em edição para ele.
    t = TarefaAtualizacaoCadete.query.filter_by(
        cadete_user_id=user.id, militar_id=militar_id
    ).filter(TarefaAtualizacaoCadete.status.in_(["PENDENTE", "EM_EDICAO"])).first()
    return t is not None


def cadete_restantes(user):
    return TarefaAtualizacaoCadete.query.filter_by(
        cadete_user_id=user.id, status="PENDENTE"
    ).count()
