import io
import re
import unicodedata
from collections import defaultdict

import pandas as pd
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from src import database
from src.models import Militar
from src.services.format_planilha import formatar_planilha


militares_bp = Blueprint(
    "militares_importacao",
    __name__,
    url_prefix="/militares"
)


COLUNAS_NOME_ACEITAS = {
    "nome",
    "nome completo",
    "nome_completo",
    "militar",
    "bombeiro militar",
    "bombeiro_militar",
}

COLUNAS_POSTO_ACEITAS = {
    "posto",
    "posto grad",
    "posto_grad",
    "posto graduação",
    "posto graduacao",
    "posto/grad",
    "posto/graduação",
    "posto/graduacao",
}


def normalizar_texto(valor):
    """
    Remove acentos, pontuações, espaços extras e converte para maiúsculo.

    Exemplo:
        "  João  da Silva " -> "JOAO DA SILVA"
        "1º SGT BM"         -> "1 SGT BM"
    """
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    # Troca pontuação por espaço.
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)

    # Remove espaços duplicados.
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


def normalizar_posto(valor):
    texto = normalizar_texto(valor)

    # Remove o sufixo BM caso exista no banco e não exista no CSV.
    partes = texto.split()

    if partes and partes[-1] == "BM":
        partes.pop()

    texto = " ".join(partes)

    equivalencias = {
        "ALUNO OFICIAL": "AL OF",
        "AL OFICIAL": "AL OF",
        "ALUNO SOLDADO": "AL SD",
        "AL SOLDADO": "AL SD",

        "SOLDADO": "SD",
        "CABO": "CB",

        "TERCEIRO SGT": "3 SGT",
        "TERCEIRO SARGENTO": "3 SGT",

        "SEGUNDO SGT": "2 SGT",
        "SEGUNDO SARGENTO": "2 SGT",

        "PRIMEIRO SGT": "1 SGT",
        "PRIMEIRO SARGENTO": "1 SGT",

        "SUB TEN": "SUBTEN",
        "SUBTENENTE": "SUBTEN",

        "SEGUNDO TEN": "2 TEN",
        "SEGUNDO TENENTE": "2 TEN",

        "PRIMEIRO TEN": "1 TEN",
        "PRIMEIRO TENENTE": "1 TEN",

        "CAPITAO": "CAP",
        "MAJOR": "MAJ",
        "TEN CEL": "TC",
        "TENENTE CORONEL": "TC",
        "CORONEL": "CEL",
    }

    return equivalencias.get(texto, texto)


def limpar_documento(valor):
    """
    Mantém o documento como texto, evitando valores como 123456.0.
    """
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def obter_nome_posto(militar):
    if not militar.posto_grad:
        return ""

    posto = militar.posto_grad

    for atributo in [
        "nome",
        "sigla",
        "descricao",
        "posto_grad",
    ]:
        valor = getattr(posto, atributo, None)

        if valor:
            return str(valor).strip()

    return ""


def localizar_coluna(dataframe, nomes_aceitos):
    """
    Localiza uma coluna mesmo quando ela possui diferenças de acentuação,
    espaços ou uso de underline.
    """
    colunas_normalizadas = {}

    for coluna in dataframe.columns:
        nome_normalizado = normalizar_texto(
            str(coluna).replace("_", " ")
        )
        colunas_normalizadas[nome_normalizado] = coluna

    for nome_aceito in nomes_aceitos:
        nome_normalizado = normalizar_texto(
            nome_aceito.replace("_", " ")
        )

        if nome_normalizado in colunas_normalizadas:
            return colunas_normalizadas[nome_normalizado]

    return None


