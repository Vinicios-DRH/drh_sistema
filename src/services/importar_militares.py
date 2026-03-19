import io
import re
import unicodedata
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import func

from src import database
from src.models import Militar, Obm, MilitarObmFuncao


COLUMN_SYNONYMS = {
    "nome completo": "nome_completo",
    "nome_completo": "nome_completo",
    "nome de guerra": "nome_guerra",
    "nome_guerra": "nome_guerra",
    "cpf": "cpf",
    "rg": "rg",
    "nome pai": "nome_pai",
    "nome_pai": "nome_pai",
    "nome mae": "nome_mae",
    "nome mãe": "nome_mae",
    "nome_mae": "nome_mae",
    "matricula": "matricula",
    "matrícula": "matricula",
    "obm": "obm",
    "posto_grad": "posto_grad",
    "posto grad": "posto_grad",
    "quadro": "quadro",
    "sexo": "sexo",
    "raca": "raca",
    "raça": "raca",
    "data nascimento": "data_nascimento",
    "data_nascimento": "data_nascimento",
    "nascimento": "data_nascimento",
    "email": "email",
    "celular": "celular",
    "cidade": "cidade",
    "estado": "estado",
    "endereco": "endereco",
    "endereço": "endereco",
    "nome de pai": "nome_pai",
    "nome de mae": "nome_mae",
}

IMPORTABLE_FIELDS = {
    "nome_completo": str,
    "nome_guerra": str,
    "cpf": str,
    "rg": str,
    "nome_pai": str,
    "nome_mae": str,
    "matricula": str,
    "sexo": str,
    "raca": str,
    "data_nascimento": "date",
    "email": str,
    "celular": str,
    "cidade": str,
    "estado": str,
    "endereco": str,
}

IDENTIFIER_FIELDS = ["cpf", "matricula", "rg", "nome_completo"]


def normalizar_texto_base(valor: str) -> str:
    if valor is None:
        return ""
    valor = str(valor).strip().lower()
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    valor = re.sub(r"\s+", " ", valor)
    return valor


def normalizar_nome_coluna(nome: str) -> str:
    base = normalizar_texto_base(nome).replace("-", " ").replace("/", " ")
    base = re.sub(r"\s+", " ", base).strip()
    return COLUMN_SYNONYMS.get(base, base.replace(" ", "_"))


def valor_vazio(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, float) and pd.isna(valor):
        return True
    texto = str(valor).strip()
    return texto == "" or texto.lower() in {"nan", "none", "null", "nat"}


def limpar_string(valor):
    if valor_vazio(valor):
        return None
    return str(valor).strip()


def normalizar_cpf(valor):
    if valor_vazio(valor):
        return None
    digits = re.sub(r"\D", "", str(valor))
    return digits or None


def normalizar_nome(valor):
    if valor_vazio(valor):
        return None
    return re.sub(r"\s+", " ", str(valor).strip()).upper()


def normalizar_rg(valor):
    if valor_vazio(valor):
        return None
    return re.sub(r"\s+", "", str(valor).strip()).upper()


def normalizar_matricula(valor):
    if valor_vazio(valor):
        return None
    return re.sub(r"\s+", "", str(valor).strip()).upper()


def to_date(valor):
    if valor_vazio(valor):
        return None

    if isinstance(valor, datetime):
        return valor.date()

    if isinstance(valor, date):
        return valor

    try:
        convertido = pd.to_datetime(valor, dayfirst=True, errors="coerce")
        if pd.isna(convertido):
            return None
        return convertido.date()
    except Exception:
        return None


