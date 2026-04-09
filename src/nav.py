# src/nav.py
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from flask import session, url_for
from flask_login import current_user
from src.decorators.control import has_perm, _get_pg_id_user
from src.authz import can_see_taf_panel, is_super, is_super_or_perm


def _safe_url(endpoint: str, **values) -> str:
    """
    Gera url_for sem quebrar.
    Se endpoint exigir parâmetro e ele não vier, devolve '#'.
    """
    try:
        return url_for(endpoint, **values)
    except Exception:
        return "#"


def _is_super() -> bool:
    return is_super()


def _rule_true() -> bool:
    return True


def _rule_funcao_in(ids: List[int]) -> bool:
    return int(getattr(current_user, "funcao_user_id", 0) or 0) in set(ids)


def _rule_user_id_is(uid: int) -> bool:
    return int(getattr(current_user, "id", 0) or 0) == int(uid)


def _rule_paf_solicitante() -> bool:
    if not getattr(current_user, "is_authenticated", False):
        return False

    funcao_id = int(getattr(current_user, "funcao_user_id", 0) or 0)
    if funcao_id != 12:
        return False

    PG_SUP = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}
    pg_id = _get_pg_id_user()
    return (pg_id in PG_SUP) if pg_id is not None else False


def _rule_alunos_total() -> bool:
    """
    Regra original:
      - (funcao == 2 e obm_id_1 == 26) OU funcao in {5,6}
    """
    funcao = int(getattr(current_user, "funcao_user_id", 0) or 0)
    obm = int(getattr(current_user, "obm_id_1", 0) or 0)
    return (funcao == 2 and obm == 26) or (funcao in {5, 6})


def _mk_item(
    label: str,
    endpoint: str,
    icon: str = "",
    perm: Optional[str] = None,
    rule: Callable[[], bool] = _rule_true,
    endpoint_kwargs: Optional[dict] = None,
) -> Dict[str, Any]:
    endpoint_kwargs = endpoint_kwargs or {}

    return {
        "type": "item",
        "label": label,
        "icon": icon,
        "href": _safe_url(endpoint, **endpoint_kwargs),
        "endpoint": endpoint,
        "kwargs": endpoint_kwargs,
        "disabled": False,
        "perm": perm,
        "rule": rule,
    }


def _mk_group(label: str, icon: str, children: List[Dict[str, Any]], perm=None, rule=_rule_true):
    return {
        "type": "group",
        "label": label,
        "icon": icon,
        "children": children,
        "perm": perm,
        "rule": rule,
    }


def _is_visible(node: Dict[str, Any]) -> bool:
    # regra (condição)
    if not node.get("rule", _rule_true)():
        return False

    # permissão (se houver)
    perm = node.get("perm")
    if perm and not has_perm(perm):
        return False

    # grupo: precisa ter pelo menos 1 filho visível
    if node.get("type") == "group":
        visible_children = [c for c in node.get(
            "children", []) if _is_visible(c)]
        node["children"] = visible_children
        return len(visible_children) > 0

    return True


def pode_ver_ferias_super() -> bool:
    return is_super_or_perm("NAV_FERIAS_SUPER")


