from sqlalchemy import func, case, and_

from src.models import Paf, Militar
from src import database


def get_militares_pendentes_ferias():
    total_dias_usufruidos = (
        func.coalesce(Paf.qtd_dias_primeiro_periodo, 0) +
        func.coalesce(Paf.qtd_dias_segundo_periodo, 0) +
        func.coalesce(Paf.qtd_dias_terceiro_periodo, 0)
    )

    direito_total_dias = case(
        (
            and_(Militar.obm_id == 48, Militar.especialidade_id == 12),
            40
        ),
        else_=30
    ).label("direito_total_dias")

    base_query = (
        database.session.query(
            Militar,
            func.coalesce(func.sum(total_dias_usufruidos),
                          0).label("dias_usufruidos"),
            direito_total_dias
        )
        .outerjoin(Paf, Paf.militar_id == Militar.id)
        .group_by(Militar.id, direito_total_dias)
    )

    # Quem falta tirar (não completou o direito)
    pendentes = (
        base_query
        .having(func.coalesce(func.sum(total_dias_usufruidos), 0) < direito_total_dias)
        .all()
    )

    # Quem não tirou nenhum dia
    nenhum_dia = [
        row for row in pendentes
        if row.dias_usufruidos == 0
    ]

    # Quem tirou alguma coisa mas não completou
    parcial = [
        row for row in pendentes
        if 0 < row.dias_usufruidos < row.direito_total_dias
    ]

    return pendentes, nenhum_dia, parcial