def to_decimal(valor):
    if valor_vazio(valor):
        return None
    try:
        texto = str(valor).strip().replace(",", ".")
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def converter_valor_campo(campo, valor):
    if valor_vazio(valor):
        return None

    tipo = IMPORTABLE_FIELDS.get(campo)

    if tipo == "date":
        return to_date(valor)

    if tipo == "decimal":
        return to_decimal(valor)

    if tipo == bool:
        texto = str(valor).strip().lower()
        return texto in {"sim", "true", "1", "s", "yes"}

    if tipo == int:
        try:
            return int(float(str(valor).replace(",", ".")))
        except Exception:
            return None

    if campo == "cpf":
        return normalizar_cpf(valor)

    if campo == "nome_completo":
        return normalizar_nome(valor)

    if campo == "nome_guerra":
        return limpar_string(valor).upper()

    if campo == "matricula":
        return normalizar_matricula(valor)

    if campo == "rg":
        return normalizar_rg(valor)

    return limpar_string(valor)


def ler_planilha(file_storage):
    nome = (file_storage.filename or "").lower()

    conteudo = file_storage.read()
    buffer = io.BytesIO(conteudo)

    if nome.endswith(".csv"):
        try:
            df = pd.read_csv(buffer, dtype=str)
        except UnicodeDecodeError:
            buffer.seek(0)
            df = pd.read_csv(buffer, dtype=str, encoding="latin1")
    else:
        df = pd.read_excel(buffer, dtype=str)

    df.columns = [normalizar_nome_coluna(c) for c in df.columns]
    df = df.where(pd.notnull(df), None)

    return df


def colunas_reconhecidas(df):
    return [c for c in df.columns if c in IMPORTABLE_FIELDS or c == "obm"]


def colunas_nao_reconhecidas(df):
    return [c for c in df.columns if c not in IMPORTABLE_FIELDS and c != "obm"]


def localizar_militar(row_data: dict):
    cpf = normalizar_cpf(row_data.get("cpf"))
    matricula = normalizar_matricula(row_data.get("matricula"))
    rg = normalizar_rg(row_data.get("rg"))
    nome = normalizar_nome(row_data.get("nome_completo"))

    if cpf:
        militar = Militar.query.filter(
            func.regexp_replace(func.coalesce(
                Militar.cpf, ""), r"[^0-9]", "", "g") == cpf
        ).first()
        if militar:
            return militar

    if matricula:
        militar = Militar.query.filter(
            func.upper(func.coalesce(Militar.matricula, "")) == matricula
        ).first()
        if militar:
            return militar

    if rg:
        militar = Militar.query.filter(
            func.upper(func.coalesce(Militar.rg, "")) == rg
        ).first()
        if militar:
            return militar

    if nome:
        militar = Militar.query.filter(
            func.upper(func.coalesce(Militar.nome_completo, "")) == nome
        ).first()
        if militar:
            return militar

    return None


def analisar_importacao(df, campos_selecionados):
    resumo = {
        "total_linhas": 0,
        "novos": 0,
        "existentes": 0,
        "complementaveis": 0,
        "sem_identificador": 0,
        "sugestoes_por_campo": {},
        "preview": [],
        "erros": [],
    }

    preview_limit = 50

    for idx, row in df.iterrows():
        linha_excel = idx + 2
        row_data = row.to_dict()
        resumo["total_linhas"] += 1

        tem_identificador = any(not valor_vazio(row_data.get(f))
                                for f in IDENTIFIER_FIELDS)
        if not tem_identificador:
            resumo["sem_identificador"] += 1
            resumo["erros"].append({
                "linha": linha_excel,
                "erro": "Linha sem CPF, matrícula, RG ou nome_completo."
            })
            continue

        militar = localizar_militar(row_data)

        if militar is None:
            resumo["novos"] += 1
            if len(resumo["preview"]) < preview_limit:
                resumo["preview"].append({
                    "linha": linha_excel,
                    "tipo": "novo",
                    "nome_planilha": row_data.get("nome_completo"),
                    "cpf_planilha": row_data.get("cpf"),
                    "campos_sugeridos": list(campos_selecionados),
                    "campos_alterados": [],
                })
            continue

        resumo["existentes"] += 1

        campos_sugeridos = []
        campos_diferentes = []

        for campo in campos_selecionados:
            valor_novo = converter_valor_campo(campo, row_data.get(campo))
            if valor_vazio(valor_novo):
                continue

            valor_atual = getattr(militar, campo, None)

            atual_normalizado = "" if valor_atual is None else str(
                valor_atual).strip()
            novo_normalizado = "" if valor_novo is None else str(
                valor_novo).strip()

            if valor_vazio(valor_atual):
                campos_sugeridos.append(campo)
                resumo["sugestoes_por_campo"][campo] = resumo["sugestoes_por_campo"].get(
                    campo, 0) + 1
            elif atual_normalizado != novo_normalizado:
                campos_diferentes.append(campo)

        if campos_sugeridos:
            resumo["complementaveis"] += 1

        if len(resumo["preview"]) < preview_limit:
            resumo["preview"].append({
                "linha": linha_excel,
                "tipo": "existente",
                "nome_banco": militar.nome_completo,
                "cpf_banco": militar.cpf,
                "campos_sugeridos": campos_sugeridos,
                "campos_alterados": campos_diferentes,
            })

    return resumo


