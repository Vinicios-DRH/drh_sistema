import io
import re
import json
import unicodedata
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import func

from src import database
from src.models import (
    Militar,
    Obm,
    MilitarObmFuncao,
    PostoGrad,
    Quadro,
    Localidade,
    EstadoCivil,
    Especialidade,
    Destino,
    Situacao,
    Agregacoes,
    GC,
    Punicao,
    Comportamento,
    FuncaoGratificada,
)
COLUMN_SYNONYMS = {
    "nome completo": "nome_completo",
    "nome_completo": "nome_completo",
    "nome de guerra": "nome_guerra",
    "nome_guerra": "nome_guerra",
    "cpf": "cpf",
    "rg": "rg",
    "rg_militar": "rg",
    "nome pai": "nome_pai",
    "nome_pai": "nome_pai",
    "nome mae": "nome_mae",
    "nome mãe": "nome_mae",
    "nome_mae": "nome_mae",
    "matricula": "matricula",
    "matrícula": "matricula",
    "sexo": "sexo",
    "raca": "raca",
    "raça": "raca",
    "data nascimento": "data_nascimento",
    "data_nascimento": "data_nascimento",
    "inclusao": "inclusao",
    "data_inclusao": "inclusao",
    "data inclusao": "inclusao",
    "nascimento": "data_nascimento",
    "email": "email",
    "celular": "celular",
    "cidade": "cidade",
    "estado": "estado",
    "endereco": "endereco",
    "endereço": "endereco",

    "posto_grad": "posto_grad",
    "posto grad": "posto_grad",
    "posto/grad": "posto_grad",
    "quadro": "quadro",
    "localidade": "localidade",
    "estado_civil": "estado_civil",
    "estado civil": "estado_civil",
    "especialidade": "especialidade",
    "destino": "destino",

    # NOVO BLOCO FUNCIONAL
    "situacao": "situacao_principal",
    "situação": "situacao_principal",
    "pronto": "situacao_principal",

    "modalidade": "modalidade",
    "situacao funcional": "modalidade",

    "motivo": "motivo",
    "agregacao": "motivo",
    "agregação": "motivo",
    "agregacoes": "motivo",
    "agregações": "motivo",

    "inicio_periodo": "inicio_periodo",
    "inicio periodo": "inicio_periodo",
    "início período": "inicio_periodo",
    "inicio": "inicio_periodo",
    "início": "inicio_periodo",
    "data_inicio": "inicio_periodo",
    "data início": "inicio_periodo",

    "fim_periodo": "fim_periodo",
    "fim periodo": "fim_periodo",
    "término": "fim_periodo",
    "termino": "fim_periodo",
    "fim": "fim_periodo",
    "data_fim": "fim_periodo",
    "data fim": "fim_periodo",

    "publicacao": "situacao_militar",
    "publicação": "situacao_militar",
    "situacao_militar": "situacao_militar",
    "situação militar": "situacao_militar",
    "bg": "situacao_militar",
    "boletim": "situacao_militar",

    "situacao2": "situacao2",
    "situação2": "situacao2",
    "agregacoes2": "agregacoes2",
    "agregações2": "agregacoes2",
    "gc": "gc",
    "punicao": "punicao",
    "punição": "punicao",
    "comportamento": "comportamento",
    "funcao_gratificada": "funcao_gratificada",
    "função gratificada": "funcao_gratificada",
    "obm": "obm",
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
    "inclusao": "date",
    "email": str,
    "celular": str,
    "cidade": str,
    "estado": str,
    "endereco": str,

    "posto_grad": "fk",
    "quadro": "fk",
    "localidade": "fk",
    "estado_civil": "fk",
    "especialidade": "fk",
    "destino": "fk",

    # NOVOS
    "situacao_principal": str,
    "modalidade": "fk",
    "motivo": "fk",
    "inicio_periodo": "date",
    "fim_periodo": "date",
    "situacao_militar": str,

    "situacao2": "fk",
    "agregacoes2": "fk",
    "gc": "fk",
    "punicao": "fk",
    "comportamento": "fk",
    "funcao_gratificada": "fk",
    "obm": "fk",
}
FK_FIELD_MAP = {
    "posto_grad": {
        "target_attr": "posto_grad_id",
        "model": PostoGrad,
        "lookup_field": "sigla",
        "label": "Posto/Grad",
    },
    "quadro": {
        "target_attr": "quadro_id",
        "model": Quadro,
        "lookup_field": "quadro",
        "label": "Quadro",
    },
    "localidade": {
        "target_attr": "localidade_id",
        "model": Localidade,
        "lookup_field": "sigla",
        "label": "Localidade",
    },
    "estado_civil": {
        "target_attr": "estado_civil",
        "model": EstadoCivil,
        "lookup_field": "estado",
        "label": "Estado civil",
    },
    "especialidade": {
        "target_attr": "especialidade_id",
        "model": Especialidade,
        "lookup_field": "ocupacao",
        "label": "Especialidade",
    },
    "destino": {
        "target_attr": "destino_id",
        "model": Destino,
        "lookup_field": "local",
        "label": "Destino",
    },
    "modalidade": {
        "target_attr": "situacao_id",
        "model": Situacao,
        "lookup_field": "condicao",
        "label": "Modalidade",
    },
    "situacao2": {
        "target_attr": "situacao2_id",
        "model": Situacao,
        "lookup_field": "condicao",
        "label": "Situação 2",
    },
    "motivo": {
        "target_attr": "agregacoes_id",
        "model": Agregacoes,
        "lookup_field": "tipo",
        "label": "Motivo",
    },
    "agregacoes2": {
        "target_attr": "agregacoes2_id",
        "model": Agregacoes,
        "lookup_field": "tipo",
        "label": "Agregações 2",
    },
    "gc": {
        "target_attr": "gc_id",
        "model": GC,
        "lookup_field": "descricao",
        "label": "GC",
    },
    "punicao": {
        "target_attr": "punicao_id",
        "model": Punicao,
        "lookup_field": "sancao",
        "label": "Punição",
    },
    "comportamento": {
        "target_attr": "comportamento_id",
        "model": Comportamento,
        "lookup_field": "conduta",
        "label": "Comportamento",
    },
    "funcao_gratificada": {
        "target_attr": "funcao_gratificada_id",
        "model": FuncaoGratificada,
        "lookup_field": "gratificacao",
        "label": "Função gratificada",
    },
    "obm": {
        "target_attr": "obm",
        "model": Obm,
        "lookup_field": "sigla",
        "label": "OBM",
    },
}

