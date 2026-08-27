"""Consultas usadas pelas telas de listagem de situação funcional irmãs da
LTS: militares agregados, à disposição e em licença especial.

A regra de status de cada uma já existe em src.decorators.business_logic
(processar_militares_agregados/a_disposicao/le) — este módulo é só sobre
montar a listagem (com eager loading) para o template.
"""
from collections import Counter
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src import database
from src.models import LicencaEspecial, Militar, MilitaresADisposicao, MilitaresAgregados
from src.querys import _periodo_vigente_expr
from src.services.militar_situacao_service import ids_alto_comando_excluidos_de_agregado_disposicao

DIAS_ALERTA_VENCIMENTO = 30
QTD_DESTINOS_NO_RANKING = 5

_RELACIONAMENTOS_COMUNS = ("militar", "posto_grad", "quadro", "destino", "modalidade", "publicacao_bg")


def _ids_mais_recentes_por_militar(model):
    """Id do registro mais novo (maior id) de cada militar_id — mesmo
    critério que já decide qual é "o registro atual" de um militar em
    sincronizar_blocos_funcionais (militar_situacao_service.py). Usado pra
    telas de listagem mostrarem um único registro por militar, mesmo tendo
    várias linhas de histórico no banco pra ele."""
    linhas = (
        database.session.query(
            model.id,
            func.row_number().over(
                partition_by=model.militar_id,
                order_by=model.id.desc(),
            ).label("linha"),
        )
        .subquery()
    )
    return database.session.query(linhas.c.id).filter(linhas.c.linha == 1)


def _ids_militares_com_registro_vigente(model, campo_inicio, campo_fim):
    """Ids de militar (deduplicado, sem o alto comando) com um registro
    vigente por data na tabela filha informada — mesmo critério de "Vigente"
    dos dashboards de Agregados/À Disposição. Usado pra qualquer tela que
    precise filtrar/contar "quem está à disposição (ou agregado) hoje" bater
    com o mesmo número dessas telas, em vez de confiar no campo Situação da
    ficha (que só é atualizado quando o operador salva a ficha, e não cobre
    o caso de alguém Agregado E à disposição ao mesmo tempo)."""
    query = (
        database.session.query(model.militar_id)
        .join(Militar, Militar.id == model.militar_id)
        .filter(Militar.inativo.is_(False))
        .filter(model.id.in_(_ids_mais_recentes_por_militar(model)))
        .filter(_periodo_vigente_expr(campo_inicio, campo_fim))
    )
    excluidos = ids_alto_comando_excluidos_de_agregado_disposicao()
    if excluidos:
        query = query.filter(model.militar_id.notin_(excluidos))
    return set(mid for (mid,) in query.all())


def ids_militares_a_disposicao_vigente():
    """Union de "só à disposição" e "agregado e à disposição ao mesmo
    tempo" — a tabela À Disposição é alimentada pela Modalidade, não pela
    Situação, então já cobre os dois casos."""
    return _ids_militares_com_registro_vigente(
        MilitaresADisposicao,
        MilitaresADisposicao.inicio_periodo,
        MilitaresADisposicao.fim_periodo_disposicao,
    )


def ids_militares_agregados_vigente():
    return _ids_militares_com_registro_vigente(
        MilitaresAgregados,
        MilitaresAgregados.inicio_periodo,
        MilitaresAgregados.fim_periodo_agregacao,
    )


def listar_militares_agregados(militar_id=None):
    """Sem `militar_id`, lista só o registro MAIS RECENTE de cada militar
    (tela /militares-agregados) — sem isso, um militar com histórico de
    mais de uma agregação aparecia repetido na lista, inclusive com um
    registro já vencido que a ficha dele nem mostra mais (ela só olha o
    atual), o que confundia o operador. Com `militar_id`, filtra pra um
    único militar e devolve TODO o histórico dele (módulo de Histórico)."""
    query = MilitaresAgregados.query.options(
        *[joinedload(getattr(MilitaresAgregados, rel)) for rel in _RELACIONAMENTOS_COMUNS]
    )
    if militar_id is not None:
        query = query.filter(MilitaresAgregados.militar_id == militar_id)
    else:
        query = (
            query
            .join(Militar, Militar.id == MilitaresAgregados.militar_id)
            .filter(Militar.inativo.is_(False))
            .filter(MilitaresAgregados.id.in_(_ids_mais_recentes_por_militar(MilitaresAgregados)))
        )
        excluidos = ids_alto_comando_excluidos_de_agregado_disposicao()
        if excluidos:
            query = query.filter(MilitaresAgregados.militar_id.notin_(excluidos))
    return query.order_by(MilitaresAgregados.fim_periodo_agregacao.desc().nullslast()).all()


def listar_militares_a_disposicao(militar_id=None):
    """Sem `militar_id`, lista só o registro MAIS RECENTE de cada militar
    (tela /militares-a-disposicao) — mesmo motivo de
    listar_militares_agregados. Com `militar_id`, filtra pra um único
    militar e devolve TODO o histórico dele (módulo de Histórico)."""
    query = MilitaresADisposicao.query.options(
        *[joinedload(getattr(MilitaresADisposicao, rel)) for rel in _RELACIONAMENTOS_COMUNS]
    )
    if militar_id is not None:
        query = query.filter(MilitaresADisposicao.militar_id == militar_id)
    else:
        query = (
            query
            .join(Militar, Militar.id == MilitaresADisposicao.militar_id)
            .filter(Militar.inativo.is_(False))
            .filter(MilitaresADisposicao.id.in_(_ids_mais_recentes_por_militar(MilitaresADisposicao)))
        )
        excluidos = ids_alto_comando_excluidos_de_agregado_disposicao()
        if excluidos:
            query = query.filter(MilitaresADisposicao.militar_id.notin_(excluidos))
    return query.order_by(MilitaresADisposicao.fim_periodo_disposicao.desc().nullslast()).all()


