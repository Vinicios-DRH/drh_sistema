import smtplib
from email.mime.text import MIMEText

def enviar_email(destinatario, assunto, mensagem):
    try:
        # Configuração do servidor SMTP
        smtp_server = 'smtp.office365.com'
        port = 587
        login = 'bm6@cbm.am.gov.br'
        password = 'Ticbmam193#'

        # Criação da mensagem
        msg = MIMEText(mensagem)
        msg['Subject'] = assunto
        msg['From'] = login
        msg['To'] = destinatario

        # Envio do e-mail
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()
            server.login(login, password)
            server.sendmail(msg['From'], [msg['To']], msg.as_string())
        print("Email enviado com sucesso!")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
