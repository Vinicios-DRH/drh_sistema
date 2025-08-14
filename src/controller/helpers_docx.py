# helpers_docx.py
import io
import zipfile
import re
from typing import Dict

# Fallback 100% em regex (não depende de lxml)
# - Resolve {chave} contínuo
# - Resolve { + chave + } quebrado em três <w:t> diferentes


def _replace_in_xml_text(xml: str, mapping: Dict[str, str]) -> str:
    # 1) Caso “fácil”: {chave} contínuo
    for k, v in mapping.items():
        xml = xml.replace("{%s}" % k, str(v))

    # 2) Caso “quebrado”: <w:t>{</w:t> ... <w:t>chave</w:t> ... <w:t>}</w:t>
    #    Permitindo espaços e atributos nos w:t
    for k, v in mapping.items():
        # tudo na mesma sequência (típico do Word): { | chave | }
        patt = re.compile(
            r"(<w:t[^>]*>)\{\s*(</w:t>\s*<w:t[^>]*>)\s*"
            + re.escape(k) +
            r"\s*(</w:t>\s*<w:t[^>]*>)\s*\}(</w:t>)"
        )
        xml = patt.sub(r"\1" + str(v) + r"\4", xml)

        # variação: às vezes não há espaçamentos intermediários
        patt2 = re.compile(
            r"<w:t[^>]*>\{\s*</w:t>\s*<w:t[^>]*>\s*"
            + re.escape(k) +
            r"\s*</w:t>\s*<w:t[^>]*>\s*\}</w:t>"
        )
        xml = patt2.sub("<w:t>%s</w:t>" % str(v), xml)

    return xml


def render_docx_from_template(template_path: str, mapping: Dict[str, str]) -> io.BytesIO:
    """Abre o DOCX, troca placeholders inclusive os quebrados em múltiplos <w:t>, e retorna um buffer pronto para download."""
    buf = io.BytesIO()
    with zipfile.ZipFile(template_path, "r") as zin, \
            zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".xml"):
                s = data.decode("utf-8", errors="ignore")
                s = _replace_in_xml_text(s, mapping)
                data = s.encode("utf-8")
            zout.writestr(info, data)
    buf.seek(0)
    return buf


# Utilitário opcional de debug — lista as chaves que o template realmente tem
def list_placeholders_in_docx(template_path: str):
    rx = re.compile(r"\{([A-Za-z0-9_]+)\}")
    found = set()
    with zipfile.ZipFile(template_path, "r") as z:
        for name in z.namelist():
            if not name.endswith(".xml"):
                continue
            s = z.read(name).decode("utf-8", errors="ignore")
            found.update(rx.findall(s))
            # também coleta a forma quebrada { | chave | }
            # captura <w:t>{</w:t><w:t>chave</w:t><w:t>}</w:t>
            for m in re.finditer(r"<w:t[^>]*>\{\s*</w:t>\s*<w:t[^>]*>\s*([A-Za-z0-9_]+)\s*</w:t>\s*<w:t[^>]*>\s*\}</w:t>", s):
                found.add(m.group(1))
    return sorted(found)