def criar_vinculo_obm_se_necessario(militar_id, obm_id):
    if not obm_id:
        return

    vinculo_ativo = MilitarObmFuncao.query.filter_by(
        militar_id=militar_id,
        data_fim=None
    ).first()

    if vinculo_ativo:
        if vinculo_ativo.obm_id == obm_id:
            return
        vinculo_ativo.data_fim = datetime.utcnow()

    novo_vinculo = MilitarObmFuncao(
        militar_id=militar_id,
        obm_id=obm_id,
        tipo=1
    )
    database.session.add(novo_vinculo)


def importar_dataframe(df, campos_selecionados, modo="complementar", obm_id=None, usuario_id=None):
    relatorio = {
        "inseridos": 0,
        "atualizados": 0,
        "ignorados": 0,
        "erros": [],
    }

    for idx, row in df.iterrows():
        linha_excel = idx + 2

        try:
            row_data = row.to_dict()

            tem_identificador = any(not valor_vazio(row_data.get(f))
                                    for f in IDENTIFIER_FIELDS)
            if not tem_identificador:
                relatorio["ignorados"] += 1
                relatorio["erros"].append({
                    "linha": linha_excel,
                    "erro": "Linha ignorada por não possuir identificador."
                })
                continue

            militar = localizar_militar(row_data)

            if militar is None:
                militar = Militar()

                for campo in campos_selecionados:
                    if not hasattr(militar, campo):
                        continue

                    valor_convertido = converter_valor_campo(
                        campo, row_data.get(campo))
                    if valor_vazio(valor_convertido):
                        continue

                    setattr(militar, campo, valor_convertido)

                militar.usuario_id = usuario_id
                database.session.add(militar)
                database.session.flush()

                if obm_id:
                    criar_vinculo_obm_se_necessario(militar.id, obm_id)

                relatorio["inseridos"] += 1
                continue

            alterou = False

            for campo in campos_selecionados:
                if not hasattr(militar, campo):
                    continue

                valor_convertido = converter_valor_campo(
                    campo, row_data.get(campo))
                if valor_vazio(valor_convertido):
                    continue

                valor_atual = getattr(militar, campo, None)

                if modo == "complementar":
                    if valor_vazio(valor_atual):
                        setattr(militar, campo, valor_convertido)
                        alterou = True

                elif modo == "sobrescrever":
                    atual_normalizado = "" if valor_atual is None else str(
                        valor_atual).strip()
                    novo_normalizado = "" if valor_convertido is None else str(
                        valor_convertido).strip()

                    if atual_normalizado != novo_normalizado:
                        setattr(militar, campo, valor_convertido)
                        alterou = True

            if obm_id:
                criar_vinculo_obm_se_necessario(militar.id, obm_id)

            if alterou:
                relatorio["atualizados"] += 1
            else:
                relatorio["ignorados"] += 1

        except Exception as e:
            relatorio["erros"].append({
                "linha": linha_excel,
                "erro": str(e)
            })

    database.session.commit()
    return relatorio
