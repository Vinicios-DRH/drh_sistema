from src import bcrypt
from src.models import Militar, MilitaresAgregados, MilitaresADisposicao, User
from sqlalchemy import and_
from datetime import datetime
from flask import request
import pytz


def obter_estatisticas_militares():
    """Executa as consultas necessárias e retorna os resultados em um dicionário."""
    efetivo_total = Militar.query.count()

    # Excluindo os civis (posto_grad_id != 15)
    efetivo_total_sem_civis = Militar.query.filter(Militar.posto_grad_id != 15).count()

    efetivo_civis = Militar.query.filter(Militar.posto_grad_id == 15).count()

    oficiais_superiores = Militar.query.filter(
        Militar.posto_grad_id.in_([14, 13, 12])
    ).count()

    oficiais_intermediarios = Militar.query.filter(
        Militar.posto_grad_id == 11
    ).count()

    oficiais_subalternos = Militar.query.filter(
        Militar.posto_grad_id.in_([10, 9])
    ).count()

    pracas = Militar.query.filter(
        Militar.posto_grad_id.in_([16, 6, 5, 4, 3, 2, 1])
    ).count()

    a_disposicao = MilitaresADisposicao.query.count()

    agregados_total = MilitaresAgregados.query.count()

    agregados = (
        Militar.query.join(MilitaresAgregados, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.agregacoes_id == 5)
        .count()
    )

    agregados_lts = (
        Militar.query.join(MilitaresAgregados, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.agregacoes_id == 2)
        .count()
    )

    agregados_rr = (
        Militar.query.join(MilitaresAgregados, Militar.id == MilitaresAgregados.militar_id)
        .filter(Militar.agregacoes_id == 4)
        .count()
    )

    militares_combatentes = Militar.query.filter(
        Militar.especialidade_id == 3
    ).count()

    militares_saude = Militar.query.filter(
        Militar.especialidade_id.in_([1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    ).count()

    cbc = Militar.query.filter(
        Militar.localidade_id == 1
    ).count()

    cbi = Militar.query.filter(
        Militar.localidade_id == 2
    ).count()

    qobm = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 2,
        Militar.especialidade_id == 3
    )).count()

    qoabm = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 3
    )).count()

    qcobm_medico = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id.in_([7, 8, 9])
    )).count()

    qcobm_enfermeiro = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 5
    )).count()

    qcobm_dentista = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 4
    )).count()

    qcobm_assistente_social = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 2
    )).count()

    qcobm_farmaceutico = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([9, 10, 11, 12, 13, 14]),
        Militar.quadro_id == 5,
        Militar.especialidade_id == 6
    )).count()

    qcobm_al_01 = Militar.query.filter(and_(
        Militar.posto_grad_id == 8,
        Militar.quadro_id == 5
    )).count()

    qobm_al_01 = Militar.query.filter(and_(
        Militar.posto_grad_id == 7,
        Militar.quadro_id == 7,
        Militar.especialidade_id == 3
    )).count()

    qpbm = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([1, 2, 3, 4, 5, 6]),
        Militar.quadro_id == 1,
        Militar.especialidade_id == 3
    )).count()

    qpebm = Militar.query.filter(and_(
        Militar.posto_grad_id == 6,
        Militar.quadro_id == 6,
        Militar.especialidade_id == 3
    )).count()

    qcpbm = Militar.query.filter(and_(
        Militar.posto_grad_id.in_([1, 2, 3, 4, 5, 6]),
        Militar.quadro_id == 4,
        Militar.especialidade_id.in_([1, 10, 11, 12])
    )).count()

    licenca_especial = Militar.query.filter(Militar.situacao_id == 4).count()

    lts = Militar.query.filter(Militar.situacao_id == 6).count()

    maternidade = Militar.query.filter(Militar.situacao_id == 5).count()

    return {
        'efetivo_total': efetivo_total,
        'efetivo_total_sem_civis': efetivo_total_sem_civis,
        'efetivo_civis': efetivo_civis,
        'oficiais_superiores': oficiais_superiores,
        'oficiais_intermediarios': oficiais_intermediarios,
        'oficiais_subalternos': oficiais_subalternos,
        'qcobm_al_01': qcobm_al_01,
        'pracas': pracas,
        'a_disposicao': a_disposicao,
        'agregados_total': agregados_total,
        'agregados': agregados,
        'agregados_lts': agregados_lts,
        'agregados_rr': agregados_rr,
        'militares_combatentes': militares_combatentes,
        'militares_saude': militares_saude,
        'cbc': cbc,
        'cbi': cbi,
        'qobm': qobm,
        'licenca_especial': licenca_especial,
        'lts': lts,
        'maternidade': maternidade,
        'qoabm': qoabm,
        'qcobm_medico': qcobm_medico,
        'qcobm_enfermeiro': qcobm_enfermeiro,
        'qcobm_dentista': qcobm_dentista,
        'qcobm_assistente_social': qcobm_assistente_social,
        'qcobm_farmaceutico': qcobm_farmaceutico,
        'qobm_al_01': qobm_al_01,
        'qpbm': qpbm,
        'qpebm': qpebm,
        'qcpbm': qcpbm
    }


def get_user_ip():
    # Verifica se o cabeçalho X-Forwarded-For está presente
    if request.headers.get('X-Forwarded-For'):
        # Pode conter múltiplos IPs, estou pegando o primeiro
        ip = request.headers.getlist('X-Forwarded-For')[0]
    else:
        # Fallback para o IP remoto
        ip = request.remote_addr
    return ip


def login_usuario(cpf, senha):
    user = User.query.filter_by(cpf=cpf).first()

    if user and bcrypt.check_password_hash(user.senha, senha):
        fuso_horario = pytz.timezone('America/Manaus')
        user.data_ultimo_acesso = datetime.now(fuso_horario)
        user.ip_address = get_user_ip()
        return user
    
    return None
