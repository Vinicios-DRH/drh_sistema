from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only, selectinload

from src.models import (
    Militar,
    PostoGrad,
    MilitarObmFuncao,
    Obm,
    Situacao,
    MilitarContatoEmergencia,
    MilitarConjuge,
)
from src.utils.cadastro_status import (
    get_campos_pendentes_cadastro,
    LABELS_CAMPOS_CADASTRO,
)


def _query_militares_ativos_atualizacao():
    return (
        Militar.query
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Situacao, Situacao.id == Militar.situacao_id)
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


def _aplicar_filtros(query, q="", status="", posto_grad_id=None, situacao_id=None):
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

    if situacao_id:
        query = query.filter(Militar.situacao_id == situacao_id)

    return query


def _obter_obm_recente_obj(militar):
    if not militar or not militar.obm_funcoes:
        return None

    itens = [item for item in militar.obm_funcoes if item and item.obm]

    if not itens:
        return None

    def sort_key(item):
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


def _label_campo(campo):
    return LABELS_CAMPOS_CADASTRO.get(campo, campo.replace("_", " ").title())


def _campos_monitorados_detalhe():
    return [
        "grau_instrucao",
        "raca",
        "nome_pai",
        "nome_mae",
        "estado_civil",
        "data_nascimento",
        "endereco",
        "cidade",
        "estado",
        "cep",
        "celular",
        "email",
        "local_nascimento",
        "altura",
        "cor_olhos",
        "cor_cabelos",
        "medida_cabeca",
        "numero_sapato",
        "medida_calca",
        "medida_camisa",
        "tipo_sanguineo",
        "local_tatuagem",
        "contato_emergencia",
        "conjuge_nome",
    ]


def _base_load_lista():
    return (
        load_only(
            Militar.id,
            Militar.nome_completo,
            Militar.nome_guerra,
            Militar.matricula,
            Militar.posto_grad_id,
            Militar.situacao_id,
            Militar.atualizacao_cadastral_em,
            Militar.cadastro_atualizado,
        ),
        selectinload(Militar.posto_grad).load_only(
            PostoGrad.id,
            PostoGrad.sigla,
        ),
        selectinload(Militar.situacao).load_only(
            Situacao.id,
            Situacao.condicao,
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
            Militar.situacao_id,
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
            Militar.raca,
            Militar.local_nascimento,
            Militar.tatuagem,
            Militar.local_tatuagem,
        ),
        selectinload(Militar.posto_grad).load_only(
            PostoGrad.id,
            PostoGrad.sigla,
        ),
        selectinload(Militar.situacao).load_only(
            Situacao.id,
            Situacao.condicao,
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
        ),
        selectinload(Militar.contatos_emergencia).load_only(
            MilitarContatoEmergencia.id,
            MilitarContatoEmergencia.nome,
            MilitarContatoEmergencia.telefone,
            MilitarContatoEmergencia.parentesco,
            MilitarContatoEmergencia.telefone_secundario,
        ),
        selectinload(Militar.conjuge_cadastral).load_only(
            MilitarConjuge.id,
            MilitarConjuge.nome,
            MilitarConjuge.cpf,
            MilitarConjuge.telefone,
        ),
    )


def obter_resumo_atualizacao_cadastral(obm_id=None, posto_grad_id=None, situacao_id=None):
    query = _aplicar_filtros(
        _query_militares_ativos_atualizacao(),
        q="",
        status="",
        posto_grad_id=posto_grad_id,
        situacao_id=situacao_id,
    )

    militares = (
        query
        .options(*_base_load_lista())
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    if obm_id:
        militares = [
            m for m in militares if _militar_pertence_obm_recente(m, obm_id)
        ]

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


def obter_militares_atualizacao_cadastral(
    q="",
    status="",
    obm_id=None,
    posto_grad_id=None,
    situacao_id=None,
    page=1,
    per_page=50
):
    query = _aplicar_filtros(
        _query_militares_ativos_atualizacao(),
        q=q,
        status=status,
        posto_grad_id=posto_grad_id,
        situacao_id=situacao_id,
    )

    militares = (
        query
        .options(*_base_load_lista())
        .order_by(Militar.nome_completo.asc())
        .all()
    )

    if obm_id:
        militares = [
            m for m in militares if _militar_pertence_obm_recente(m, obm_id)
        ]

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


def listar_situacoes_atualizacao():
    return (
        Situacao.query
        .options(load_only(Situacao.id, Situacao.condicao))
        .order_by(Situacao.condicao.asc())
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
        "situacao": militar.situacao.condicao if militar.situacao else "-",
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
    pendentes_set = set(campos_pendentes)

    preenchidos = []
    pendentes = []

    for campo in _campos_monitorados_detalhe():
        label = _label_campo(campo)
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
        "situacao": militar.situacao.condicao if militar.situacao else "-",
        "obm": _obter_obm_principal(militar),
        "cadastro_atualizado": bool(militar.cadastro_atualizado),
        "cadastro_completo": len(campos_pendentes) == 0,
        "preenchidos": preenchidos,
        "pendentes": pendentes,
        "campos_pendentes_raw": campos_pendentes,
        "atualizacao_cadastral_em": (
            militar.atualizacao_cadastral_em.strftime("%d/%m/%Y %H:%M")
            if militar.atualizacao_cadastral_em else ""
        ),
    }
