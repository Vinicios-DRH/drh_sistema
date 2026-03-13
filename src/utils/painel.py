from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only, selectinload

from src.models import Militar, PostoGrad, MilitarObmFuncao, Obm
from src.utils.cadastro_status import get_campos_pendentes_cadastro


def _query_militares_ativos_atualizacao():
    return (
        Militar.query
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
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


def _aplicar_filtros(query, q="", status="", posto_grad_id=None):
    q = (q or "").strip()
    status = (status or "").strip()

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

    if posto_grad_id:
        query = query.filter(Militar.posto_grad_id == posto_grad_id)

    return query


def _obter_obm_recente_obj(militar):
    if not militar or not militar.obm_funcoes:
        return None

    itens = [item for item in militar.obm_funcoes if item and item.obm]

    if not itens:
        return None

    def sort_key(item):
        # vínculo atual primeiro (data_fim = None)
        data_fim_none = item.data_fim is None
        data_fim = item.data_fim
        data_criacao = item.data_criacao
        return (
            1 if data_fim_none else 0,
            data_fim or data_criacao,
            data_criacao,
            item.id or 0,
        )

    itens.sort(key=sort_key, reverse=True)
    return itens[0].obm


def _obter_obm_principal(militar):
    obm = _obter_obm_recente_obj(militar)
    if not obm:
        return "-"
    return obm.sigla or getattr(obm, "obm", None) or getattr(obm, "nome", None) or "-"


def _militar_pertence_obm_recente(militar, obm_id):
    if not obm_id:
        return True

    obm = _obter_obm_recente_obj(militar)
    return bool(obm and obm.id == obm_id)


def _base_load_lista():
    return (
        load_only(
            Militar.id,
            Militar.nome_completo,
            Militar.nome_guerra,
            Militar.matricula,
            Militar.posto_grad_id,
            Militar.atualizacao_cadastral_em,
            Militar.cadastro_atualizado,
        ),
        selectinload(Militar.posto_grad).load_only(
            PostoGrad.id,
            PostoGrad.sigla,
        ),
        selectinload(Militar.obm_funcoes)
        .load_only(
            MilitarObmFuncao.id,
            MilitarObmFuncao.militar_id,
            MilitarObmFuncao.obm_id,
            MilitarObmFuncao.data_criacao,
            MilitarObmFuncao.data_fim,
        )
        .selectinload(MilitarObmFuncao.obm)
        .load_only(
            Obm.id,
            Obm.sigla,
        )
    )


def _base_load_detalhe():
    return (
        load_only(
            Militar.id,
            Militar.nome_completo,
            Militar.nome_guerra,
            Militar.matricula,
            Militar.posto_grad_id,
            Militar.atualizacao_cadastral_em,
            Militar.cadastro_atualizado,
            Militar.nome_pai,
            Militar.nome_mae,
            Militar.data_nascimento,
            Militar.sexo,
            Militar.estado_civil,
            Militar.endereco,
            Militar.cidade,
            Militar.estado,
            Militar.cep,
            Militar.celular,
            Militar.email,
            Militar.grau_instrucao,
            Militar.tipo_sanguineo,
            Militar.cor_olhos,
            Militar.cor_cabelos,
            Militar.altura,
            Militar.numero_sapato,
            Militar.medida_calca,
            Militar.medida_camisa,
            Militar.medida_cabeca,
            Militar.cpf,
            Militar.rg,
        ),
        selectinload(Militar.posto_grad).load_only(
            PostoGrad.id,
            PostoGrad.sigla,
        ),
        selectinload(Militar.obm_funcoes)
        .load_only(
            MilitarObmFuncao.id,
            MilitarObmFuncao.militar_id,
            MilitarObmFuncao.obm_id,
            MilitarObmFuncao.data_criacao,
            MilitarObmFuncao.data_fim,
        )
        .selectinload(MilitarObmFuncao.obm)
        .load_only(
            Obm.id,
            Obm.sigla,
        )
    )


def obter_resumo_atualizacao_cadastral(obm_id=None, posto_grad_id=None):
    query = _aplicar_filtros(
        _query_militares_ativos_atualizacao(),
        q="",
        status="",
        posto_grad_id=posto_grad_id,
    )

    militares = (
        query
        .options(*_base_load_lista())
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    if obm_id:
        militares = [
            m for m in militares if _militar_pertence_obm_recente(m, obm_id)]

    total = len(militares)
    total_atualizado = sum(1 for m in militares if bool(m.cadastro_atualizado))
    total_pendente = total - total_atualizado
    percentual = round((total_atualizado / total * 100), 1) if total else 0

    return {
        "total": total,
        "total_atualizado": total_atualizado,
        "total_pendente": total_pendente,
        "percentual": percentual,
    }


def obter_militares_atualizacao_cadastral(q="", status="", obm_id=None, posto_grad_id=None, page=1, per_page=50):
    query = _aplicar_filtros(
        _query_militares_ativos_atualizacao(),
        q=q,
        status=status,
        posto_grad_id=posto_grad_id,
    )

    militares = (
        query
        .options(*_base_load_lista())
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    if obm_id:
        militares = [
            m for m in militares if _militar_pertence_obm_recente(m, obm_id)]

    total_filtrado = len(militares)

    inicio = (page - 1) * per_page
    fim = inicio + per_page
    militares_pagina = militares[inicio:fim]

    return militares_pagina, total_filtrado


def listar_obms_atualizacao():
    return (
        Obm.query
        .options(load_only(Obm.id, Obm.sigla))
        .order_by(Obm.sigla.asc())
        .all()
    )


def listar_postos_grad_atualizacao():
    return (
        PostoGrad.query
        .options(load_only(PostoGrad.id, PostoGrad.sigla))
        .filter(PostoGrad.id != 15)
        .order_by(PostoGrad.sigla.asc())
        .all()
    )


def serializar_militar_atualizacao(militar):
    cadastro_ok = bool(militar.cadastro_atualizado)

    return {
        "id": militar.id,
        "nome_completo": militar.nome_completo or "-",
        "nome_guerra": militar.nome_guerra or "",
        "matricula": militar.matricula or "-",
        "posto_grad": militar.posto_grad.sigla if militar.posto_grad else "-",
        "obm": _obter_obm_principal(militar),
        "cadastro_atualizado": cadastro_ok,
        "status_label": "Atualizado" if cadastro_ok else "Pendente",
        "atualizacao_cadastral_em": (
            militar.atualizacao_cadastral_em.strftime("%d/%m/%Y %H:%M")
            if militar.atualizacao_cadastral_em else ""
        ),
    }


def obter_detalhes_militar_atualizacao(militar_id):
    militar = (
        Militar.query
        .options(*_base_load_detalhe())
        .filter(Militar.id == militar_id)
        .first()
    )

    if not militar:
        return None

    campos_pendentes = get_campos_pendentes_cadastro(militar) or []
    cadastro_completo = len(campos_pendentes) == 0

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

    pendentes_set = set(campos_pendentes)

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
        "cadastro_atualizado": cadastro_completo,
        "cadastro_completo": cadastro_completo,
        "preenchidos": preenchidos,
        "pendentes": pendentes,
        "atualizacao_cadastral_em": (
            militar.atualizacao_cadastral_em.strftime("%d/%m/%Y %H:%M")
            if militar.atualizacao_cadastral_em else ""
        ),
    }
