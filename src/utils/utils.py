from flask import request
from flask_login import current_user
from src import database
from src.models import LogExportacaoExcel


def registrar_log_download(nome_relatorio, colunas_lista, filtros_dict="Nenhum filtro aplicado"):
    """Função global para registrar qualquer download de Excel no sistema."""
    try:
        # Pega o IP real do usuário (trata casos de proxy/Cloudflare)
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()

        # Formata a lista de colunas para texto
        colunas_str = "; ".join(colunas_lista) if isinstance(
            colunas_lista, list) else str(colunas_lista)

        novo_log = LogExportacaoExcel(
            usuario_id=current_user.id,
            nome_relatorio=nome_relatorio,
            ip_address=ip,
            colunas_selecionadas=colunas_str,
            filtros_aplicados=str(filtros_dict)
        )
        database.session.add(novo_log)
        database.session.commit()
    except Exception as e:
        database.session.rollback()
        # Não trava o download do usuário se o log falhar, mas avisa no terminal
        print(f"[ERRO DE LOG] Falha ao registrar exportação: {str(e)}")