def montar_resumo_dashboard(registros, campo_fim: str, status_vencido: str = "Venceu") -> dict:
    """Cards de resumo + ranking de destinos pras telas de listagem (à
    disposição / agregados). Computado em cima da mesma lista já
    deduplicada (um registro por militar) que vai pra tabela — sem
    consulta extra ao banco.

    `campo_fim` é o nome do atributo de data de término em cada registro
    ("fim_periodo_disposicao" ou "fim_periodo_agregacao"), já que os dois
    modelos usam nomes diferentes pra essa coluna. `status_vencido` é o
    texto usado pelo status "já venceu" — MilitaresADisposicao usa "Venceu",
    mas MilitaresAgregados usa "Término de Agregação" (ver atualizar_status
    de cada model em src/models.py)."""
    hoje = date.today()
    total = len(registros)

    vigentes = a_iniciar = vencidos = vencendo_em_breve = sem_dados = 0
    contagem_destino = Counter()

    for r in registros:
        if r.status == "Vigente":
            vigentes += 1
            fim = getattr(r, campo_fim)
            if fim and 0 <= (fim - hoje).days <= DIAS_ALERTA_VENCIMENTO:
                vencendo_em_breve += 1
        elif r.status == "A iniciar":
            a_iniciar += 1
        elif r.status == status_vencido:
            vencidos += 1
        else:
            # "Inativo" (sem data de início preenchida) ou qualquer outro
            # status fora dos três normais — não pode ficar de fora da
            # soma, senão os cards não batem com o total de registros.
            sem_dados += 1

        contagem_destino[r.destino.local if r.destino else "Sem destino informado"] += 1

    top_destinos = contagem_destino.most_common(QTD_DESTINOS_NO_RANKING)
    outros = total - sum(qtd for _, qtd in top_destinos)
    if outros > 0:
        top_destinos.append(("Outros", outros))

    maior_qtd = max((qtd for _, qtd in top_destinos), default=0)
    destinos = [
        {
            "nome": nome,
            "qtd": qtd,
            "pct": round(qtd / total * 100) if total else 0,
            "largura_pct": round(qtd / maior_qtd * 100) if maior_qtd else 0,
        }
        for nome, qtd in top_destinos
    ]

    return {
        "hoje": hoje,
        "total": total,
        "vigentes": vigentes,
        "a_iniciar": a_iniciar,
        "vencidos": vencidos,
        "vencendo_em_breve": vencendo_em_breve,
        "sem_dados": sem_dados,
        "status_vencido": status_vencido,
        "destinos": destinos,
    }


def _dias_texto(status, inicio, fim, hoje, status_vencido) -> str:
    """Mesmo texto do badge "Dias" da tela (macro dias_badge em
    _situacoes_militares_macros.html), só que em texto puro pra planilha."""
    if status == "Vigente" and fim:
        dias = (fim - hoje).days
        return f"Faltam {dias} dia{'s' if dias != 1 else ''}"
    if status == status_vencido and fim:
        dias = (hoje - fim).days
        return f"Vencido há {dias} dia{'s' if dias != 1 else ''}"
    if status == "A iniciar" and inicio:
        dias = (inicio - hoje).days
        return f"Inicia em {dias} dia{'s' if dias != 1 else ''}"
    return "—"


COLUNAS_EXPORTACAO_SITUACAO = [
    "Posto/Graduação", "Matrícula", "Nome Completo", "Quadro", "Destino",
    "Situação atual do militar", "A contar de", "Término", "Dias", "Status",
    "Documento Autorizador",
]


def gerar_planilha_situacao(titulo: str, registros, campo_fim: str, status_vencido: str) -> BytesIO:
    """Gera o .xlsx de uma tela de listagem (à disposição / agregados) a
    partir da mesma lista (já deduplicada, um registro por militar) usada
    na tabela — mesmas colunas, incluindo os "Dias" calculados."""
    hoje = date.today()

    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31]  # limite de 31 caracteres do Excel pro nome da aba

    ws.append(COLUNAS_EXPORTACAO_SITUACAO)
    for col_num in range(1, len(COLUNAS_EXPORTACAO_SITUACAO) + 1):
        ws.cell(row=1, column=col_num).font = Font(bold=True)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS_EXPORTACAO_SITUACAO))}1"

    def fmt(dt):
        return dt.strftime("%d/%m/%Y") if dt else ""

    for r in registros:
        fim = getattr(r, campo_fim)
        ws.append([
            r.posto_grad.sigla if r.posto_grad else "",
            r.militar.matricula if r.militar else "",
            r.militar.nome_completo if r.militar else "",
            r.quadro.quadro if r.quadro else "",
            r.destino.local if r.destino else "",
            r.militar.situacao if r.militar and r.militar.situacao else "",
            fmt(r.inicio_periodo),
            fmt(fim),
            _dias_texto(r.status, r.inicio_periodo, fim, hoje, status_vencido),
            r.status or "",
            r.publicacao_bg.boletim_geral if r.publicacao_bg else "",
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def listar_licencas_especiais(militar_id=None):
    """Sem `militar_id`, lista todas (tela /licenca-especial). Com
    `militar_id`, filtra pra um único militar (módulo de Histórico)."""
    query = LicencaEspecial.query.options(
        *[joinedload(getattr(LicencaEspecial, rel)) for rel in _RELACIONAMENTOS_COMUNS]
    )
    if militar_id is not None:
        query = query.filter(LicencaEspecial.militar_id == militar_id)
    return query.order_by(LicencaEspecial.fim_periodo_le.desc().nullslast()).all()
