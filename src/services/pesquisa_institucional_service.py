"""Serviço da Pesquisa Institucional — Levantamento de Necessidades de
Treinamento e Desenvolvimento (LNTD / ESASP) para o CBMAM.

Cada militar avalia de 1 a 5 (inteiro) a relevância de cada curso das 11
trilhas educacionais da ESASP (a..k) e pode indicar cursos não listados.
O Super User e os militares da BM-3 visualizam o ranking consolidado
(ordenado de forma decrescente pelo somatório de notas de cada curso) e as
avaliações individuais de cada militar.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import case, func

from src import database
from src.models import (
    Militar,
    MilitarObmFuncao,
    Obm,
    PesquisaInstitucionalAvaliacao,
    PesquisaInstitucionalCurso,
    PesquisaInstitucionalResposta,
    PostoGrad,
    User,
    now_manaus_naive,
)

MANAUS_TZ = ZoneInfo("America/Manaus")

# Escala inteira 1 a 5 exigida no formulário e nos relatórios
ESCALA_NOTAS: dict[int, str] = {
    1: "Irrelevante",
    2: "Pouco relevante",
    3: "Moderadamente relevante",
    4: "Relevante",
    5: "Muito relevante",
}

ESCALA_CORES: dict[int, str] = {
    1: "#ef4444",  # vermelho
    2: "#f97316",  # laranja
    3: "#eab308",  # amarelo
    4: "#3b82f6",  # azul
    5: "#10b981",  # verde
}

# Metadados visuais por seção (ícones Bootstrap Icons e subtítulo)
SECOES_META: dict[str, dict[str, str]] = {
    "a": {
        "icone": "bi-people-fill",
        "cor": "#2563eb",
        "descricao": "Desenvolvimento de lideranças, gestão de equipes e competências humanas.",
    },
    "b": {
        "icone": "bi-box-seam-fill",
        "cor": "#0891b2",
        "descricao": "Patrimônio, almoxarifado, suprimentos, contratações e materiais.",
    },
    "c": {
        "icone": "bi-diagram-3-fill",
        "cor": "#7c3aed",
        "descricao": "Planejamento estratégico, gestão de projetos, processos e contratos.",
    },
    "d": {
        "icone": "bi-tree-fill",
        "cor": "#059669",
        "descricao": "Sustentabilidade pública, A3P, PLS, eficiência energética e ESG.",
    },
    "e": {
        "icone": "bi-shield-check",
        "cor": "#b91c1c",
        "descricao": "Governança, integridade, compliance, riscos, auditoria e licitações.",
    },
    "f": {
        "icone": "bi-bank2",
        "cor": "#9333ea",
        "descricao": "Direito administrativo, regime jurídico, LGPD, LAI e legislação aplicada.",
    },
    "g": {
        "icone": "bi-cash-coin",
        "cor": "#0d9488",
        "descricao": "Orçamento público, execução financeira, contabilidade e responsabilidade fiscal.",
    },
    "h": {
        "icone": "bi-translate",
        "cor": "#d97706",
        "descricao": "Língua Brasileira de Sinais (Libras) para comunicação e atendimento ao público.",
    },
    "i": {
        "icone": "bi-cpu-fill",
        "cor": "#1d4ed8",
        "descricao": "Transformação digital, segurança da informação, Power BI, Excel e IA aplicada.",
    },
    "j": {
        "icone": "bi-megaphone-fill",
        "cor": "#e11d48",
        "descricao": "Redação oficial, comunicação institucional, oratória, cerimonial e atendimento.",
    },
    "k": {
        "icone": "bi-heart-pulse-fill",
        "cor": "#16a34a",
        "descricao": "Saúde ocupacional, saúde mental, prevenção de acidentes, ergonomia, ISO e CIPA.",
    },
}

# Catálogo oficial extraído das páginas 1 a 3 do documento LNTD / ESASP
TRILHAS_ESASP_DEFAULT: list[tuple[str, str, list[str]]] = [
    (
        "a",
        "Gestão Pública, Liderança e Recursos Humanos",
        [
            "Liderança e Gestão de Equipes",
            "Gestão de Pessoas",
            "Desenvolvimento Gerencial",
            "Trabalho em Equipe",
            "Inteligência Emocional",
            "Comunicação Interpessoal",
            "Gestão de Conflitos",
            "Gestão Por Competências",
            "Desenvolvimento Organizacional",
        ],
    ),
    (
        "b",
        "Cadeia Logística",
        [
            "Gestão Patrimonial",
            "Almoxarifado",
            "Estoque",
            "Logística Governamental",
            "Cadeia de Suprimentos",
            "Planejamento das Contratações",
            "Gestão de Materiais",
            "Diárias e Passagens",
        ],
    ),
    (
        "c",
        "Projetos e Processos",
        [
            "Gestão de Projetos",
            "Gestão de Processos",
            "Planejamento Estratégico",
            "Indicadores de Desempenho Institucional",
            "Gestão Documental",
            "Transformação Organizacional",
            "Melhoria Contínua dos Fluxos Administrativos",
            "Sistema de gestão de contratos – SGC",
        ],
    ),
    (
        "d",
        "Meio Ambiente e Sustentabilidade",
        [
            "Sustentabilidade na Administração Pública",
            "Agenda Ambiental na Administração Pública (A3P)",
            "Plano de Logística Sustentável (PLS)",
            "Compras Sustentáveis",
            "Gestão de Resíduos",
            "Eficiência Energética",
            "Responsabilidade Socioambiental",
            "Governança e Sustentabilidade",
            "Normalização Ambiental (ISO 14001 e ESG)",
        ],
    ),
    (
        "e",
        "Controle Interno e Gestão Administrativa",
        [
            "Sistema de Controle Interno",
            "Governança Pública",
            "Integridade",
            "Compliance",
            "Gestão de Riscos",
            "Auditoria Governamental",
            "Transparência Pública",
            "Gestão de Ouvidoria Pública",
            "Transferências voluntárias e tomadas de contas especiais",
            "Respostas a órgão de controle",
            "Auditoria na Prestação de Contas",
            "Ferramentas de Controle Interno e Monitoramento",
            "Elaboração de Relatórios",
            "Licitação e Contratos",
        ],
    ),
    (
        "f",
        "Conhecimento Jurídico",
        [
            "Direito Aplicado à Administração Pública",
            "Regime Jurídico dos Servidores",
            "Processos Administrativos",
            "Legislação Administrativa",
            "Direitos Humanos, Legislação e Exercício da Cidadania",
            "Lei Geral de Proteção de Dados (LGPD)",
            "Lei de Acesso a Informação (LAI)",
            "Transparência Pública",
            "Redação jurídica",
            "Lei das estatais lei nº 13.303/2016 - processo de compra e contratação de empresas públicas, sociedades de economia mista subsidiárias",
            "Atualização do marco regulatório do 3º setor – lei 13.019/2014",
        ],
    ),
    (
        "g",
        "Orçamento e Finanças",
        [
            "Planejamento Governamental",
            "Orçamento Público",
            "Educação financeira pessoal",
            "Execução Financeira e Orçamentária",
            "Contabilidade Pública",
            "Responsabilidade Fiscal",
            "Prestação de Contas",
            "Gestão de Recursos Públicos",
        ],
    ),
    (
        "h",
        "Idiomas",
        [
            "Língua brasileira de sinais – Libras básico",
            "Língua brasileira de sinais – Libras intermediário",
            "Língua brasileira de sinais – Libras Avançada",
            "Libras Para Atendimento ao Público",
        ],
    ),
    (
        "i",
        "Tecnologia da Informação",
        [
            "Letramento Digital",
            "Ferramentas Corporativas Digitais",
            "Sistemas Governamentais",
            "Transformação Digital",
            "Segurança da Informação",
            "Análise de Dados no Power BI",
            "Business Intelligence",
            "Excel (básico, intermediário e avançado)",
            "Inteligência Artificial Aplicada ao Serviço Público",
            "Fundamentos de TI: hardware e software",
            "Fundamentos do design gráfico",
        ],
    ),
    (
        "j",
        "Comunicação Organizacional",
        [
            "Redação Oficial",
            "Linguagem Simples",
            "Comunicação Institucional",
            "Comunicação Digital",
            "Comunicação e Oratória",
            "Atendimento ao Cidadão",
            "Redes Sociais Governamentais",
            "Cerimonial e Protocolo",
            "Relacionamento Institucional",
        ],
    ),
    (
        "k",
        "Bem-estar e Segurança no Ambiente de Trabalho",
        [
            "Saúde Ocupacional",
            "Qualidade de Vida",
            "Saúde Mental",
            "Prevenção de Acidentes",
            "Ergonomia do Trabalho",
            "Acessibilidade",
            "Inclusão e Segurança no Ambiente Laboral",
            "Leitura e Interpretação das Normas de ISO 9001: 2015 – Auditoria de Qualidade",
            "Mentalidade de Riscos",
            "Leitura e Interpretação das Normas da NR1",
            "Subsídios para Formação da Comissão Interna de Acidentes e de Assédio – CIPA",
        ],
    ),
]

_catalogo_inicializado = False


def ano_pesquisa_vigente() -> int:
    return datetime.now(MANAUS_TZ).year


def garantir_tabelas_e_catalogo_pesquisa() -> None:
    """Cria as tabelas da Pesquisa Institucional caso ainda não existam e
    popula o catálogo padrão das 11 trilhas da ESASP na primeira execução."""
    global _catalogo_inicializado
    if _catalogo_inicializado:
        return

    engine = database.engine
    PesquisaInstitucionalCurso.__table__.create(bind=engine, checkfirst=True)
    PesquisaInstitucionalResposta.__table__.create(bind=engine, checkfirst=True)
    PesquisaInstitucionalAvaliacao.__table__.create(bind=engine, checkfirst=True)

    qtd = database.session.query(func.count(PesquisaInstitucionalCurso.id)).scalar() or 0
    if qtd == 0:
        for idx_secao, (codigo, titulo, cursos) in enumerate(TRILHAS_ESASP_DEFAULT, start=1):
            for idx_curso, nome_curso in enumerate(cursos, start=1):
                database.session.add(
                    PesquisaInstitucionalCurso(
                        secao_codigo=codigo,
                        secao_titulo=titulo,
                        ordem_secao=idx_secao,
                        nome=nome_curso,
                        ordem_curso=idx_curso,
                        ativo=True,
                    )
                )
        database.session.commit()

    _catalogo_inicializado = True


def listar_cursos_ativos() -> list[PesquisaInstitucionalCurso]:
    garantir_tabelas_e_catalogo_pesquisa()
    return (
        PesquisaInstitucionalCurso.query.filter_by(ativo=True)
        .order_by(
            PesquisaInstitucionalCurso.ordem_secao.asc(),
            PesquisaInstitucionalCurso.ordem_curso.asc(),
            PesquisaInstitucionalCurso.id.asc(),
        )
        .all()
    )


def listar_trilhas_e_cursos() -> list[dict]:
    """Retorna as 11 trilhas (a..k) estruturadas com seus cursos e metadados."""
    cursos = listar_cursos_ativos()
    secoes_map: dict[str, dict] = {}
    secoes_lista: list[dict] = []

    for c in cursos:
        cod = c.secao_codigo
        if cod not in secoes_map:
            meta = SECOES_META.get(cod, {})
            sec = {
                "codigo": cod,
                "titulo": c.secao_titulo,
                "ordem": c.ordem_secao,
                "icone": meta.get("icone", "bi-journal-bookmark-fill"),
                "cor": meta.get("cor", "#2563eb"),
                "descricao": meta.get("descricao", ""),
                "cursos": [],
            }
            secoes_map[cod] = sec
            secoes_lista.append(sec)
        secoes_map[cod]["cursos"].append(c)

    return secoes_lista


def obter_resposta_militar(
    militar_id: int | None,
    user_id: int | None,
    ano: int | None = None,
) -> tuple[PesquisaInstitucionalResposta | None, dict[int, int]]:
    """Busca a resposta já enviada pelo militar (ou usuário) no ano vigente e
    devolve (resposta, {curso_id: nota})."""
    garantir_tabelas_e_catalogo_pesquisa()
    ano = ano or ano_pesquisa_vigente()

    query = PesquisaInstitucionalResposta.query.filter_by(ano_referencia=ano)
    resposta = None
    if militar_id:
        resposta = (
            query.filter_by(militar_id=militar_id)
            .order_by(PesquisaInstitucionalResposta.id.desc())
            .first()
        )
    if not resposta and user_id:
        resposta = (
            query.filter_by(user_id=user_id)
            .order_by(PesquisaInstitucionalResposta.id.desc())
            .first()
        )

    if not resposta:
        return None, {}

    notas_map = {int(av.curso_id): int(av.nota) for av in resposta.avaliacoes}
    return resposta, notas_map


def salvar_resposta_pesquisa(
    militar: Militar | None,
    user: User,
    notas_por_curso: dict[int, int],
    sugestao_texto: str | None,
    ip_address: str | None = None,
    ano: int | None = None,
) -> PesquisaInstitucionalResposta:
    """Valida e grava (ou atualiza) as notas de 1 a 5 dadas pelo militar."""
    garantir_tabelas_e_catalogo_pesquisa()
    ano = ano or ano_pesquisa_vigente()
    cursos = listar_cursos_ativos()

    faltantes = []
    notas_validadas: dict[int, int] = {}
    for c in cursos:
        valor = notas_por_curso.get(c.id)
        if valor is None:
            faltantes.append(f"{c.secao_codigo}) {c.nome}")
            continue
        try:
            nota_int = int(valor)
        except (ValueError, TypeError):
            raise ValueError(f"Nota inválida para o curso '{c.nome}'. Selecione um valor de 1 a 5.")
        if nota_int not in ESCALA_NOTAS:
            raise ValueError(f"A nota do curso '{c.nome}' deve ser um número inteiro entre 1 e 5.")
        notas_validadas[c.id] = nota_int

    if faltantes:
        exemplo = ", ".join(faltantes[:3])
        resto = f" (e mais {len(faltantes) - 3})" if len(faltantes) > 3 else ""
        raise ValueError(
            f"Por favor, selecione uma nota de 1 a 5 para todos os cursos listados. "
            f"Pendentes: {exemplo}{resto}."
        )

    militar_id = militar.id if militar else getattr(user, "militar_id", None)
    user_id = getattr(user, "id", None)
    resposta, _ = obter_resposta_militar(militar_id, user_id, ano=ano)

    sugestao_limpa = (sugestao_texto or "").strip() or None
    agora = now_manaus_naive()

    if not resposta:
        resposta = PesquisaInstitucionalResposta(
            ano_referencia=ano,
            militar_id=militar_id,
            user_id=user_id,
            sugestao_cursos_nao_listados=sugestao_limpa,
            ip_address=ip_address,
            criado_em=agora,
            atualizado_em=agora,
        )
        database.session.add(resposta)
        database.session.flush()
    else:
        resposta.militar_id = militar_id or resposta.militar_id
        resposta.user_id = user_id or resposta.user_id
        resposta.sugestao_cursos_nao_listados = sugestao_limpa
        resposta.ip_address = ip_address
        resposta.atualizado_em = agora

    existentes_por_curso = {av.curso_id: av for av in resposta.avaliacoes}
    for curso_id, nota_int in notas_validadas.items():
        if curso_id in existentes_por_curso:
            existentes_por_curso[curso_id].nota = nota_int
        else:
            database.session.add(
                PesquisaInstitucionalAvaliacao(
                    resposta_id=resposta.id,
                    curso_id=curso_id,
                    nota=nota_int,
                )
            )

    database.session.commit()
    return resposta


def obter_consolidado_pesquisa(
    ano: int | None = None,
    secao_filtro: str | None = None,
    busca: str | None = None,
) -> dict:
    """Consolida todas as notas dadas pelos militares e ordena os cursos de
    forma DECRESCENTE pelo somatório de notas (SUM(nota) DESC)."""
    garantir_tabelas_e_catalogo_pesquisa()
    ano = ano or ano_pesquisa_vigente()

    C = PesquisaInstitucionalCurso
    A = PesquisaInstitucionalAvaliacao
    R = PesquisaInstitucionalResposta

    # Subconsulta filtrando respostas do ano de referência
    respostas_ano_sq = (
        database.session.query(R.id)
        .filter(R.ano_referencia == ano)
        .subquery()
    )

    soma_expr = func.coalesce(
        func.sum(
            case((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id)), A.nota), else_=0)
        ),
        0,
    )
    qtd_expr = func.coalesce(
        func.sum(
            case((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id)), 1), else_=0)
        ),
        0,
    )
    media_expr = func.coalesce(
        func.avg(
            case((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id)), A.nota), else_=None)
        ),
        0,
    )

    nota_1_expr = func.coalesce(
        func.sum(
            case(
                ((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id))) & (A.nota == 1), 1),
                else_=0,
            )
        ),
        0,
    )
    nota_2_expr = func.coalesce(
        func.sum(
            case(
                ((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id))) & (A.nota == 2), 1),
                else_=0,
            )
        ),
        0,
    )
    nota_3_expr = func.coalesce(
        func.sum(
            case(
                ((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id))) & (A.nota == 3), 1),
                else_=0,
            )
        ),
        0,
    )
    nota_4_expr = func.coalesce(
        func.sum(
            case(
                ((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id))) & (A.nota == 4), 1),
                else_=0,
            )
        ),
        0,
    )
    nota_5_expr = func.coalesce(
        func.sum(
            case(
                ((A.resposta_id.in_(database.session.query(respostas_ano_sq.c.id))) & (A.nota == 5), 1),
                else_=0,
            )
        ),
        0,
    )

    q = (
        database.session.query(
            C,
            soma_expr.label("somatorio_notas"),
            media_expr.label("media_notas"),
            qtd_expr.label("total_votos"),
            nota_1_expr.label("qtd_1"),
            nota_2_expr.label("qtd_2"),
            nota_3_expr.label("qtd_3"),
            nota_4_expr.label("qtd_4"),
            nota_5_expr.label("qtd_5"),
        )
        .outerjoin(A, A.curso_id == C.id)
        .filter(C.ativo.is_(True))
    )

    if secao_filtro:
        q = q.filter(C.secao_codigo == secao_filtro.strip().lower())

    if busca:
        termo = f"%{busca.strip()}%"
        q = q.filter((C.nome.ilike(termo)) | (C.secao_titulo.ilike(termo)))

    # Ordenação principal exigida: DECRESCENTE pelo somatório de notas
    rows = (
        q.group_by(C.id)
        .order_by(
            soma_expr.desc(),
            media_expr.desc(),
            C.ordem_secao.asc(),
            C.ordem_curso.asc(),
        )
        .all()
    )

    ranking_cursos = []
    por_secao: dict[str, dict] = {}

    for pos, row in enumerate(rows, start=1):
        curso_obj = row[0]
        somatorio = int(row.somatorio_notas or 0)
        media = float(row.media_notas or 0.0)
        votos = int(row.total_votos or 0)
        q1 = int(row.qtd_1 or 0)
        q2 = int(row.qtd_2 or 0)
        q3 = int(row.qtd_3 or 0)
        q4 = int(row.qtd_4 or 0)
        q5 = int(row.qtd_5 or 0)

        meta = SECOES_META.get(curso_obj.secao_codigo, {})
        item = {
            "posicao": pos,
            "curso_id": curso_obj.id,
            "nome": curso_obj.nome,
            "secao_codigo": curso_obj.secao_codigo,
            "secao_titulo": curso_obj.secao_titulo,
            "ordem_secao": curso_obj.ordem_secao,
            "cor_secao": meta.get("cor", "#2563eb"),
            "icone_secao": meta.get("icone", "bi-journal-bookmark-fill"),
            "somatorio_notas": somatorio,
            "media_notas": round(media, 2),
            "total_votos": votos,
            "qtd_1": q1,
            "qtd_2": q2,
            "qtd_3": q3,
            "qtd_4": q4,
            "qtd_5": q5,
            "pct_relevante": round(((q4 + q5) / votos) * 100, 1) if votos > 0 else 0.0,
        }
        ranking_cursos.append(item)

        cod = curso_obj.secao_codigo
        if cod not in por_secao:
            por_secao[cod] = {
                "codigo": cod,
                "titulo": curso_obj.secao_titulo,
                "ordem": curso_obj.ordem_secao,
                "cor": meta.get("cor", "#2563eb"),
                "icone": meta.get("icone", "bi-journal-bookmark-fill"),
                "somatorio_secao": 0,
                "cursos": [],
            }
        por_secao[cod]["somatorio_secao"] += somatorio
        por_secao[cod]["cursos"].append(item)

    secoes_ordenadas = sorted(por_secao.values(), key=lambda s: s["ordem"])
    for sec in secoes_ordenadas:
        sec["cursos"].sort(
            key=lambda x: (-x["somatorio_notas"], -x["media_notas"], x["curso_id"])
        )

    total_respondentes = (
        database.session.query(func.count(R.id))
        .filter(R.ano_referencia == ano)
        .scalar()
        or 0
    )
    total_sugestoes = (
        database.session.query(func.count(R.id))
        .filter(
            R.ano_referencia == ano,
            R.sugestao_cursos_nao_listados.isnot(None),
            func.trim(R.sugestao_cursos_nao_listados) != "",
        )
        .scalar()
        or 0
    )
    soma_global = sum(item["somatorio_notas"] for item in ranking_cursos)
    votos_global = sum(item["total_votos"] for item in ranking_cursos)
    media_global = round(soma_global / votos_global, 2) if votos_global > 0 else 0.0

    return {
        "ano": ano,
        "ranking_cursos": ranking_cursos,
        "secoes_consolidado": secoes_ordenadas,
        "total_respondentes": int(total_respondentes),
        "total_sugestoes": int(total_sugestoes),
        "soma_global": int(soma_global),
        "votos_global": int(votos_global),
        "media_global": media_global,
    }


def _obm_sigla_do_militar(militar_id: int | None, user: User | None) -> str:
    if militar_id:
        vinc = (
            database.session.query(Obm.sigla)
            .join(MilitarObmFuncao, MilitarObmFuncao.obm_id == Obm.id)
            .filter(
                MilitarObmFuncao.militar_id == militar_id,
                MilitarObmFuncao.data_fim.is_(None),
            )
            .order_by(MilitarObmFuncao.tipo.asc(), MilitarObmFuncao.id.desc())
            .first()
        )
        if vinc and vinc[0]:
            return vinc[0]
    if user and getattr(user, "obm_id_1", None):
        obm = database.session.get(Obm, user.obm_id_1)
        if obm and obm.sigla:
            return obm.sigla
    return "—"


def listar_respostas_individuais(
    ano: int | None = None,
    busca: str | None = None,
) -> list[dict]:
    """Lista todos os militares que responderam à Pesquisa Institucional,
    com resumo das notas atribuídas e eventual sugestão de curso não listado."""
    garantir_tabelas_e_catalogo_pesquisa()
    ano = ano or ano_pesquisa_vigente()

    R = PesquisaInstitucionalResposta
    A = PesquisaInstitucionalAvaliacao

    q = (
        database.session.query(
            R,
            func.coalesce(func.sum(A.nota), 0).label("soma_notas"),
            func.coalesce(func.avg(A.nota), 0).label("media_notas"),
            func.count(A.id).label("qtd_cursos"),
        )
        .outerjoin(A, A.resposta_id == R.id)
        .outerjoin(Militar, Militar.id == R.militar_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(User, User.id == R.user_id)
        .filter(R.ano_referencia == ano)
    )

    if busca:
        termo = f"%{busca.strip()}%"
        q = q.filter(
            (Militar.nome_completo.ilike(termo))
            | (Militar.nome_guerra.ilike(termo))
            | (Militar.matricula.ilike(termo))
            | (User.nome.ilike(termo))
            | (R.sugestao_cursos_nao_listados.ilike(termo))
        )

    rows = (
        q.group_by(R.id)
        .order_by(R.atualizado_em.desc(), R.id.desc())
        .all()
    )

    resultados = []
    for r, soma, media, qtd in rows:
        militar = r.militar
        user = r.user
        posto_sigla = (
            militar.posto_grad.sigla
            if militar and getattr(militar, "posto_grad", None)
            else "—"
        )
        nome_exibicao = (
            militar.nome_completo
            if militar and militar.nome_completo
            else (user.nome if user and user.nome else "Militar")
        )
        nome_guerra = militar.nome_guerra if militar and militar.nome_guerra else "—"
        matricula = militar.matricula if militar and militar.matricula else "—"
        obm_sigla = _obm_sigla_do_militar(r.militar_id, user)

        resultados.append(
            {
                "id": r.id,
                "militar_id": r.militar_id,
                "posto_grad": posto_sigla,
                "nome_completo": nome_exibicao,
                "nome_guerra": nome_guerra,
                "matricula": matricula,
                "obm_sigla": obm_sigla,
                "criado_em": r.criado_em,
                "atualizado_em": r.atualizado_em,
                "sugestao_cursos_nao_listados": r.sugestao_cursos_nao_listados,
                "soma_notas": int(soma or 0),
                "media_notas": round(float(media or 0.0), 2),
                "qtd_cursos": int(qtd or 0),
            }
        )

    return resultados


def obter_detalhe_resposta_individual(resposta_id: int) -> dict | None:
    """Retorna os dados completos de um militar e todas as notas (1 a 5) que
    ele atribuiu a cada curso, organizadas por seção (a..k)."""
    garantir_tabelas_e_catalogo_pesquisa()
    r = database.session.get(PesquisaInstitucionalResposta, resposta_id)
    if not r:
        return None

    militar = r.militar
    user = r.user
    posto_sigla = (
        militar.posto_grad.sigla
        if militar and getattr(militar, "posto_grad", None)
        else "—"
    )
    nome_exibicao = (
        militar.nome_completo
        if militar and militar.nome_completo
        else (user.nome if user and user.nome else "Militar")
    )
    matricula = militar.matricula if militar and militar.matricula else "—"
    obm_sigla = _obm_sigla_do_militar(r.militar_id, user)

    notas_map = {int(av.curso_id): int(av.nota) for av in r.avaliacoes}
    trilhas = listar_trilhas_e_cursos()

    contagem_por_nota = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    soma_total = 0
    qtd_total = 0

    secoes_detalhe = []
    for sec in trilhas:
        cursos_sec = []
        soma_sec = 0
        for c in sec["cursos"]:
            nota = notas_map.get(c.id)
            if nota in contagem_por_nota:
                contagem_por_nota[nota] += 1
                soma_total += nota
                soma_sec += nota
                qtd_total += 1
            cursos_sec.append(
                {
                    "curso_id": c.id,
                    "nome": c.nome,
                    "nota": nota,
                    "nota_label": ESCALA_NOTAS.get(nota, "Não avaliado"),
                    "nota_cor": ESCALA_CORES.get(nota, "#64748b"),
                }
            )
        media_sec = round(soma_sec / len(cursos_sec), 2) if cursos_sec else 0.0
        secoes_detalhe.append(
            {
                **sec,
                "cursos_avaliados": cursos_sec,
                "soma_secao": soma_sec,
                "media_secao": media_sec,
            }
        )

    media_total = round(soma_total / qtd_total, 2) if qtd_total > 0 else 0.0

    return {
        "resposta": r,
        "posto_grad": posto_sigla,
        "nome_completo": nome_exibicao,
        "nome_guerra": militar.nome_guerra if militar and militar.nome_guerra else "—",
        "matricula": matricula,
        "cpf": (militar.cpf if militar and militar.cpf else (user.cpf if user else "—")),
        "obm_sigla": obm_sigla,
        "criado_em": r.criado_em,
        "atualizado_em": r.atualizado_em,
        "sugestao_cursos_nao_listados": r.sugestao_cursos_nao_listados,
        "soma_total": soma_total,
        "media_total": media_total,
        "qtd_total": qtd_total,
        "contagem_por_nota": contagem_por_nota,
        "secoes": secoes_detalhe,
    }