IDENTIFIER_FIELDS = ["cpf", "matricula", "rg", "nome_completo"]

SIMPLE_FIELD_TARGET_MAP = {
    "situacao_principal": "pronto",
    "inicio_periodo": "inicio_periodo",
    "fim_periodo": "fim_periodo",
    "situacao_militar": "situacao_militar",
}


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
    return [c for c in df.columns if c in IMPORTABLE_FIELDS]


def colunas_nao_reconhecidas(df):
    return [c for c in df.columns if c not in IMPORTABLE_FIELDS]


def localizar_militar(row_data: dict):
    cpf = normalizar_cpf(row_data.get("cpf"))
    matricula = normalizar_matricula(row_data.get("matricula"))
    rg = normalizar_rg(row_data.get("rg"))
    nome = normalizar_nome(row_data.get("nome_completo"))

    encontrados = []

    if cpf:
        m = Militar.query.filter(
            func.regexp_replace(func.coalesce(
                Militar.cpf, ""), r"[^0-9]", "", "g") == cpf
        ).first()
        if m:
            encontrados.append(("cpf", m))

    if matricula:
        m = Militar.query.filter(
            func.upper(func.coalesce(Militar.matricula, "")) == matricula
        ).first()
        if m:
            encontrados.append(("matricula", m))

    if rg:
        m = Militar.query.filter(
            func.upper(func.coalesce(Militar.rg, "")) == rg
        ).first()
        if m:
            encontrados.append(("rg", m))

    if nome:
        m = Militar.query.filter(
            func.upper(func.coalesce(Militar.nome_completo, "")) == nome
        ).first()
        if m:
            encontrados.append(("nome_completo", m))

    if not encontrados:
        return None, None, []

    ids = {m.id for _, m in encontrados}
    if len(ids) > 1:
        return None, "conflito_identificacao", encontrados

    return encontrados[0][1], encontrados[0][0], encontrados


