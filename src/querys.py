import json
from datetime import datetime

import pytz
from flask import request
from sqlalchemy import and_, func

from src import bcrypt, database
from src.models import (
    Militar,
    MilitaresAgregados,
    MilitaresADisposicao,
    User,
    Obm,
    MilitarObmFuncao,
)


def obter_estatisticas_militares():
    """
    Executa as consultas necessárias e retorna os resultados em um dicionário.
    Todas as estatísticas consideram apenas militares ATIVOS (inativo = False).
    """

    # Query base: somente militares ativos
    militares_ativos = Militar.query.filter(Militar.inativo.is_(False))

    # Total de militares ativos (inclui civis)
    efetivo_total = militares_ativos.count()

    # Excluindo os civis (posto_grad_id != 15)
    efetivo_total_sem_civis = militares_ativos.filter(
        Militar.posto_grad_id != 15
    ).count()

    # Apenas civis (ativos)
    efetivo_civis = militares_ativos.filter(
        Militar.posto_grad_id == 15
    ).count()

    # Oficiais (ativos)
    oficiais_superiores = militares_ativos.filter(
        Militar.posto_grad_id.in_([14, 13, 12])
    ).count()

    oficiais_intermediarios = militares_ativos.filter(
        Militar.posto_grad_id == 11
    ).count()

    oficiais_subalternos = militares_ativos.filter(
        Militar.posto_grad_id.in_([10, 9])
    ).count()

    # Praças (ativos)
    pracas = militares_ativos.filter(
        Militar.posto_grad_id.in_([16, 6, 5, 4, 3, 2, 1])
    ).count()

    # À disposição — apenas de militares ativos
    a_disposicao = (
        MilitaresADisposicao.query
        .join(Militar, Militar.id == MilitaresADisposicao.militar_id)
        .filter(Militar.inativo.is_(False))
        .count()
    )

    # Agregados — apenas de militares ativos
    agregados_total = (
        MilitaresAgregados.query
        .join(Militar, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.inativo.is_(False))
        .count()
    )

    agregados = (
        militares_ativos
        .join(MilitaresAgregados, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.agregacoes_id == 5)
        .count()
    )

    agregados_lts = (
        militares_ativos
        .join(MilitaresAgregados, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.agregacoes_id == 2)
        .count()
    )

    agregados_rr = (
        militares_ativos
        .join(MilitaresAgregados, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.agregacoes_id == 4)
        .count()
    )

    # Especialidades / saúde / localidade (sempre só ativos)
    militares_combatentes = militares_ativos.filter(
        Militar.especialidade_id == 3
    ).count()

    militares_saude = militares_ativos.filter(
        Militar.especialidade_id.in_(
            [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        )
    ).count()

    cbc = militares_ativos.filter(
        Militar.localidade_id == 1
    ).count()

    cbi = militares_ativos.filter(
        Militar.localidade_id == 2
    ).count()

    # Quadros / postos específicos
    qobm = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 2,
        Militar.especialidade_id == 3
    )).count()

    qoabm = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 3
    )).count()

    qcobm_medico = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id.in_([7, 8, 9])
    )).count()

    qcobm_enfermeiro = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 5
    )).count()

    qcobm_dentista = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 4
    )).count()

    qcobm_assistente_social = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 2
    )).count()

    qcobm_farmaceutico = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 6
    )).count()

    qcobm_al_01 = militares_ativos.filter(and_(
        Militar.posto_grad_id == 8,
        Militar.quadro_id == 5
    )).count()

    qobm_al_01 = militares_ativos.filter(and_(
        Militar.posto_grad_id == 7,
        Militar.quadro_id == 7,
        Militar.especialidade_id == 3
    )).count()

    qpbm = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([1, 2, 3, 4, 5, 6]),
        Militar.quadro_id == 1,
        Militar.especialidade_id == 3
    )).count()

    qpebm = militares_ativos.filter(and_(
        Militar.posto_grad_id == 6,
        Militar.quadro_id == 6,
        Militar.especialidade_id == 3
    )).count()

    qcpbm = militares_ativos.filter(and_(
        Militar.posto_grad_id.in_([1, 2, 3, 4, 5, 6]),
        Militar.quadro_id == 4,
        Militar.especialidade_id.in_([1, 10, 11, 12])
    )).count()

    # Situações — sempre só ativos
    licenca_especial = militares_ativos.filter(
        Militar.situacao_id == 4
    ).count()

    lts = militares_ativos.filter(
        Militar.situacao_id == 6
    ).count()

    maternidade = militares_ativos.filter(
        Militar.situacao_id == 5
    ).count()

    return {
        "efetivo_total": efetivo_total,
        "efetivo_total_sem_civis": efetivo_total_sem_civis,
        "efetivo_civis": efetivo_civis,
        "oficiais_superiores": oficiais_superiores,
        "oficiais_intermediarios": oficiais_intermediarios,
        "oficiais_subalternos": oficiais_subalternos,
        "qcobm_al_01": qcobm_al_01,
        "pracas": pracas,
        "a_disposicao": a_disposicao,
        "agregados_total": agregados_total,
        "agregados": agregados,
        "agregados_lts": agregados_lts,
        "agregados_rr": agregados_rr,
        "militares_combatentes": militares_combatentes,
        "militares_saude": militares_saude,
        "cbc": cbc,
        "cbi": cbi,
        "qobm": qobm,
        "licenca_especial": licenca_especial,
        "lts": lts,
        "maternidade": maternidade,
        "qoabm": qoabm,
        "qcobm_medico": qcobm_medico,
        "qcobm_enfermeiro": qcobm_enfermeiro,
        "qcobm_dentista": qcobm_dentista,
        "qcobm_assistente_social": qcobm_assistente_social,
        "qcobm_farmaceutico": qcobm_farmaceutico,
        "qobm_al_01": qobm_al_01,
        "qpbm": qpbm,
        "qpebm": qpebm,
        "qcpbm": qcpbm,
    }