def ler_csv_upload(arquivo):
    """
    Lê o CSV enviado, priorizando o padrão utilizado pelo arquivo do TAF:
    UTF-8 com BOM e separador por ponto e vírgula.
    """
    conteudo = arquivo.read()

    if not conteudo:
        raise ValueError("O arquivo enviado está vazio.")

    tentativas = [
        {
            "encoding": "utf-8-sig",
            "sep": ";",
        },
        {
            "encoding": "utf-8",
            "sep": ";",
        },
        {
            "encoding": "latin-1",
            "sep": ";",
        },
        {
            "encoding": "cp1252",
            "sep": ";",
        },
    ]

    ultimo_erro = None

    for tentativa in tentativas:
        try:
            texto = conteudo.decode(tentativa["encoding"])

            dataframe = pd.read_csv(
                io.StringIO(texto),
                sep=tentativa["sep"],
                dtype=str,
                keep_default_na=False,
            )

            if len(dataframe.columns) > 1:
                return dataframe

        except (
            UnicodeDecodeError,
            pd.errors.ParserError,
        ) as erro:
            ultimo_erro = erro

    # Última tentativa: detectar o separador automaticamente.
    for codificacao in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            texto = conteudo.decode(codificacao)

            dataframe = pd.read_csv(
                io.StringIO(texto),
                sep=None,
                engine="python",
                dtype=str,
                keep_default_na=False,
            )

            if len(dataframe.columns) > 1:
                return dataframe

        except (
            UnicodeDecodeError,
            pd.errors.ParserError,
        ) as erro:
            ultimo_erro = erro

    raise ValueError(
        f"Não foi possível ler o CSV. Erro: {ultimo_erro}"
    )


def preparar_indice_militares(militares):
    """
    Cria um índice por nome normalizado para evitar uma consulta ao banco
    para cada linha do CSV.
    """
    indice = defaultdict(list)

    for militar in militares:
        nome_normalizado = normalizar_texto(militar.nome_completo)

        if nome_normalizado:
            indice[nome_normalizado].append(militar)

    return indice


def filtrar_por_posto(candidatos, posto_csv):
    posto_normalizado = normalizar_posto(posto_csv)

    if not posto_normalizado:
        return candidatos

    encontrados = []

    for militar in candidatos:
        posto_banco = normalizar_posto(
            obter_nome_posto(militar)
        )

        if posto_banco == posto_normalizado:
            encontrados.append(militar)

    return encontrados


