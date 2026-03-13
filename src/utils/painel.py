from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload

from src.models import Militar, PostoGrad, MilitarObmFuncao, Obm
from src.utils.cadastro_status import get_campos_pendentes_cadastro, cadastro_esta_completo


def _query_militares_ativos_atualizacao():
    return (
        Militar.query
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .outerjoin(Obm, Obm.id == MilitarObmFuncao.obm_id)
        .filter(
            and_(
                or_(
                    Militar.inativo.is_(False),
                    Militar.inativo.is_(None)
                ),
                or_(
                    Militar.posto_grad_id.is_(None),
                    Militar.posto_grad_id != 15
                )
            )
        )
    )


def obter_resumo_atualizacao_cadastral(obm_id=None, posto_grad_id=None):
    query_base = _query_militares_ativos_atualizacao()

    if obm_id:
        query_base = query_base.filter(MilitarObmFuncao.obm_id == obm_id)

    if posto_grad_id:
        query_base = query_base.filter(Militar.posto_grad_id == posto_grad_id)

    total = query_base.with_entities(Militar.id).distinct().count()

    total_atualizado = (
        query_base
        .filter(Militar.cadastro_atualizado.is_(True))
        .with_entities(Militar.id)
        .distinct()
        .count()
    )

    total_pendente = (
        query_base
        .filter(
            or_(
                Militar.cadastro_atualizado.is_(False),
                Militar.cadastro_atualizado.is_(None)
            )
        )
        .with_entities(Militar.id)
        .distinct()
        .count()
    )

    percentual = round((total_atualizado / total * 100), 1) if total else 0

    return {
        "total": total,
        "total_atualizado": total_atualizado,
        "total_pendente": total_pendente,
        "percentual": percentual,
    }


def obter_militares_atualizacao_cadastral(q="", status="", obm_id=None, posto_grad_id=None):
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

    if obm_id:
        query = query.filter(MilitarObmFuncao.obm_id == obm_id)

    if posto_grad_id:
        query = query.filter(Militar.posto_grad_id == posto_grad_id)

    militar_ids = [
        row[0]
        for row in query.with_entities(Militar.id).distinct().all()
    ]

    if not militar_ids:
        return []

    militares = (
        Militar.query
        .options(
            joinedload(Militar.posto_grad),
            joinedload(Militar.obm_funcoes).joinedload(MilitarObmFuncao.obm)
        )
        .filter(Militar.id.in_(militar_ids))
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    return militares


def listar_obms_atualizacao():
    return (
        Obm.query
        .order_by(Obm.sigla.asc())
        .all()
    )


def listar_postos_grad_atualizacao():
    return (
        PostoGrad.query
        .filter(PostoGrad.id != 15)
        .order_by(PostoGrad.sigla.asc())
        .all()
    )


def _obter_obm_principal(militar):
    if not militar.obm_funcoes:
        return "-"
    for item in militar.obm_funcoes:
        if item.obm:
            return item.obm.sigla or item.obm.obm or item.obm.nome or "-"
    return "-"


def serializar_militar_atualizacao(militar):
    return {
        "id": militar.id,
        "nome_completo": militar.nome_completo or "-",
        "nome_guerra": militar.nome_guerra or "",
        "matricula": militar.matricula or "-",
        "posto_grad": militar.posto_grad.sigla if militar.posto_grad else "-",
        "obm": _obter_obm_principal(militar),
        "cadastro_atualizado": bool(militar.cadastro_atualizado),
        "status_label": "Atualizado" if militar.cadastro_atualizado else "Pendente",
        "atualizacao_cadastral_em": (
            militar.atualizacao_cadastral_em.strftime("%d/%m/%Y %H:%M")
            if militar.atualizacao_cadastral_em else ""
        ),
    }


def obter_detalhes_militar_atualizacao(militar_id):
    militar = (
        Militar.query
        .options(
            joinedload(Militar.posto_grad),
            joinedload(Militar.obm_funcoes).joinedload(MilitarObmFuncao.obm)
        )
        .filter(Militar.id == militar_id)
        .first()
    )

    if not militar:
        return None

    campos_pendentes = get_campos_pendentes_cadastro(militar)
    cadastro_completo = cadastro_esta_completo(militar)

    preenchidos = []
    pendentes = []

    mapa_campos = {
        "nome_completo": "Nome completo",
        "nome_guerra": "Nome de guerra",
        "cpf": "CPF",
        "rg": "RG",
        "matricula": "Matrícula",
        "nome_pai": "Nome do pai",
        "nome_mae": "Nome da mãe",
        "data_nascimento": "Data de nascimento",
        "sexo": "Sexo",
        "estado_civil": "Estado civil",
        "endereco": "Endereço",
        "cidade": "Cidade",
        "estado": "Estado",
        "cep": "CEP",
        "celular": "Celular",
        "email": "E-mail",
        "grau_instrucao": "Grau de instrução",
        "tipo_sanguineo": "Tipo sanguíneo",
        "cor_olhos": "Cor dos olhos",
        "cor_cabelos": "Cor dos cabelos",
        "altura": "Altura",
        "numero_sapato": "Número do sapato",
        "medida_calca": "Medida da calça",
        "medida_camisa": "Medida da camisa",
        "medida_cabeca": "Medida da cabeça",
    }

    pendentes_set = set(campos_pendentes or [])

    for campo, label in mapa_campos.items():
        if campo in pendentes_set:
            pendentes.append(label)
        else:
            preenchidos.append(label)

    return {
        "id": militar.id,
        "nome_completo": militar.nome_completo or "-",
        "nome_guerra": militar.nome_guerra or "",
        "matricula": militar.matricula or "-",
        "posto_grad": militar.posto_grad.sigla if militar.posto_grad else "-",
        "obm": _obter_obm_principal(militar),
        "cadastro_atualizado": bool(militar.cadastro_atualizado),
        "cadastro_completo": bool(cadastro_completo),
        "preenchidos": preenchidos,
        "pendentes": pendentes,
        "atualizacao_cadastral_em": (
            militar.atualizacao_cadastral_em.strftime("%d/%m/%Y %H:%M")
            if militar.atualizacao_cadastral_em else ""
        ),
    }
