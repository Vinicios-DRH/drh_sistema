"""Camada de apoio ao wizard web de importação de militares (rotas em
src/routes/militares_importacao.py).

Enquanto `src.services.importar_militares` é o motor da importação em si
(leitura de planilha, mapeamento de campos, gravação no banco), este módulo
cuida do que é específico do fluxo HTTP em 3 telas (analisar → reanalisar →
confirmar): serializar o DataFrame entre requisições, montar o contexto
repetido nas telas de prévia e guardar/ler o resultado da última importação
na sessão.
"""
import base64
import io
import json

import pandas as pd

from src.models import Obm
from src.services.importar_militares import (
    analisar_importacao,
    colunas_nao_reconhecidas,
    colunas_reconhecidas,
)

SESSAO_RELATORIO = "ultimo_relatorio_importacao_militares"
SESSAO_NOME_ARQUIVO = "ultimo_nome_arquivo_importacao_militares"
SESSAO_MODO = "ultimo_modo_importacao_militares"
SESSAO_CAMPOS = "ultimo_campos_importacao_militares"


def dataframe_para_payload(df: pd.DataFrame) -> str:
    """Serializa o DataFrame lido do upload para trafegar (num campo hidden)
    entre as telas de análise, reanálise e confirmação da importação."""
    json_str = df.to_json(orient="records", force_ascii=False)
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


def payload_para_dataframe(payload_b64: str) -> pd.DataFrame:
    """Reconstrói o DataFrame a partir do payload gerado por `dataframe_para_payload`.

    Levanta ValueError com mensagem amigável se o payload estiver ausente ou
    corrompido — quem chama decide como exibir isso ao usuário (e se loga).
    """
    if not payload_b64:
        raise ValueError("Dados da planilha não encontrados.")

    try:
        json_bytes = base64.b64decode(payload_b64.encode("utf-8"))
        json_str = json_bytes.decode("utf-8")
        return pd.read_json(io.StringIO(json_str), orient="records", dtype=False)
    except Exception as exc:
        raise ValueError(f"Erro ao ler os dados da planilha: {exc}") from exc


def montar_contexto_confirmacao(df, campos_selecionados, modo, nome_arquivo, payload_b64=None):
    """Monta o contexto compartilhado pelas telas de análise e reanálise
    (`militares/importar_confirmacao.html`), que mostram a prévia de quantos
    militares seriam inseridos/atualizados/ignorados com os campos escolhidos.
    """
    return {
        "colunas_ok": colunas_reconhecidas(df),
        "colunas_invalidas": colunas_nao_reconhecidas(df),
        "resumo": analisar_importacao(df, campos_selecionados, modo=modo),
        "obms": Obm.query.order_by(Obm.sigla).all(),
        "payload_b64": payload_b64 if payload_b64 is not None else dataframe_para_payload(df),
        "campos_preselecionados": campos_selecionados,
        "nome_arquivo": nome_arquivo,
        "total_colunas": len(df.columns),
        "modo": modo,
    }


def salvar_resultado_na_sessao(session, relatorio, nome_arquivo, modo, campos_selecionados):
    """Guarda o relatório da última importação na sessão, pra tela de resultado
    poder ser recarregada (F5, voltar) sem perder o que acabou de acontecer."""
    session[SESSAO_RELATORIO] = relatorio
    session[SESSAO_NOME_ARQUIVO] = nome_arquivo
    session[SESSAO_MODO] = modo
    session[SESSAO_CAMPOS] = campos_selecionados


def obter_resultado_da_sessao(session):
    return {
        "relatorio": session.get(SESSAO_RELATORIO),
        "nome_arquivo": session.get(SESSAO_NOME_ARQUIVO),
        "modo": session.get(SESSAO_MODO),
        "campos_selecionados": session.get(SESSAO_CAMPOS, []),
    }


def parse_json_seguro(texto):
    """json.loads que nunca levanta: devolve {} se o texto for vazio ou inválido."""
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except Exception:
        return {}
