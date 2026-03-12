from src.models import EstadoCivil


LABELS_CAMPOS_CADASTRO = {
    "grau_instrucao": "Grau de instrução",
    "raca": "Raça/Cor",
    "nome_pai": "Nome do pai",
    "nome_mae": "Nome da mãe",
    "estado_civil": "Estado civil",
    "data_nascimento": "Data de nascimento",
    "endereco": "Endereço",
    "cidade": "Cidade",
    "estado": "UF",
    "cep": "CEP",
    "celular": "Celular",
    "email": "E-mail",
    "local_nascimento": "Local de nascimento",
    "altura": "Altura",
    "cor_olhos": "Cor dos olhos",
    "cor_cabelos": "Cor dos cabelos",
    "medida_cabeca": "Medida da cabeça",
    "numero_sapato": "Número do sapato",
    "medida_calca": "Medida da calça",
    "medida_camisa": "Medida da camisa",
    "tipo_sanguineo": "Tipo sanguíneo",
    "local_tatuagem": "Local da tatuagem",
    "contato_emergencia": "Contato de emergência",
    "conjuge_nome": "Nome do cônjuge",
}


def _is_empty(value):
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _estado_civil_nome(militar):
    if not getattr(militar, "estado_civil", None):
        return ""

    estado = EstadoCivil.query.get(militar.estado_civil)
    if not estado:
        return ""

    return (estado.estado or "").strip().upper()


def _exige_conjuge(militar):
    nome = _estado_civil_nome(militar)
    return nome in {"CASADO", "CASADA", "UNIÃO ESTÁVEL", "UNIAO ESTAVEL"}


def campos_obrigatorios_cadastro(m):
    return {
        "grau_instrucao": m.grau_instrucao,
        "raca": m.raca,
        "nome_pai": m.nome_pai,
        "nome_mae": m.nome_mae,
        "estado_civil": m.estado_civil,
        "data_nascimento": m.data_nascimento,
        "endereco": m.endereco,
        "cidade": m.cidade,
        "estado": m.estado,
        "cep": m.cep,
        "celular": m.celular,
        "email": m.email,
        "local_nascimento": getattr(m, "local_nascimento", None),
        "altura": getattr(m, "altura", None),
        "cor_olhos": getattr(m, "cor_olhos", None),
        "cor_cabelos": getattr(m, "cor_cabelos", None),
        "medida_cabeca": getattr(m, "medida_cabeca", None),
        "numero_sapato": getattr(m, "numero_sapato", None),
        "medida_calca": getattr(m, "medida_calca", None),
        "medida_camisa": getattr(m, "medida_camisa", None),
        "tipo_sanguineo": getattr(m, "tipo_sanguineo", None),
    }


def get_campos_pendentes_cadastro(m):
    pendentes = []

    # Campos principais do militar
    for nome, valor in campos_obrigatorios_cadastro(m).items():
        if _is_empty(valor):
            pendentes.append(nome)

    # Tatuagem -> local obrigatório
    tatuagem = getattr(m, "tatuagem", None)
    local_tatuagem = getattr(m, "local_tatuagem", None)
    if tatuagem is True and _is_empty(local_tatuagem):
        pendentes.append("local_tatuagem")

    # Pelo menos 1 contato de emergência
    contatos = getattr(m, "contatos_emergencia", []) or []
    contatos_validos = [
        c for c in contatos
        if not _is_empty(getattr(c, "nome", None)) and not _is_empty(getattr(c, "telefone", None))
    ]
    if len(contatos_validos) == 0:
        pendentes.append("contato_emergencia")

    # Cônjuge obrigatório em alguns estados civis
    if _exige_conjuge(m):
        conjuge = getattr(m, "conjuge_cadastral", None)
        if not conjuge or _is_empty(getattr(conjuge, "nome", None)):
            pendentes.append("conjuge_nome")

    # Remove duplicados preservando ordem
    pendentes_unicos = []
    for item in pendentes:
        if item not in pendentes_unicos:
            pendentes_unicos.append(item)

    return pendentes_unicos


def cadastro_esta_completo(m):
    return len(get_campos_pendentes_cadastro(m)) == 0


def get_labels_campos_pendentes(campos_pendentes):
    return [
        LABELS_CAMPOS_CADASTRO.get(campo, campo.replace("_", " ").title())
        for campo in campos_pendentes
    ]
