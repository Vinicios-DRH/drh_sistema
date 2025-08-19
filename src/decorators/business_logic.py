from datetime import datetime, timedelta
from src.models import MilitaresAgregados, MilitaresADisposicao, LicencaEspecial, LicencaParaTratamentoDeSaude
from src.decorators.email_utils import enviar_email
from src import database


def atualizar_status_agregacao(militar_agregado):
    hoje = datetime.now().date()
    fim_periodo = militar_agregado.fim_periodo_agregacao
    dias_restantes = (fim_periodo - hoje).days

    # Atualizando o status da agregação
    if militar_agregado.inicio_periodo <= hoje <= fim_periodo:
        militar_agregado.status = 'Vigente'
    else:
        militar_agregado.status = 'Término de Agregação'

    # Verificação de envio do email de 30 dias
    if dias_restantes <= 30 and not militar_agregado.email_30_dias_enviado:
        # Mesmo se faltar menos de 30 dias (ex: 22 dias), o email de 30 dias deve ser enviado
        mensagem = (f"Em {max(dias_restantes, 0)} dias termina a Vigência de AGREGAÇÃO do militar "
                    f"{militar_agregado.militar.nome_completo}.")
        print(f"Enviando email de 30 dias para {militar_agregado.militar.nome_completo}")  # Logging
        enviar_email('7519957@gmail.com', 'Aviso de Vigência - 30 Dias', mensagem)
        militar_agregado.email_30_dias_enviado = True

    # Verificação de envio do email de 15 dias
    if dias_restantes <= 15 and not militar_agregado.email_15_dias_enviado:
        # Mesmo se faltar menos de 15 dias (ex: 12 dias), o email de 15 dias deve ser enviado
        mensagem = f"Em {max(dias_restantes, 0)} dias termina a Vigência de AGREGAÇÃO do militar {militar_agregado.militar.nome_completo}."
        print(f"Enviando email de 15 dias para {militar_agregado.militar.nome_completo}")  # Logging
        enviar_email('7519957@gmail.com', 'Aviso de Vigência - 15 Dias', mensagem)
        militar_agregado.email_15_dias_enviado = True

    # Salvar as alterações no banco de dados
    database.session.commit()


def atualizar_status_a_disposicao(militar_a_disposicao):
    hoje = datetime.now().date()
    fim_periodo = militar_a_disposicao.fim_periodo_disposicao
    dias_restantes = (fim_periodo - hoje).days

    # atualizando status da disposição do militar
    if militar_a_disposicao.inicio_periodo <= hoje <= fim_periodo:
        militar_a_disposicao.status = 'Vigente'
    else:
        militar_a_disposicao.status = 'Término da Disposição'

    # Verificação do envio de email de 30 dias
    if dias_restantes <= 30 and not militar_a_disposicao.email_30_dias_enviado_disposicao:
        mensagem = (f'Em {max(dias_restantes, 0)} dias termina a VIGÊNCIA de DISPOSIÇÃO do militar '
                    f'{militar_a_disposicao.militar.nome_completo}.')
        print(f"Enviando email de 30 dias para {militar_a_disposicao.militar.nome_completo}")
        enviar_email('7519957@gmail.com', 'Aviso de DISPOSIÇÃO DE MILITAR - 30 DIAS', mensagem)
        militar_a_disposicao.email_30_dias_enviado_disposicao = True

    # Verificação do envio de email de 15 dias
    if dias_restantes <= 15 and not militar_a_disposicao.email_15_dias_enviado_disposicao:
        mensagem = (f'Em {max(dias_restantes, 0)} dias termina a VIGÊNCIA de DISPOSIÇÃO do militar '
                    f'{militar_a_disposicao.militar.nome_completo}.')
        print(f"Enviando email de 15 dias para {militar_a_disposicao.militar.nome_completo}")
        enviar_email('7519957@gmail.com', 'Aviso de DISPOSIÇÃO DE MILITAR - 15 DIAS', mensagem)
        militar_a_disposicao.email_15_dias_enviado_disposicao = True

    # Salvar as alterações no banco de dados
    database.session.commit()


