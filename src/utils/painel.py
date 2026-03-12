from sqlalchemy import or_
from src.models import Militar, PostoGrad


def _query_militares_ativos_atualizacao():
    return (
        Militar.query
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .filter(
            or_(
                Militar.inativo.is_(False),
                Militar.inativo.is_(None)
            )
        )
    )


def obter_resumo_atualizacao_cadastral():
    query_base = _query_militares_ativos_atualizacao()

    total = query_base.count()

    total_atualizado = query_base.filter(
        Militar.cadastro_atualizado.is_(True)
    ).count()

    total_pendente = query_base.filter(
        or_(
            Militar.cadastro_atualizado.is_(False),
            Militar.cadastro_atualizado.is_(None)
        )
    ).count()

    percentual = round((total_atualizado / total * 100), 1) if total else 0

    return {
        "total": total,
        "total_atualizado": total_atualizado,
        "total_pendente": total_pendente,
        "percentual": percentual,
    }


def obter_militares_atualizacao_cadastral(q="", status=""):
    q = (q or "").strip()
    status = (status or "").strip()

    query = _query_militares_ativos_atualizacao()

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Militar.nome_completo.ilike(like),
                Militar.matricula.ilike(like),
                Militar.nome_guerra.ilike(like),
            )
        )

    if status == "atualizado":
        query = query.filter(Militar.cadastro_atualizado.is_(True))
    elif status == "pendente":
        query = query.filter(
            or_(
                Militar.cadastro_atualizado.is_(False),
                Militar.cadastro_atualizado.is_(None)
            )
        )

    militares = query.order_by(Militar.nome_completo.asc()).all()
    return militares


def serializar_militar_atualizacao(militar):
    return {
        "id": militar.id,
        "nome_completo": militar.nome_completo or "-",
        "nome_guerra": militar.nome_guerra or "",
        "matricula": militar.matricula or "-",
        "posto_grad": militar.posto_grad.sigla if militar.posto_grad else "-",
        "cadastro_atualizado": bool(militar.cadastro_atualizado),
        "status_label": "Atualizado" if militar.cadastro_atualizado else "Pendente",
        "atualizacao_cadastral_em": (
            militar.atualizacao_cadastral_em.strftime("%d/%m/%Y %H:%M")
            if militar.atualizacao_cadastral_em else ""
        ),
    }