@militares_bp.route("/identificar-csv", methods=["GET", "POST"])
def identificar_militares_csv():
    if request.method == "GET":
        return render_template(
            "militares/identificar_csv.html"
        )

    arquivo = request.files.get("arquivo_csv")

    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo CSV.", "warning")
        return redirect(
            url_for("militares_importacao.identificar_militares_csv")
        )

    if not arquivo.filename.lower().endswith(".csv"):
        flash("O arquivo precisa estar no formato CSV.", "danger")
        return redirect(
            url_for("militares_importacao.identificar_militares_csv")
        )

    try:
        dataframe = ler_csv_upload(arquivo)

        if dataframe.empty:
            flash("O arquivo CSV não possui registros.", "warning")
            return redirect(
                url_for(
                    "militares_importacao.identificar_militares_csv"
                )
            )

        coluna_nome = localizar_coluna(
            dataframe,
            COLUNAS_NOME_ACEITAS,
        )

        coluna_posto = localizar_coluna(
            dataframe,
            COLUNAS_POSTO_ACEITAS,
        )

        if not coluna_nome:
            flash(
                "Não foi localizada uma coluna de nome no CSV. "
                "Utilize, por exemplo, 'nome' ou 'nome_completo'.",
                "danger",
            )
            return redirect(
                url_for(
                    "militares_importacao.identificar_militares_csv"
                )
            )

        if not coluna_posto:
            flash(
                "Não foi localizada uma coluna de posto/graduação "
                "no CSV. Utilize, por exemplo, 'posto_grad'.",
                "danger",
            )
            return redirect(
                url_for(
                    "militares_importacao.identificar_militares_csv"
                )
            )

        # Carrega somente os campos necessários e o relacionamento de posto.
        militares = (
            database.session.query(Militar)
            .options(
                joinedload(Militar.posto_grad)
            )
            .filter(
                Militar.nome_completo.isnot(None),
                or_(
                    Militar.inativo.is_(False),
                    Militar.inativo.is_(None),
                ),
            )
            .all()
        )

        indice_militares = preparar_indice_militares(militares)

        resultados = []
        nao_encontrados = []
        ambiguidades = []

        for numero_linha, linha in dataframe.iterrows():
            nome_csv = str(linha.get(coluna_nome, "")).strip()
            posto_csv = str(linha.get(coluna_posto, "")).strip()

            registro_base = {
                "linha_csv": numero_linha + 2,
                **linha.to_dict(),
            }

            if not nome_csv:
                resultado = {
                    **registro_base,
                    "status": "NOME VAZIO",
                    "posto_grad_banco": "",
                    "nome_completo_banco": "",
                    "cpf": "",
                    "rg": "",
                    "matricula": "",
                    "observacao": "A linha não possui nome.",
                }

                resultados.append(resultado)
                nao_encontrados.append(resultado)
                continue

            nome_normalizado = normalizar_texto(nome_csv)

            candidatos = indice_militares.get(
                nome_normalizado,
                [],
            )

            if not candidatos:
                resultado = {
                    **registro_base,
                    "status": "NÃO ENCONTRADO",
                    "posto_grad_banco": "",
                    "nome_completo_banco": "",
                    "cpf": "",
                    "rg": "",
                    "matricula": "",
                    "observacao": (
                        "Nenhum militar encontrado pelo nome completo."
                    ),
                }

                resultados.append(resultado)
                nao_encontrados.append(resultado)
                continue

            # Se houver mais de um militar com o mesmo nome,
            # tenta resolver usando o posto do CSV.
            candidatos_posto = filtrar_por_posto(
                candidatos,
                posto_csv,
            )

            if len(candidatos_posto) == 1:
                militar = candidatos_posto[0]
                status = "ENCONTRADO"

            elif len(candidatos) == 1:
                militar = candidatos[0]

                posto_banco = normalizar_posto(
                    obter_nome_posto(militar)
                )

                posto_arquivo = normalizar_posto(
                    posto_csv
                )

                if (
                    posto_arquivo
                    and posto_banco
                    and posto_arquivo != posto_banco
                ):
                    status = "ENCONTRADO - POSTO DIVERGENTE"
                else:
                    status = "ENCONTRADO"

            else:
                resultado = {
                    **registro_base,
                    "status": "AMBÍGUO",
                    "posto_grad_banco": "",
                    "nome_completo_banco": "",
                    "cpf": "",
                    "rg": "",
                    "matricula": "",
                    "observacao": (
                        f"Foram encontrados {len(candidatos)} "
                        "militares com esse nome."
                    ),
                }

                resultados.append(resultado)
                ambiguidades.append(resultado)
                continue

            resultado = {
                **registro_base,
                "status": status,
                "posto_grad_banco": obter_nome_posto(militar),
                "nome_completo_banco": militar.nome_completo or "",
                "cpf": limpar_documento(militar.cpf),
                "rg": limpar_documento(militar.rg),
                "matricula": limpar_documento(militar.matricula),
                "observacao": (
                    "Posto do CSV diferente do posto cadastrado."
                    if status == "ENCONTRADO - POSTO DIVERGENTE"
                    else ""
                ),
            }

            resultados.append(resultado)

        df_resultado = pd.DataFrame(resultados)

        df_nao_encontrados = pd.DataFrame(
            nao_encontrados,
            columns=df_resultado.columns,
        )

        df_ambiguidades = pd.DataFrame(
            ambiguidades,
            columns=df_resultado.columns,
        )

        arquivo_excel = io.BytesIO()

        with pd.ExcelWriter(
            arquivo_excel,
            engine="openpyxl",
        ) as writer:
            df_resultado.to_excel(
                writer,
                sheet_name="Resultado",
                index=False,
            )

            df_nao_encontrados.to_excel(
                writer,
                sheet_name="Nao_encontrados",
                index=False,
            )

            df_ambiguidades.to_excel(
                writer,
                sheet_name="Ambiguidades",
                index=False,
            )

            formatar_planilha(
                writer.book["Resultado"]
            )
            formatar_planilha(
                writer.book["Nao_encontrados"]
            )
            formatar_planilha(
                writer.book["Ambiguidades"]
            )

        arquivo_excel.seek(0)

        return send_file(
            arquivo_excel,
            as_attachment=True,
            download_name="identificacao_militares.xlsx",
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    except ValueError as erro:
        flash(str(erro), "danger")

    except Exception as erro:
        database.session.rollback()

        # Substitua pelo seu logger.
        print(f"Erro ao identificar militares: {erro}")

        flash(
            "Ocorreu um erro ao processar o arquivo CSV.",
            "danger",
        )

    return redirect(
        url_for("militares_importacao.identificar_militares_csv")
    )