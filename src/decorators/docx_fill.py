# docx_fill.py
from docx import Document

def _replace_in_paragraph(paragraph, mapping: dict[str, str]):
    # junta tudo, troca, e reescreve mantendo o parágrafo simples
    full = "".join(run.text for run in paragraph.runs)
    new = full
    for k, v in mapping.items():
        new = new.replace(k, v)

    if new != full:
        # zera runs e coloca tudo no primeiro
        if paragraph.runs:
            paragraph.runs[0].text = new
            for r in paragraph.runs[1:]:
                r.text = ""
        else:
            paragraph.add_run(new)

def docx_fill_template(template_path: str, mapping: dict[str, str]) -> bytes:
    doc = Document(template_path)

    # parágrafos
    for p in doc.paragraphs:
        _replace_in_paragraph(p, mapping)

    # tabelas
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _replace_in_paragraph(p, mapping)

    from io import BytesIO
    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.read()