def buscar_fk_por_texto(campo_planilha, valor):
    if valor_vazio(valor):
        return None, None

    config = FK_FIELD_MAP.get(campo_planilha)
    if not config:
        return None, f"Campo relacional '{campo_planilha}' não configurado."

    model = config["model"]
    lookup_field = config["lookup_field"]
    label = config["label"]

    valor_norm = normalizar_texto_base(valor)

    registros = model.query.all()

    candidatos = []
    for item in registros:
        texto_item = getattr(item, lookup_field, None)
        if valor_vazio(texto_item):
            continue
        if normalizar_texto_base(texto_item) == valor_norm:
            candidatos.append(item)

    if len(candidatos) == 1:
        return candidatos[0].id, None

    if len(candidatos) > 1:
        return None, f"{label} '{valor}' retornou múltiplos registros."

    return None, f"{label} '{valor}' não encontrado."


def converter_valor_campo(campo, valor):
    if valor_vazio(valor):
        return None

    tipo = IMPORTABLE_FIELDS.get(campo)

    if tipo == "date":
        return to_date(valor)

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

    if campo == "situacao_principal":
        texto = normalizar_texto_base(valor)
        if texto == "pronto":
            return "PRONTO"
        if texto == "agregado":
            return "AGREGADO"
        return limpar_string(valor).upper()

    if tipo == "fk":
        return limpar_string(valor)

    return limpar_string(valor)


def montar_resumo_base():
    return {
        "total_linhas": 0,
        "novos": 0,
        "existentes": 0,
        "complementaveis": 0,
        "conflitos_identificacao": 0,
        "sem_identificador": 0,
        "sugestoes_por_campo": {},
        "inconsistencias_por_tipo": {},
        "preview": [],
        "erros": [],
    }


def adicionar_inconsistencia(resumo, tipo, linha, detalhe):
    resumo["inconsistencias_por_tipo"][tipo] = resumo["inconsistencias_por_tipo"].get(
        tipo, 0) + 1
    resumo["erros"].append({
        "linha": linha,
        "tipo": tipo,
        "erro": detalhe,
    })


def sugerir_campos_faltantes(militar, row_data, campos_selecionados):
    sugestoes = []
    divergentes = []

    for campo in campos_selecionados:
        valor_novo = converter_valor_campo(campo, row_data.get(campo))
        if valor_vazio(valor_novo):
            continue

        if campo in FK_FIELD_MAP and campo != "obm":
            target_attr = FK_FIELD_MAP[campo]["target_attr"]
            valor_atual = getattr(militar, target_attr, None)
        else:
            if campo == "obm":
                continue
            target_attr = SIMPLE_FIELD_TARGET_MAP.get(campo, campo)
            valor_atual = getattr(militar, target_attr, None)

        atual_txt = "" if valor_atual is None else str(valor_atual).strip()
        novo_txt = "" if valor_novo is None else str(valor_novo).strip()

        if valor_vazio(valor_atual):
            sugestoes.append(campo)
        elif atual_txt != novo_txt:
            divergentes.append(campo)

    return sugestoes, divergentes


