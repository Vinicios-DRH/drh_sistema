from datetime import datetime
from src import database
from src.models import (
    MilitaresAgregados, MilitaresADisposicao,
    LicencaEspecial, LicencaParaTratamentoDeSaude
)
from src.decorators.email_utils import enviar_email


def _hoje():
    return datetime.now().date()

def _dias_restantes(fim):
    if not fim:
        return None
    return (fim - _hoje()).days


# -------------------------
# AGREGADOS
# -------------------------
def atualizar_status_agregacao(m):
    ini = m.inicio_periodo
    fim = m.fim_periodo_agregacao

    if not ini or not fim:
        m.status = 'Dados incompletos'
        return

    if _hoje() < ini:
        m.status = 'A iniciar'
        return

    if ini <= _hoje() <= fim:
        m.status = 'Vigente'
        # avisos
        # dias = _dias_restantes(fim)
        # if dias is not None:
        #     if dias <= 30 and not m.email_30_dias_enviado:
        #         enviar_email('7519957@gmail.com', 'Aviso de Vigência - 30 Dias',
        #                      f"Em {max(dias, 0)} dias termina a Vigência de AGREGAÇÃO do militar {m.militar.nome_completo}.")
        #         m.email_30_dias_enviado = True
        #     if dias <= 15 and not m.email_15_dias_enviado:
        #         enviar_email('7519957@gmail.com', 'Aviso de Vigência - 15 Dias',
        #                      f"Em {max(dias, 0)} dias termina a Vigência de AGREGAÇÃO do militar {m.militar.nome_completo}.")
        #         m.email_15_dias_enviado = True
        return

    m.status = 'Término de Agregação'


# -------------------------
# À DISPOSIÇÃO
# -------------------------
def atualizar_status_a_disposicao(m):
    ini = m.inicio_periodo
    fim = m.fim_periodo_disposicao

    if not ini or not fim:
        m.status = 'Dados incompletos'
        return

    if _hoje() < ini:
        m.status = 'A iniciar'
        return

    if ini <= _hoje() <= fim:
        m.status = 'Vigente'
        dias = _dias_restantes(fim)
        # if dias is not None:
        #     if dias <= 30 and not m.email_30_dias_enviado_disposicao:
        #         enviar_email('7519957@gmail.com', 'Aviso de DISPOSIÇÃO DE MILITAR - 30 DIAS',
        #                      f"Em {max(dias, 0)} dias termina a VIGÊNCIA de DISPOSIÇÃO do militar {m.militar.nome_completo}.")
        #         m.email_30_dias_enviado_disposicao = True
        #     if dias <= 15 and not m.email_15_dias_enviado_disposicao:
        #         enviar_email('7519957@gmail.com', 'Aviso de DISPOSIÇÃO DE MILITAR - 15 DIAS',
        #                      f"Em {max(dias, 0)} dias termina a VIGÊNCIA de DISPOSIÇÃO do militar {m.militar.nome_completo}.")
        #         m.email_15_dias_enviado_disposicao = True
        return

    m.status = 'Término da Disposição'


# -------------------------
# LICENÇA ESPECIAL (já ok)
# -------------------------
def atualizar_status_le(m):
    hoje = _hoje()
    ini = m.inicio_periodo_le
    fim = m.fim_periodo_le

    if not ini or not fim:
        m.status = 'Dados incompletos'
        return

    if hoje < ini:
        m.status = 'A iniciar'
    elif ini <= hoje <= fim:
        m.status = 'Vigente'
        # avisos (opcional)
        # dias = _dias_restantes(fim)
        # if dias is not None:
        #     if dias <= 30 and not m.email_30_dias_enviado_le:
        #         enviar_email('7519957@gmail.com', 'Aviso de LICENÇA ESPECIAL DE MILITAR - 30 DIAS',
        #                      f'Em {max(dias, 0)} dias termina a VIGÊNCIA de Licença Especial do militar {m.militar.nome_completo}.')
        #         m.email_30_dias_enviado_le = True
        #     if dias <= 15 and not m.email_15_dias_enviado_le:
        #         enviar_email('7519957@gmail.com', 'Aviso de LICENÇA ESPECIAL DE MILITAR - 15 DIAS',
        #                      f'Em {max(dias, 0)} dias termina a VIGÊNCIA de LICENÇA ESPECIAL do militar {m.militar.nome_completo}.')
        #         m.email_15_dias_enviado_le = True
    else:
        m.status = 'Término da Licença Especial'


# -------------------------
# LTS
# -------------------------
def atualizar_status_lts(m):
    hoje = _hoje()
    ini = m.inicio_periodo_lts
    fim = m.fim_periodo_lts

    if not ini or not fim:
        m.status = 'Dados incompletos'
        return

    if hoje < ini:
        m.status = 'A iniciar'
    elif ini <= hoje <= fim:
        m.status = 'Vigente'
        # (se quiser avisos por e-mail, use flags equivalentes às de LE)
        # dias = _dias_restantes(fim)
        # ...
    else:
        m.status = 'Término da Licença para Tratamento de Saúde'


def processar_militares_agregados():
    itens = MilitaresAgregados.query.all()
    for m in itens:
        atualizar_status_agregacao(m)
    database.session.commit()

def processar_militares_a_disposicao():
    itens = MilitaresADisposicao.query.all()
    for m in itens:
        atualizar_status_a_disposicao(m)
    database.session.commit()

def processar_militares_le():
    itens = LicencaEspecial.query.all()
    for m in itens:
        atualizar_status_le(m)
    database.session.commit()

def processar_militares_lts():
    itens = LicencaParaTratamentoDeSaude.query.all()
    for m in itens:
        atualizar_status_lts(m)
    database.session.commit()