def build_nav(militar_id_atual: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retorna a árvore de menus (itens e grupos).
    - SUPER USER vê tudo.
    - Para o resto, o controle principal vira PERMISSÃO (UserPermissao),
      mas mantendo algumas regras antigas onde faz sentido (funcao/obm/pg_id).
    """
    is_super = _is_super()
    is_super_or_perm = pode_ver_ferias_super()
    funcao_id = int(getattr(current_user, "funcao_user_id", 0) or 0)

    # ===== Regras antigas equivalentes =====
    pode_novo = (funcao_id == 12)  # declaração vínculo (antigo)
    pode_recebimento = funcao_id in {1, 2, 5, 6, 7}
    pode_ver_validacoes = pode_recebimento or _rule_user_id_is(394)
    pode_paf = _rule_paf_solicitante()

    nav: List[Dict[str, Any]] = []

    # Início
    nav.append(_mk_item("Início", "home", icon="fas fa-home"))

    # Declaração de Vínculo (no antigo, estava “apagado” / comentado)
    # Aqui eu deixo como item controlável por permissão, mas respeitando o "pode_novo".
    nav.append(
        _mk_item(
            "Declaração de Vínculo",
            "acumulo.novo",
            icon="fas fa-user",
            perm="NAV_DECLARACAO_VINCULO",
            rule=(lambda: is_super or pode_novo) if militar_id_atual else (
                lambda: False),
            endpoint_kwargs={
                "militar_id": militar_id_atual} if militar_id_atual else {},
        )
    )

    # Validações
    nav.append(
        _mk_group(
            "Validações",
            icon="fas fa-user-friends",
            perm="NAV_VALIDACOES",
            rule=(lambda: is_super or pode_ver_validacoes),
            children=[
                _mk_item(
                    "Declarações — Recebimento",
                    "acumulo.recebimento",
                    perm="NAV_VALIDACOES_RECEBIMENTO",
                ),
                _mk_item(
                    "Validação PAF",
                    "paf.recebimento",
                    perm="NAV_VALIDACOES_PAF",
                    rule=(lambda: is_super or pode_recebimento),
                ),
                _mk_item(
                    "Processos Inclusão de Dependentes",
                    "dep.drh_lista_processos",
                    perm="NAV_VALIDACOES_DEP_PROCESSOS",
                    rule=(lambda: is_super or pode_recebimento),
                ),
            ],
        )
    )

    nav.append(
        _mk_group(
            "TAF",
            icon="fas fa-stopwatch",
            perm="NAV_TAF",
            rule=(lambda: is_super or can_see_taf_panel()),
            children=[
                _mk_item(
                    "Painel de Avaliações",
                    "taf_admin.painel",
                    icon="fas fa-clipboard-check",
                    perm="NAV_TAF_PAINEL",
                    rule=(lambda: is_super or can_see_taf_panel()),
                ),
            ],
        )
    )

    # Plano Anual de Férias (Solicitante)
    nav.append(
        _mk_group(
            "Plano Anual de Férias",
            icon="fas fa-user-friends",
            perm="NAV_PAF_SOLICITANTE",
            rule=(lambda: is_super or pode_paf),
            children=[
                _mk_item("Solicitação", "paf.novo", perm="NAV_PAF_NOVO"),
                _mk_item("Minhas Solicitações", "paf.minhas",
                         perm="NAV_PAF_MINHAS"),
            ],
        )
    )

    # Inclusão de Dependentes (Solicitante)
    nav.append(
        _mk_group(
            "Inclusão de Dependentes",
            icon="fas fa-user-friends",
            perm="NAV_DEP_SOLICITANTE",
            rule=_rule_true,  # regra específica em cada item, pois pode ser diferente
            children=[
                _mk_item("Solicitar Inclusão", "dep.requerimento_form",
                         perm="NAV_DEP_REQUERER"),
                _mk_item("Acompanhar solicitação",
                         "dep.militar_acompanhar", perm="NAV_DEP_ACOMPANHAR"),
            ],
        )
    )

    # DRH / SUPER (Documentação, Militares, Motoristas, Pagadoria, Convocação e afins) — regra antiga: funcao in {5,6,7,12}
    rule_drh_like = (lambda: is_super or _rule_funcao_in([5, 6, 7, 12]))

    nav.append(
        _mk_group(
            "Documentação",
            icon="fas fa-id-card",
            perm="NAV_DOCS",
            rule=rule_drh_like,
            children=[
                _mk_item("Licença Especial", "gerar_le", perm="NAV_DOCS_LE"),
                _mk_item("Indeferida Licença Especial",
                         "indeferimento_le", perm="NAV_DOCS_LE_INDEF"),
                _mk_item("Licença Paternidade",
                         "gerar_lp", perm="NAV_DOCS_LP"),
                _mk_item("Certidão de Casamento",
                         "gerar_certidao_casamento", perm="NAV_DOCS_CASAMENTO"),
                _mk_item("Certidão de Óbito", "gerar_certidao_obito",
                         perm="NAV_DOCS_OBITO"),
                _mk_item("Tempo de Serviço", "certidao_tempo_servico",
                         perm="NAV_DOCS_TEMPO"),
                _mk_item("Exercício de Atividade Atípica",
                         "certidao_exercicio_atv_atipica", perm="NAV_DOCS_ATIPICA"),
                _mk_item("Declaração", "declaracao",
                         perm="NAV_DOCS_DECLARACAO"),
                _mk_item("Nota de Elogio", "nota_elogio",
                         perm="NAV_DOCS_ELOGIO"),
            ],
        )
    )

    nav.append(
        _mk_group(
            "Militares Ativos",
            icon="fas fa-user-friends",
            perm="NAV_MIL_ATIVOS",
            rule=rule_drh_like,
            children=[
                _mk_item("Mapa da Força", "militares",
                         perm="NAV_MIL_ATIVOS_MAPA"),
                _mk_item("Adicionar Militar", "adicionar_militar",
                         perm="NAV_MIL_ATIVOS_ADD"),
                _mk_item("Importar Planilha", "tela_importar_militares",
                         perm="NAV_MIL_ATIVOS_IMPORT"),
                _mk_item("Militares a disposição",
                         "militares_a_disposicao", perm="NAV_MIL_ATIVOS_DISP"),
                _mk_item("Militares agregados", "militares_agregados",
                         perm="NAV_MIL_ATIVOS_AGREG"),
                _mk_item("Licença Especial", "licenca_especial",
                         perm="NAV_MIL_ATIVOS_LE"),
                _mk_item("LTS", "lts", perm="NAV_MIL_ATIVOS_LTS"),
                _mk_item("Militares por cadete", "relatorio_cadetes_militares",
                         perm="NAV_MIL_ATIVOS_CADETES"),
                _mk_item(
                    "Histórico do Militar",
                    "historico_militar.pagina_historico",
                    icon="fas fa-history",
                    perm="NAV_HISTORICO_MILITAR",
                    # ou só (lambda: True) se quiser liberar pra qualquer função, desde que tenha perm
                    rule=rule_drh_like,
                ),
            ],
        )
    )

    nav.append(
        _mk_group(
            "Militares Inativos",
            icon="fas fa-user-friends",
            perm="NAV_MIL_INATIVOS",
            rule=rule_drh_like,
            children=[
                _mk_item("Mapa da Força Inativos",
                         "listar_militares_inativos", perm="NAV_MIL_INATIVOS_MAPA"),
                _mk_item("Adicionar Militar Inativo",
                         "adicionar_militar_inativo", perm="NAV_MIL_INATIVOS_ADD"),
            ],
        )
    )

    nav.append(
        _mk_group(
            "Motoristas",
            icon="fas fa-id-card",
            perm="NAV_MOTORISTAS",
            rule=rule_drh_like,
            children=[
                _mk_item("Adicionar Motorista", "adicionar_motorista",
                         perm="NAV_MOTORISTAS_ADD"),
                _mk_item("Mapa Motoristas", "motoristas",
                         perm="NAV_MOTORISTAS_MAPA"),
                _mk_item("Motoristas Desclassificados",
                         "motoristas_desclassificados", perm="NAV_MOTORISTAS_DESC"),
                _mk_item("Listar CNHs", "listar_cnhs",
                         perm="NAV_MOTORISTAS_CNH"),
                _mk_item("Viaturas", "escolher_obm", perm="NAV_VIATURAS"),
            ],
        )
    )

    nav.append(
        _mk_group(
            "Pagadoria",
            icon="fas fa-dollar-sign",
            perm="NAV_PAGADORIA",
            rule=rule_drh_like,
            children=[
                _mk_item("Nova Tabela de Vencimentos",
                         "novo_vencimento", perm="NAV_PAGADORIA_TABELA"),
                _mk_item("Cálculo de Impacto", "calcular_impacto",
                         perm="NAV_PAGADORIA_IMPACTO"),
            ],
        )
    )

    # nav.append(
    #     _mk_group(
    #         "Convocação Concurso",
    #         icon="fas fa-id-card",
    #         perm="NAV_CONVOCACAO",
    #         rule=rule_drh_like,
    #         children=[
    #             _mk_item("Relatório Convocação",
    #                      "relatorio_convocacao", perm="NAV_CONVOCACAO_REL"),
    #             _mk_item("Adicionar Convocado", "adicionar_convocacao",
    #                      perm="NAV_CONVOCACAO_ADD"),
    #             _mk_item("Importar Convocados", "importar_convocados",
    #                      perm="NAV_CONVOCACAO_IMPORT"),
    #             _mk_item("Controle Convocacao", "controle_convocacao",
    #                      perm="NAV_CONVOCACAO_CTRL"),
    #             _mk_item("Dashboard", "dashboard", perm="NAV_CONVOCACAO_DASH"),
    #         ],
    #     )
    # )

    # Alunos Soldados
    nav.append(
        _mk_group(
            "Alunos Soldados",
            icon="fas fa-user-graduate",
            perm="NAV_ALUNOS",
            rule=(lambda: is_super or _rule_alunos_total()),
            children=[
                _mk_item("Nova Ficha", "ficha_aluno", perm="NAV_ALUNOS_NOVA"),
                _mk_item("Ver Fichas", "listar_fichas",
                         perm="NAV_ALUNOS_LISTAR"),
                _mk_item("Ver Alunos Inativos",
                         "listar_alunos_inativos", perm="NAV_ALUNOS_INATIVOS"),
                _mk_item("Ver Alunos em LTS", "listar_alunos_em_lts",
                         perm="NAV_ALUNOS_LTS"),
                _mk_item("Pelotão Rio Javari", "listar_por_pelotao",
                         perm="NAV_ALUNOS_JAVARI", endpoint_kwargs={"slug": "rio-javari"}),
                _mk_item("Pelotão Rio Juruá", "listar_por_pelotao",
                         perm="NAV_ALUNOS_JURUA", endpoint_kwargs={"slug": "rio-jurua"}),
                _mk_item("Pelotão Rio Japurá", "listar_por_pelotao",
                         perm="NAV_ALUNOS_JAPURA", endpoint_kwargs={"slug": "rio-japura"}),
                _mk_item("Pelotão Rio Purus", "listar_por_pelotao",
                         perm="NAV_ALUNOS_PURUS", endpoint_kwargs={"slug": "rio-purus"}),
            ],
        )
    )

    # Pelotões isolados (funcao 8/9/10/11) — regra antiga
    nav.append(_mk_item("📊 Pelotão Rio Javari", "listar_por_pelotao", perm="NAV_ALUNOS_JAVARI", rule=(
        lambda: is_super or _rule_funcao_in([8])), endpoint_kwargs={"slug": "rio-javari"}))
    nav.append(_mk_item("📊 Pelotão Rio Juruá", "listar_por_pelotao", perm="NAV_ALUNOS_JURUA", rule=(
        lambda: is_super or _rule_funcao_in([9])), endpoint_kwargs={"slug": "rio-jurua"}))
    nav.append(_mk_item("📊 Pelotão Rio Japurá", "listar_por_pelotao", perm="NAV_ALUNOS_JAPURA", rule=(
        lambda: is_super or _rule_funcao_in([10])), endpoint_kwargs={"slug": "rio-japura"}))
    nav.append(_mk_item("📊 Pelotão Rio Purus", "listar_por_pelotao", perm="NAV_ALUNOS_PURUS", rule=(
        lambda: is_super or _rule_funcao_in([11])), endpoint_kwargs={"slug": "rio-purus"}))

    # Utilidades (só super user no antigo)
    nav.append(
        _mk_group(
            "Utilidades",
            icon="fas fa-tools",
            perm="NAV_UTILIDADES",
            rule=(lambda: is_super or _rule_funcao_in([6])),
            children=[
                _mk_item("Usuários", "usuarios", perm="NAV_UTIL_USUARIOS"),
                _mk_item("Adicionar Usuário", "criar_conta",
                         perm="NAV_UTIL_CRIAR"),
            ],
        )
    )

    nav.append(
        _mk_group(
            "Ferramentas",
            icon="fas fa-tools",
            perm="NAV_FERRAMENTAS",
            rule=rule_drh_like,
            children=[
                _mk_item(
                    "Gerar QrCodes",
                    "gerar_qrcodes",
                    icon="fas fa-qrcode",
                    perm="NAV_FERRAMENTAS_QR",
                ),
                _mk_item(
                    "Removedor de Fundo",
                    "remove_bg.remover_fundo",
                    icon="fas fa-image",
                    perm="NAV_FERRAMENTAS_REMOVE_BG",
                ),
            ],
        )
    )

    # Férias (chefe/diretor e super)
    nav.append(
        _mk_group(
            "Férias",
            icon="fas fa-tools",
            perm="NAV_FERIAS",
            rule=(lambda: is_super or _rule_funcao_in([1, 2, 7])),
            children=[_mk_item("Férias", "exibir_ferias_chefe",
                               perm="NAV_FERIAS_CHEFIA")],
        )
    )
    nav.append(
        _mk_group(
            "Férias",
            icon="fas fa-tools",
            perm="NAV_FERIAS",
            rule=(lambda: pode_ver_ferias_super() or _rule_funcao_in([6])),
            children=[_mk_item("Férias", "exibir_ferias",
                               perm="NAV_FERIAS_SUPER")],
        )
    )

    nav.append(
        _mk_item(
            "Atualização Cadastral",
            "atualizacao_cadastral.atualizar",
            icon="fas fa-address-card",
            perm="NAV_ATUALIZACAO_CADASTRAL",
            rule=(lambda: getattr(current_user, "is_authenticated", False)),
        )
    )

    nav.append(
        _mk_group(
            "Gestão Cadastral",
            icon="fas fa-folder-open",
            perm="NAV_ATUALIZACAO_CADASTRAL_PAINEL",
            rule=(lambda: getattr(current_user, "is_authenticated", False)),
            children=[
                _mk_item(
                    "Painel de Atualização",
                    "atualizacao_cadastral.painel",
                    icon="fas fa-chart-line",
                    perm="NAV_ATUALIZACAO_CADASTRAL_PAINEL",
                ),
                _mk_item(
                    "Auditoria Cadastral",
                    "atualizacao_cadastral.auditoria",
                    icon="fas fa-clipboard-list",
                    perm="NAV_ATUALIZACAO_CADASTRAL_AUDITORIA",
                ),
                _mk_item(
                    "Conferência Cadastral",
                    "atualizacao_cadastral.conferencia_lista",
                    icon="fas fa-user-check",
                    perm="NAV_ATUALIZACAO_CADASTRAL_CONFERENCIA",
                ),
            ],
        )
    )

    # Admin (se quiser encaixar no menu do super)
    nav.append(
        _mk_group(
            "Administração",
            icon="fas fa-shield-alt",
            perm="NAV_ADMIN",
            rule=(lambda: is_super),
            children=[
                _mk_item("Permissões (Usuários)",
                         "admin_permissoes.index", perm="NAV_ADMIN_PERMISSOES"),
                _mk_item("OBM Gestão (Gestoras/Subordinadas)",
                         "admin_obm_gestao.index", perm="NAV_ADMIN_OBM_GESTAO"),

                # NOVO ITEM ADICIONADO AQUI:
                _mk_item("Auditoria de Exportações",
                         "auditoria_exportacoes", perm="NAV_ADMIN_AUDITORIA"),
                _mk_item("Auditoria de Acessos",
                         "auditoria_acessos", perm="NAV_ADMIN_AUDITORIA_ACESSOS"),
            ],
        )
    )

    print("DEBUG funcao_user_id:", getattr(
        current_user, "funcao_user_id", None))
    print("DEBUG session pg_id:", session.get("pg_id"))

    # Filtra por visibilidade/permissão
    visible = [n for n in nav if _is_visible(n)]
    return visible
