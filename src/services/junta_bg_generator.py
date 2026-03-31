from __future__ import annotations

from pathlib import Path
from datetime import timedelta
from zoneinfo import ZoneInfo

from docxtpl import DocxTemplate
from sqlalchemy.orm import joinedload

from src import database
from src.models import JuntaFechamentoBg, Licencas, Militar

MANAUS_TZ = ZoneInfo("America/Manaus")


def fmt_data_br(dt):
    if not dt:
        return ""
    return dt.strftime("%d/%m/%Y")


def um_dia_apos(dt):
    if not dt:
        return ""
    return fmt_data_br(dt + timedelta(days=1))


def safe_getattr(obj, attr, default=""):
    try:
        value = getattr(obj, attr, default)
        return value if value is not None else default
    except Exception:
        return default


def numero_por_extenso(n: int) -> str:
    unidades = {
        0: "zero", 1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
        6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
        11: "onze", 12: "doze", 13: "treze", 14: "quatorze", 15: "quinze",
        16: "dezesseis", 17: "dezessete", 18: "dezoito", 19: "dezenove"
    }
    dezenas = {
        20: "vinte", 30: "trinta", 40: "quarenta", 50: "cinquenta",
        60: "sessenta", 70: "setenta", 80: "oitenta", 90: "noventa"
    }
    centenas = {
        100: "cem", 200: "duzentos", 300: "trezentos", 400: "quatrocentos",
        500: "quinhentos", 600: "seiscentos", 700: "setecentos",
        800: "oitocentos", 900: "novecentos"
    }

    if n < 0:
        return str(n)

    if n in unidades:
        return unidades[n]

    if n < 100:
        dez = (n // 10) * 10
        resto = n % 10
        if resto == 0:
            return dezenas[dez]
        return f"{dezenas[dez]} e {unidades[resto]}"

    if n == 100:
        return "cem"

    if n < 1000:
        cent = (n // 100) * 100
        resto = n % 100
        cent_texto = "cento" if cent == 100 else centenas[cent]
        if resto == 0:
            return cent_texto
        return f"{cent_texto} e {numero_por_extenso(resto)}"

    return str(n)


def montar_identidade_militar(lic):
    militar = lic.militar
    posto_grad = safe_getattr(safe_getattr(
        militar, "posto_grad", None), "sigla", "")
    quadro = safe_getattr(safe_getattr(militar, "quadro", None), "quadro", "")
    nome = safe_getattr(militar, "nome_completo", "")
    rg = safe_getattr(militar, "rg", "") or safe_getattr(
        militar, "identidade", "")

    posto_quadro = f"{posto_grad} {quadro}".strip()

    return {
        "posto_grad_quadro": posto_quadro,
        "nome_completo": nome,
        "rg": rg,
    }


def montar_item_licenca(lic):
    base = montar_identidade_militar(lic)

    base.update({
        "qtd_dias": lic.qtd_dias,
        "qtd_dias_extenso": numero_por_extenso(lic.qtd_dias),
        "data_inicio": fmt_data_br(lic.data_inicio),
        "data_fim": fmt_data_br(lic.data_fim),
        "um_dia_depois_do_termino": um_dia_apos(lic.data_fim),
        "recomendacoes": lic.observacao or "",
        "restricoes": lic.observacao or "",
        "sessao": lic.sessao or "",
    })
    return base


def agrupar_por_secao(licencas):
    grupos = {
        "lts": [],
        "ltspf": [],
        "lm": [],
        "apto_recom": [],
        "apto_restr": [],
        "apto": [],
        "agregado": [],
    }

    for lic in licencas:
        item = montar_item_licenca(lic)

        if lic.tipo_licenca == "LTS":
            grupos["lts"].append(item)
        elif lic.tipo_licenca == "LTSPF":
            grupos["ltspf"].append(item)
        elif lic.tipo_licenca == "LM":
            grupos["lm"].append(item)
        elif lic.tipo_licenca == "APTO_RECOM":
            grupos["apto_recom"].append(item)
        elif lic.tipo_licenca == "APTO_RESTR":
            grupos["apto_restr"].append(item)
        elif lic.tipo_licenca == "APTO":
            grupos["apto"].append(item)
        elif lic.tipo_licenca == "AGREGADO":
            grupos["agregado"].append(item)

    return grupos


def gerar_nota_bg_docx(fechamento_id: int, commit_db: bool = True) -> str:
    fechamento = (
        JuntaFechamentoBg.query
        .options(
            joinedload(JuntaFechamentoBg.licencas)
            .joinedload(Licencas.militar)
            .joinedload(Militar.posto_grad),
            joinedload(JuntaFechamentoBg.licencas)
            .joinedload(Licencas.militar)
            .joinedload(Militar.quadro),
        )
        .get(fechamento_id)
    )

    if not fechamento:
        raise ValueError("Fechamento BG não encontrado.")

    licencas = (
        Licencas.query
        .filter_by(fechamento_bg_id=fechamento.id)
        .options(
            joinedload(Licencas.militar).joinedload(Militar.posto_grad),
            joinedload(Licencas.militar).joinedload(Militar.quadro),
        )
        .order_by(
            Licencas.tipo_licenca.asc(),
            Licencas.created_at.asc(),
            Licencas.id.asc()
        )
        .all()
    )

    grupos = agrupar_por_secao(licencas)

    template_path = Path("src/template/modelo_junta.docx")
    output_dir = Path("src/static/junta_bg")
    output_dir.mkdir(parents=True, exist_ok=True)

    ano = fechamento.data_referencia.year
    nome_arquivo = f"nota_bg_{fechamento.nota_bg.replace('/', '-')}_{fechamento.id}.docx"
    output_path = output_dir / nome_arquivo

    doc = DocxTemplate(str(template_path))
    context = {
        "nota_bg": fechamento.nota_bg,
        "ano_atual": ano,
        "sessao": fechamento.sessao,
        "data_sessao": fmt_data_br(fechamento.data_referencia),

        "lts": grupos["lts"],
        "ltspf": grupos["ltspf"],
        "lm": grupos["lm"],
        "apto_recom": grupos["apto_recom"],
        "apto_restr": grupos["apto_restr"],
        "apto": grupos["apto"],
        "agregado": grupos["agregado"],

        "tem_lts": len(grupos["lts"]) > 0,
        "tem_ltspf": len(grupos["ltspf"]) > 0,
        "tem_lm": len(grupos["lm"]) > 0,
        "tem_apto_recom": len(grupos["apto_recom"]) > 0,
        "tem_apto_restr": len(grupos["apto_restr"]) > 0,
        "tem_apto": len(grupos["apto"]) > 0,
        "tem_agregado": len(grupos["agregado"]) > 0,
    }

    doc.render(context)
    doc.save(str(output_path))

    fechamento.arquivo_docx = nome_arquivo
    if commit_db:
        database.session.commit()

    return nome_arquivo
