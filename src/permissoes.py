# PERMISSOES_CATALOGO (src/permissoes.py)

PERMISSOES_CATALOGO = [
    # ===== NAV (geral) =====
    {"codigo": "NAV_DECLARACAO_VINCULO", "nome": "Menu: Declaração de Vínculo"},
    {"codigo": "NAV_VALIDACOES", "nome": "Menu: Validações (grupo)"},
    {"codigo": "NAV_VALIDACOES_RECEBIMENTO",
        "nome": "Menu: Validações > Declarações — Recebimento"},
    {"codigo": "NAV_VALIDACOES_PAF", "nome": "Menu: Validações > Validação PAF"},
    {"codigo": "NAV_VALIDACOES_DEP_PROCESSOS",
        "nome": "Menu: Validações > Processos Inclusão de Dependentes"},

    {"codigo": "NAV_PAF_SOLICITANTE",
        "nome": "Menu: Plano Anual de Férias (solicitante)"},
    {"codigo": "NAV_PAF_NOVO", "nome": "Menu: PAF > Solicitação"},
    {"codigo": "NAV_PAF_MINHAS", "nome": "Menu: PAF > Minhas Solicitações"},

    {"codigo": "NAV_DEP_SOLICITANTE",
        "nome": "Menu: Inclusão de Dependentes (solicitante)"},
    {"codigo": "NAV_DEP_REQUERER", "nome": "Menu: Dependentes > Solicitar Inclusão"},
    {"codigo": "NAV_DEP_ACOMPANHAR",
        "nome": "Menu: Dependentes > Acompanhar Solicitação"},

    # ===== Documentação =====
    {"codigo": "NAV_DOCS", "nome": "Menu: Documentação (grupo)"},
    {"codigo": "NAV_DOCS_LE", "nome": "Menu: Documentação > Licença Especial"},
    {"codigo": "NAV_DOCS_LE_INDEF",
        "nome": "Menu: Documentação > Indeferida Licença Especial"},
    {"codigo": "NAV_DOCS_LP", "nome": "Menu: Documentação > Licença Paternidade"},
    {"codigo": "NAV_DOCS_CASAMENTO",
        "nome": "Menu: Documentação > Certidão de Casamento"},
    {"codigo": "NAV_DOCS_OBITO", "nome": "Menu: Documentação > Certidão de Óbito"},
    {"codigo": "NAV_DOCS_TEMPO", "nome": "Menu: Documentação > Tempo de Serviço"},
    {"codigo": "NAV_DOCS_ATIPICA",
        "nome": "Menu: Documentação > Exercício de Atividade Atípica"},
    {"codigo": "NAV_DOCS_DECLARACAO", "nome": "Menu: Documentação > Declaração"},
    {"codigo": "NAV_DOCS_ELOGIO", "nome": "Menu: Documentação > Nota de Elogio"},

    # ===== Militares =====
    {"codigo": "NAV_MIL_ATIVOS", "nome": "Menu: Militares Ativos (grupo)"},
    {"codigo": "NAV_MIL_ATIVOS_MAPA", "nome": "Menu: Militares Ativos > Mapa da Força"},
    {"codigo": "NAV_MIL_ATIVOS_ADD",
        "nome": "Menu: Militares Ativos > Adicionar Militar"},
    {"codigo": "NAV_MIL_ATIVOS_DISP",
        "nome": "Menu: Militares Ativos > Militares à disposição"},
    {"codigo": "NAV_MIL_ATIVOS_AGREG",
        "nome": "Menu: Militares Ativos > Militares agregados"},
    {"codigo": "NAV_MIL_ATIVOS_LE", "nome": "Menu: Militares Ativos > Licença Especial"},
    {"codigo": "NAV_MIL_ATIVOS_LTS", "nome": "Menu: Militares Ativos > LTS"},
    {"codigo": "NAV_MIL_ATIVOS_QR", "nome": "Menu: Militares Ativos > Gerar QrCodes"},
    {"codigo": "NAV_MIL_ATIVOS_CADETES",
        "nome": "Menu: Militares Ativos > Militares por cadete"},

    {"codigo": "NAV_MIL_INATIVOS", "nome": "Menu: Militares Inativos (grupo)"},
    {"codigo": "NAV_MIL_INATIVOS_MAPA",
        "nome": "Menu: Militares Inativos > Mapa da Força Inativos"},
    {"codigo": "NAV_MIL_INATIVOS_ADD",
        "nome": "Menu: Militares Inativos > Adicionar Militar Inativo"},

    # ===== Militar (CRUD) =====
    {"codigo": "MILITAR_READ",   "nome": "Militares: Ler ficha"},
    {"codigo": "MILITAR_CREATE", "nome": "Militares: Adicionar"},
    {"codigo": "MILITAR_UPDATE", "nome": "Militares: Atualizar ficha"},
    {"codigo": "MILITAR_DELETE", "nome": "Militares: Excluir/Inativar"},

    # ===== Férias (CRUD) =====
    {"codigo": "FERIAS_READ",   "nome": "Férias: Ler"},
    {"codigo": "FERIAS_CREATE", "nome": "Férias: Criar"},
    {"codigo": "FERIAS_UPDATE", "nome": "Férias: Atualizar"},
    {"codigo": "FERIAS_DELETE", "nome": "Férias: Deletar"},


    # ===== Motoristas / Viaturas =====
    {"codigo": "NAV_MOTORISTAS", "nome": "Menu: Motoristas (grupo)"},
    {"codigo": "NAV_MOTORISTAS_ADD", "nome": "Menu: Motoristas > Adicionar Motorista"},
    {"codigo": "NAV_MOTORISTAS_MAPA", "nome": "Menu: Motoristas > Mapa Motoristas"},
    {"codigo": "NAV_MOTORISTAS_DESC",
        "nome": "Menu: Motoristas > Motoristas Desclassificados"},
    {"codigo": "NAV_MOTORISTAS_CNH", "nome": "Menu: Motoristas > Listar CNHs"},
    {"codigo": "NAV_VIATURAS", "nome": "Menu: Viaturas"},

    # ===== Pagadoria =====
    {"codigo": "NAV_PAGADORIA", "nome": "Menu: Pagadoria (grupo)"},
    {"codigo": "NAV_PAGADORIA_TABELA",
        "nome": "Menu: Pagadoria > Nova Tabela de Vencimentos"},
    {"codigo": "NAV_PAGADORIA_IMPACTO",
        "nome": "Menu: Pagadoria > Cálculo de Impacto"},

    # ===== Convocação =====
    {"codigo": "NAV_CONVOCACAO", "nome": "Menu: Convocação Concurso (grupo)"},
    {"codigo": "NAV_CONVOCACAO_REL", "nome": "Menu: Convocação > Relatório"},
    {"codigo": "NAV_CONVOCACAO_ADD", "nome": "Menu: Convocação > Adicionar Convocado"},
    {"codigo": "NAV_CONVOCACAO_IMPORT",
        "nome": "Menu: Convocação > Importar Convocados"},
    {"codigo": "NAV_CONVOCACAO_CTRL", "nome": "Menu: Convocação > Controle"},
    {"codigo": "NAV_CONVOCACAO_DASH", "nome": "Menu: Convocação > Dashboard"},

    # ===== Alunos Soldados =====
    {"codigo": "NAV_ALUNOS", "nome": "Menu: Alunos Soldados (grupo)"},
    {"codigo": "NAV_ALUNOS_NOVA", "nome": "Menu: Alunos > Nova Ficha"},
    {"codigo": "NAV_ALUNOS_LISTAR", "nome": "Menu: Alunos > Ver Fichas"},
    {"codigo": "NAV_ALUNOS_INATIVOS", "nome": "Menu: Alunos > Ver Inativos"},
    {"codigo": "NAV_ALUNOS_LTS", "nome": "Menu: Alunos > Ver em LTS"},
    {"codigo": "NAV_ALUNOS_JAVARI", "nome": "Menu: Alunos > Pelotão Rio Javari"},
    {"codigo": "NAV_ALUNOS_JURUA", "nome": "Menu: Alunos > Pelotão Rio Juruá"},
    {"codigo": "NAV_ALUNOS_JAPURA", "nome": "Menu: Alunos > Pelotão Rio Japurá"},
    {"codigo": "NAV_ALUNOS_PURUS", "nome": "Menu: Alunos > Pelotão Rio Purus"},

    # ===== Utilidades =====
    {"codigo": "NAV_UTILIDADES", "nome": "Menu: Utilidades (grupo)"},
    {"codigo": "NAV_UTIL_USUARIOS", "nome": "Menu: Utilidades > Usuários"},
    {"codigo": "NAV_UTIL_CRIAR", "nome": "Menu: Utilidades > Adicionar Usuário"},

    # ===== Férias =====
    {"codigo": "NAV_FERIAS", "nome": "Menu: Férias (grupo)"},
    {"codigo": "NAV_FERIAS_CHEFIA", "nome": "Menu: Férias > (Chefia)"},
    {"codigo": "NAV_FERIAS_SUPER", "nome": "Menu: Férias > (Super)"},
    {"codigo": "FERIAS_SUPER",
        "nome": "Férias: Super (bypass regras e ações especiais)"},
    {"codigo": "FERIAS_UPDATE", "nome": "Férias: Atualizar PAF"},
    {"codigo": "FERIAS_EDITAR_FORA_JANELA",
        "nome": "Férias: Editar fora do período 10–20"},

    # ===== Admin (opcional) =====
    {"codigo": "NAV_ADMIN", "nome": "Menu: Administração (grupo)"},
    {"codigo": "NAV_ADMIN_PERMISSOES", "nome": "Menu: Administração > Permissões"},
    {"codigo": "NAV_ADMIN_OBM_GESTAO", "nome": "Menu: Administração > OBM Gestão"},
    {"codigo": "SYS_SUPER", "nome": "Sistema: Acesso tipo SUPER (override)"},

    # ===== APP TAF =====
    {"codigo": "APP_TAF_LOGIN", "nome": "App TAF: Pode logar no aplicativo"},
    {"codigo": "APP_TAF_CORRIDA", "nome": "App TAF: Avaliar Corrida 12 min"},
    {"codigo": "APP_TAF_FLEXAO", "nome": "App TAF: Avaliar Flexão (Apoio)"},
    {"codigo": "APP_TAF_ABDOMINAL", "nome": "App TAF: Avaliar Abdominal"},
    {"codigo": "APP_TAF_BARRA_DINAMICA", "nome": "App TAF: Avaliar Barra dinâmica"},
    {"codigo": "APP_TAF_NATACAO", "nome": "App TAF: Avaliar Natação 50m"},
]
