"""Upload de PDF pro servidor próprio do CBMAM (API PHP em cbm.am.gov.br),
usado por Gestão de Chefia (comprovantes de licença/especialidade) e por
Cursos CBMAM (PDFs de inscrição). Alternativa ao Backblaze B2 quando a
integração B2 está instável — essa API já é usada em produção.
"""
import re
import unicodedata
import urllib.parse
import logging
import os
from urllib.parse import urljoin, urlsplit

import requests
from werkzeug.utils import secure_filename

API_BUCKET_URL = "https://www.cbm.am.gov.br/api"
API_BUCKET_HOSTS = {"www.cbm.am.gov.br", "cbm.am.gov.br"}
API_BUCKET_KEY_ENV = "PDF_BUCKET_API_KEY"
logger = logging.getLogger(__name__)


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
    api_key = os.getenv(API_BUCKET_KEY_ENV, "").strip()
    if not api_key:
        return False, f"Variável de ambiente {API_BUCKET_KEY_ENV} ausente."

    try:
        nome_original = secure_filename(file_obj.filename or "")
        extensao = os.path.splitext(nome_original)[1].lower()
        if not nome_original or extensao != ".pdf":
            return False, "Envie um arquivo PDF válido."

        headers = {"X-API-Key": api_key}
        nome_base = secure_filename(novo_nome or os.path.splitext(nome_original)[0])
        if not nome_base:
            return False, "Nome do arquivo inválido."

        # 1. Criar pasta (Ignora o 409 se já existir)
        resposta_pasta = requests.post(
            f"{API_BUCKET_URL}/bucket.php?action=mkdir",
            headers={**headers, "Content-Type": "application/json"},
            json={"folder": subfolder},
            timeout=10
        )
        if resposta_pasta.status_code not in (200, 201, 409):
            return False, (
                "Erro ao preparar o armazenamento "
                f"(HTTP {resposta_pasta.status_code})."
            )

        # 2. Preparar nome do arquivo
        nome_arquivo_envio = f"{nome_base}.pdf"

        conteudo_arquivo = file_obj.read()
        files = {
            "file": (
                nome_arquivo_envio,
                conteudo_arquivo,
                file_obj.mimetype or "application/pdf",
            )
        }

        resposta = requests.post(
            f"{API_BUCKET_URL}/upload_pdf.php?"
            f"{urllib.parse.urlencode({'folder': subfolder})}",
            headers=headers,
            files=files,
            timeout=30
        )

        if resposta.status_code == 200:
            dados = resposta.json()
            if dados.get("success"):
                url_final = dados.get("url")
                if not url_final:
                    nome_arquivo_retornado = dados.get("filename")
                    if not nome_arquivo_retornado:
                        return False, "A API não informou o arquivo enviado."
                    url_final = (
                        f"{API_BUCKET_URL}/download_pdf.php?"
                        f"{urllib.parse.urlencode({'folder': subfolder, 'file': nome_arquivo_retornado})}"
                    )
                else:
                    url_final = _normalizar_url_download(url_final)
                return True, url_final
            else:
                return False, dados.get("message", "API retornou 200, mas success=False.")
        else:
            return False, f"Falha no envio do arquivo (HTTP {resposta.status_code})."

    except Exception as e:
        logger.exception("Falha ao enviar PDF para o servidor de arquivos")
        return False, f"Falha de conexão: {str(e)}"


def _normalizar_url_download(url):
    url = urljoin(f"{API_BUCKET_URL}/", str(url or "").strip())
    parsed_url = urlsplit(url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or parsed_url.hostname not in API_BUCKET_HOSTS
        or parsed_url.path not in {
            "/api/download_pdf.php",
            "/download_pdf.php",
        }
    ):
        raise ValueError("A API retornou uma URL de download inválida.")

    # Links antigos da API foram gravados em HTTP; force HTTPS ao reutilizá-los.
    return parsed_url._replace(scheme="https").geturl()


def baixar_pdf_do_servidor(url):
    """Baixa um PDF da API CBMAM usando a mesma credencial dos uploads."""
    api_key = os.getenv(API_BUCKET_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"Variável de ambiente {API_BUCKET_KEY_ENV} ausente.")

    url = _normalizar_url_download(url)
    resposta = requests.get(
        url,
        headers={"X-API-Key": api_key},
        timeout=(10, 60),
        allow_redirects=False,
    )
    if not 200 <= resposta.status_code < 300:
        resposta.raise_for_status()
        raise requests.HTTPError(
            f"Download da API retornou HTTP {resposta.status_code}."
        )
    if b"%PDF-" not in resposta.content[:1024]:
        raise ValueError("A API não retornou um documento PDF válido.")
    return resposta.content
