import smtplib
from email.mime.text import MIMEText

# Configuração do servidor SMTP
smtp_server = 'smtp.office365.com'
port = 587
login = 'drh@cbm.am.gov.br'
password = 'Cbmam2023#'

# Criação da mensagem
msg = MIMEText('Teste de email')
msg['Subject'] = 'Teste'
msg['From'] = login
msg['To'] = '7519957@gmail.com'

# Envio do e-mail
with smtplib.SMTP(smtp_server, port) as server:
    server.starttls()
    server.login(login, password)
    server.sendmail(msg['From'], [msg['To']], msg.as_string())

print("Email enviado com sucesso!")
