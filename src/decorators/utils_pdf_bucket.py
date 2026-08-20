"""Upload de PDF pro servidor próprio do CBMAM (API PHP em cbm.am.gov.br),
usado por Gestão de Chefia (comprovantes de licença/especialidade) e por
Cursos CBMAM (PDFs de inscrição). Alternativa ao Backblaze B2 quando a
integração B2 está instável — essa API já é usada em produção.
"""
import re
import unicodedata
import urllib.parse

import requests

API_BUCKET_URL = "https://www.cbm.am.gov.br/api"
API_BUCKET_KEY = "cbmam_pdf_upload_token_2026_secured"


def sanitizar_nome(texto):
    """Remove acentos, troca espaços por '_' e deixa minúsculo para usar em arquivos/pastas."""
    if not texto:
        return "doc"
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-zA-Z0-9]', '_', texto).lower()
    return re.sub(r'_+', '_', texto).strip('_')


def upload_pdf_para_servidor(file_obj, subfolder, novo_nome=None):
    """
    Tenta criar a pasta e fazer o upload do PDF.
    Se 'novo_nome' for fornecido, renomeia o arquivo antes de enviar.

    Retorna (True, url_final) em caso de sucesso, ou (False, mensagem_erro).
    """
    headers = {"X-API-Key": API_BUCKET_KEY}

    try:
        # 1. Criar pasta (Ignora o 409 se já existir)
        requests.post(
            f"{API_BUCKET_URL}/bucket.php?action=mkdir",
            headers={**headers, "Content-Type": "application/json"},
            json={"folder": subfolder},
            timeout=10
        )

        # 2. Preparar nome do arquivo
        nome_arquivo_envio = file_obj.filename
        if novo_nome:
            extensao = nome_arquivo_envio.rsplit('.', 1)[-1].lower() if '.' in nome_arquivo_envio else 'pdf'
            nome_arquivo_envio = f"{novo_nome}.{extensao}"

        conteudo_arquivo = file_obj.read()
        files = {'file': (nome_arquivo_envio, conteudo_arquivo, file_obj.mimetype)}

        print(f"🚀 [UPLOAD INICIADO] Enviando '{nome_arquivo_envio}' para a pasta '{subfolder}'...")

        resposta = requests.post(
            f"{API_BUCKET_URL}/upload_pdf.php?folder={subfolder}",
            headers=headers,
            files=files,
            timeout=30
        )

        print(f"📥 [API RESPONDEU] Status: {resposta.status_code} | Corpo: {resposta.text}")

        if resposta.status_code == 200:
            dados = resposta.json()
            if dados.get("success"):
                url_final = dados.get("url")
                if not url_final:
                    nome_arquivo_retornado = dados.get("filename")
                    folder_encoded = urllib.parse.quote(subfolder, safe='')
                    url_final = f"{API_BUCKET_URL}/download_pdf.php?folder={folder_encoded}&file={nome_arquivo_retornado}"
                return True, url_final
            else:
                return False, dados.get("message", "API retornou 200, mas success=False.")
        else:
            return False, f"Erro HTTP {resposta.status_code}: {resposta.text}"

    except Exception as e:
        print(f"❌ [ERRO DE CONEXÃO] {str(e)}")
        return False, f"Falha de conexão: {str(e)}"