def atualizar_status_le(militar_le):
    hoje = datetime.now().date()
    fim_periodo = militar_le.fim_periodo_le
    dias_restantes = (fim_periodo - hoje).days

    if militar_le.inicio_periodo_le <= hoje <= fim_periodo:
        militar_le.status = 'Vigente'
    else:
        militar_le.status = 'Término da Licença Especial'

    # Verificação do envio de email de 30 dias
    if dias_restantes <= 30 and not militar_le.email_30_dias_enviado_le:
        mensagem = (f'Em {max(dias_restantes, 0)} dias termina a VIGÊNCIA de Licença Especial do militar '
                    f'{militar_le.militar.nome_completo}.')
        print(f"Enviando email de 30 dias para {militar_le.militar.nome_completo}")
        enviar_email('7519957@gmail.com', 'Aviso de LICENÇA ESPECIAL DE MILITAR - 30 DIAS', mensagem)
        militar_le.email_30_dias_enviado_le = True

    # Verificação do envio de email de 15 dias
    if dias_restantes <= 15 and not militar_le.email_15_dias_enviado_le:
        mensagem = (f'Em {max(dias_restantes, 0)} dias termina a VIGÊNCIA de LICENÇA ESPECIAL do militar '
                    f'{militar_le.militar.nome_completo}.')
        print(f"Enviando email de 15 dias para {militar_le.militar.nome_completo}")
        enviar_email('7519957@gmail.com', 'Aviso de LICENÇA ESPECIAL DE MILITAR - 15 DIAS', mensagem)
        militar_le.email_15_dias_enviado_le = True

    database.session.commit()


def atualizar_status_lts(militar_lts):
    hoje = datetime.now().date()
    fim_periodo = militar_lts.fim_periodo_lts
    dias_restantes = (fim_periodo - hoje).days

    if militar_lts.inicio_periodo_lts <= hoje <= fim_periodo:
        militar_lts.status = 'Vigente'
    else:
        militar_lts.status = 'Término da Licença para Tratamento de Saúde'

    # Verificação do envio de email de 30 dias
    if dias_restantes <= 30 and not militar_lts.email_30_dias_enviado_lts:
        mensagem = (f'Em {max(dias_restantes, 0)} dias termina a VIGÊNCIA de LTS do militar '
                    f'{militar_lts.militar.nome_completo}.')
        print(f"Enviando email de 30 dias para {militar_lts.militar.nome_completo}")
        enviar_email('7519957@gmail.com', 'Aviso de LICENÇA PARA TRATAMENTO DE SAÚDE DE MILITAR - 30 DIAS', mensagem)
        militar_lts.email_30_dias_enviado_lts = True

    # Verificação do envio de email de 15 dias
    if dias_restantes <= 15 and not militar_lts.email_15_dias_enviado_lts:
        mensagem = (f'Em {max(dias_restantes, 0)} dias termina a VIGÊNCIA de LTS do militar '
                    f'{militar_lts.militar.nome_completo}.')
        print(f"Enviando email de 15 dias para {militar_lts.militar.nome_completo}")
        enviar_email('7519957@gmail.com', 'Aviso de LICENÇA PARA TRATAMENTO DE SAÚDE DE MILITAR - 15 DIAS', mensagem)
        militar_lts.email_15_dias_enviado_lts = True

    database.session.commit()


def processar_militares_agregados():
    militares_agregados = MilitaresAgregados.query.filter(MilitaresAgregados.status == 'Vigente').all()
    for militar in militares_agregados:
        atualizar_status_agregacao(militar)


def processar_militares_a_disposicao():
    militares_a_disposicao = MilitaresADisposicao.query.filter(MilitaresADisposicao.status == 'Vigente').all()

    for militar_a_disposicao in militares_a_disposicao:
        atualizar_status_a_disposicao(militar_a_disposicao)


def processar_militares_le():
    militares_le = LicencaEspecial.query.filter(LicencaEspecial.status == 'Vigente').all()

    for militar_le in militares_le:
        atualizar_status_le(militar_le)


def processar_militares_lts():
    militares_lts = LicencaParaTratamentoDeSaude.query.filter(LicencaParaTratamentoDeSaude.status == 'Vigente').all()

    for militar_lts in militares_lts:
        atualizar_status_lts(militar_lts)