def analisar_importacao(df, campos_selecionados, modo="misto"):
    resumo = montar_resumo_base()
    preview_limit = 80

    for idx, row in df.iterrows():
        linha_excel = idx + 2
        row_data = row.to_dict()
        resumo["total_linhas"] += 1

        if not any(not valor_vazio(row_data.get(f)) for f in IDENTIFIER_FIELDS):
            resumo["sem_identificador"] += 1
            adicionar_inconsistencia(
                resumo,
                "sem_identificador",
                linha_excel,
                "Linha sem CPF, matrícula, RG ou nome_completo."
            )
            continue

        militar, match_by, encontrados = localizar_militar(row_data)

        if match_by == "conflito_identificacao":
            resumo["conflitos_identificacao"] += 1
            adicionar_inconsistencia(
                resumo,
                "conflito_identificacao",
                linha_excel,
                "A linha apontou para militares diferentes pelos identificadores informados."
            )
            continue

        # ==========================================
        # LÓGICA DE CONTROLE DE MODO (PREVIEW)
        # ==========================================
        if modo == "apenas_atualizar" and militar is None:
            adicionar_inconsistencia(
                resumo,
                "ignorado_por_modo",
                linha_excel,
                "Modo restrito: Apenas Atualizar. O militar não foi encontrado no banco e será ignorado."
            )
            continue

        if modo == "apenas_inserir" and militar is not None:
            adicionar_inconsistencia(
                resumo,
                "ignorado_por_modo",
                linha_excel,
                f"Modo restrito: Apenas Inserir. O militar ({militar.nome_completo}) já existe e será ignorado."
            )
            continue
        # ==========================================

        inconsistencias_linha = []

        for campo in campos_selecionados:
            if campo in FK_FIELD_MAP:
                valor_bruto = row_data.get(campo)
                if not valor_vazio(valor_bruto):
                    fk_id, erro_fk = buscar_fk_por_texto(campo, valor_bruto)
                    if erro_fk:
                        inconsistencias_linha.append(erro_fk)
                        adicionar_inconsistencia(
                            resumo,
                            f"fk_{campo}_invalida",
                            linha_excel,
                            erro_fk
                        )

        if militar is None:
            resumo["novos"] += 1

            if len(resumo["preview"]) < preview_limit:
                resumo["preview"].append({
                    "linha": linha_excel,
                    "tipo": "novo",
                    "match_by": None,
                    "nome": row_data.get("nome_completo"),
                    "cpf": row_data.get("cpf"),
                    "sugestoes": [c for c in campos_selecionados if c != "obm"],
                    "divergencias": [],
                    "inconsistencias": inconsistencias_linha,
                })
            continue

        resumo["existentes"] += 1

        sugestoes, divergencias = sugerir_campos_faltantes(
            militar, row_data, campos_selecionados)

        if sugestoes:
            resumo["complementaveis"] += 1
            for campo in sugestoes:
                resumo["sugestoes_por_campo"][campo] = resumo["sugestoes_por_campo"].get(
                    campo, 0) + 1

        if len(resumo["preview"]) < preview_limit:
            resumo["preview"].append({
                "linha": linha_excel,
                "tipo": "existente",
                "match_by": match_by,
                "nome": militar.nome_completo,
                "cpf": militar.cpf,
                "sugestoes": sugestoes,
                "divergencias": divergencias,
                "inconsistencias": inconsistencias_linha,
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


def importar_dataframe(df, campos_selecionados, modo="misto", regra_atualizacao="complementar", obm_id=None, usuario_id=None):
    relatorio = {
        "inseridos": 0,
        "atualizados": 0,
        "ignorados": 0,
        "erros": [],
        "alteracoes_por_campo": {},
    }

    for idx, row in df.iterrows():
        linha_excel = idx + 2

        try:
            row_data = row.to_dict()

            if not any(not valor_vazio(row_data.get(f)) for f in IDENTIFIER_FIELDS):
                relatorio["ignorados"] += 1
                relatorio["erros"].append({
                    "linha": linha_excel,
                    "tipo": "sem_identificador",
                    "erro": "Linha ignorada por não possuir identificador."
                })
                continue

            militar, match_by, encontrados = localizar_militar(row_data)

            if match_by == "conflito_identificacao":
                relatorio["ignorados"] += 1
                relatorio["erros"].append({
                    "linha": linha_excel,
                    "tipo": "conflito_identificacao",
                    "erro": "Conflito entre identificadores da linha."
                })
                continue

            novo_registro = militar is None

            # ==========================================
            # LÓGICA DE CONTROLE DE MODO (EXECUÇÃO)
            # ==========================================
            if modo == "apenas_atualizar" and novo_registro:
                relatorio["ignorados"] += 1
                relatorio["erros"].append({
                    "linha": linha_excel,
                    "tipo": "ignorado_por_modo",
                    "erro": "Modo restrito: Apenas Atualizar. O militar não foi encontrado no banco."
                })
                continue

            if modo == "apenas_inserir" and not novo_registro:
                relatorio["ignorados"] += 1
                relatorio["erros"].append({
                    "linha": linha_excel,
                    "tipo": "ignorado_por_modo",
                    "erro": f"Modo restrito: Apenas Inserir. O militar ({militar.nome_completo}) já existe."
                })
                continue
            # ==========================================

            if novo_registro:
                militar = Militar()
                database.session.add(militar)
                database.session.flush()

            alterou = False

            for campo in campos_selecionados:
                if campo == "obm":
                    continue

                valor_bruto = row_data.get(campo)
                if valor_vazio(valor_bruto):
                    continue

                # campos relacionais
                if campo in FK_FIELD_MAP:
                    config = FK_FIELD_MAP[campo]
                    target_attr = config["target_attr"]

                    fk_id, erro_fk = buscar_fk_por_texto(campo, valor_bruto)
                    if erro_fk:
                        relatorio["erros"].append({
                            "linha": linha_excel,
                            "tipo": f"fk_{campo}_invalida",
                            "erro": erro_fk
                        })
                        continue

                    valor_atual = getattr(militar, target_attr, None)

                    if regra_atualizacao == "complementar":
                        if valor_vazio(valor_atual):
                            setattr(militar, target_attr, fk_id)
                            alterou = True
                            relatorio["alteracoes_por_campo"][target_attr] = relatorio["alteracoes_por_campo"].get(
                                target_attr, 0) + 1
                    elif regra_atualizacao == "sobrescrever":
                        if valor_atual != fk_id:
                            setattr(militar, target_attr, fk_id)
                            alterou = True
                            relatorio["alteracoes_por_campo"][target_attr] = relatorio["alteracoes_por_campo"].get(
                                target_attr, 0) + 1

                    continue

                # campos simples
                target_attr = SIMPLE_FIELD_TARGET_MAP.get(campo, campo)

                if not hasattr(militar, target_attr):
                    continue

                valor_convertido = converter_valor_campo(campo, valor_bruto)
                if valor_vazio(valor_convertido):
                    continue

                valor_atual = getattr(militar, target_attr, None)

                if regra_atualizacao == "complementar":
                    if valor_vazio(valor_atual):
                        setattr(militar, target_attr, valor_convertido)
                        alterou = True
                        relatorio["alteracoes_por_campo"][target_attr] = relatorio["alteracoes_por_campo"].get(
                            target_attr, 0
                        ) + 1
                elif regra_atualizacao == "sobrescrever":
                    atual_txt = "" if valor_atual is None else str(
                        valor_atual).strip()
                    novo_txt = "" if valor_convertido is None else str(
                        valor_convertido).strip()

                    if atual_txt != novo_txt:
                        setattr(militar, target_attr, valor_convertido)
                        alterou = True
                        relatorio["alteracoes_por_campo"][target_attr] = relatorio["alteracoes_por_campo"].get(
                            target_attr, 0
                        ) + 1

            obm_final = obm_id
            if not obm_final and "obm" in campos_selecionados:
                obm_txt = row_data.get("obm")
                if not valor_vazio(obm_txt):
                    obm_final, erro_obm = buscar_fk_por_texto("obm", obm_txt)
                    if erro_obm:
                        relatorio["erros"].append({
                            "linha": linha_excel,
                            "tipo": "fk_obm_invalida",
                            "erro": erro_obm
                        })

            if obm_final:
                criar_vinculo_obm_se_necessario(militar.id, obm_final)

            if novo_registro:
                militar.usuario_id = usuario_id
                relatorio["inseridos"] += 1
            elif alterou:
                relatorio["atualizados"] += 1
            else:
                relatorio["ignorados"] += 1

        except Exception as e:
            relatorio["erros"].append({
                "linha": linha_excel,
                "tipo": "erro_inesperado",
                "erro": str(e)
            })

    database.session.commit()
    return relatorio


def salvar_historico_importacao(usuario_id, nome_arquivo, modo, campos_selecionados, relatorio, total_linhas, obm_id=None):
    from src.models import ImportacaoMilitarHistorico

    try:
        item = ImportacaoMilitarHistorico(
            usuario_id=usuario_id,
            nome_arquivo=nome_arquivo,
            modo=modo,
            total_linhas=total_linhas,
            inseridos=relatorio.get("inseridos", 0),
            atualizados=relatorio.get("atualizados", 0),
            ignorados=relatorio.get("ignorados", 0),
            obm_id=obm_id,
            campos_json=json.dumps(campos_selecionados, ensure_ascii=False),
            relatorio_json=json.dumps(
                relatorio, ensure_ascii=False, default=str),
        )
        database.session.add(item)
        database.session.commit()
        return item
    except Exception:
        database.session.rollback()
        raise