def get_user_ip():
    # Verifica se o cabeçalho X-Forwarded-For está presente
    if request.headers.get("X-Forwarded-For"):
        # Pode conter múltiplos IPs, estou pegando o primeiro
        ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        # Fallback para o IP remoto
        ip = request.remote_addr
    return ip


def login_usuario(cpf, senha):
    user = User.query.filter_by(cpf=cpf).first()

    if user and bcrypt.check_password_hash(user.senha, senha):
        fuso_horario = pytz.timezone("America/Manaus")
        user.data_ultimo_acesso = datetime.now(fuso_horario)
        user.ip_address = get_user_ip()
        return user

    return None


def efetivo_oficiais_por_obm():
    """Retorna efetivo de oficiais ATIVOS por OBM."""
    oficiais_ids = [9, 10, 11, 12, 13, 14]

    resultados = (
        database.session.query(
            Obm.id,
            Obm.sigla,
            func.count(Militar.id).label("quantidade_oficiais"),
        )
        .join(MilitarObmFuncao, Obm.id == MilitarObmFuncao.obm_id)
        .join(Militar, Militar.id == MilitarObmFuncao.militar_id)
        .filter(
            Militar.posto_grad_id.in_(oficiais_ids),
            Militar.inativo.is_(False),
        )
        .group_by(Obm.id, Obm.sigla)
        .order_by(Obm.sigla)
        .all()
    )

    return [
        {
            "obm_id": r.id,
            "obm_sigla": r.sigla,
            "efetivo_oficiais": r.quantidade_oficiais,
        }
        for r in resultados
    ]


def dados_para_mapa():
    """
    Dados para o mapa: efetivo de oficiais ATIVOS por OBM,
    já com coordenadas do JSON.
    """
    resultado = (
        database.session.query(
            Obm.id,
            Obm.sigla,
            func.count(Militar.id).label("efetivo"),
        )
        .join(MilitarObmFuncao, Obm.id == MilitarObmFuncao.obm_id)
        .join(Militar, Militar.id == MilitarObmFuncao.militar_id)
        .filter(
            Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),  # oficiais
            Militar.inativo.is_(False),
        )
        .group_by(Obm.id, Obm.sigla)
        .all()
    )

    # Carrega coordenadas
    with open("src/obm_coords.json", "r", encoding="utf-8") as f:
        coords = json.load(f)

    coord_map = {item["id"]: item for item in coords}

    dados = []
    for obm_id, nome, efetivo in resultado:
        info = coord_map.get(obm_id)
        if info:
            dados.append(
                {
                    "nome": nome,
                    "cidade": info.get("cidade", "Desconhecida"),
                    "latitude": info["latitude"],
                    "longitude": info["longitude"],
                    "efetivo": efetivo,
                }
            )

    return dados
