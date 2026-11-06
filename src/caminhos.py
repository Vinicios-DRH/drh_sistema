"""
Caminhos de arquivos do projeto, absolutos a partir da pasta `src/`.

No servidor (IIS + serviço do Windows via nssm) o processo Python não inicia
na raiz do projeto, então caminhos relativos como "src/template/x.docx" não
são encontrados e a rota cai em erro 500. Use sempre estas funções para abrir
arquivos que vêm junto com o código.
"""
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SRC_DIR / "template"


def modelo_docx(nome: str) -> str:
    """Caminho absoluto de um modelo .docx em src/template/."""
    return str(TEMPLATE_DIR / nome)


def arquivo_src(*partes: str) -> str:
    """Caminho absoluto de um arquivo dentro de src/ (ex.: 'obm_coords.json')."""
    return str(SRC_DIR.joinpath(*partes))
