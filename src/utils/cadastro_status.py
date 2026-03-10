def campos_obrigatorios_cadastro(m):
    return {
        "grau_instrucao": m.grau_instrucao,
        "raca": m.raca,
        "estado_civil": m.estado_civil,
        "data_nascimento": m.data_nascimento,
        "inclusao": m.inclusao,
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
    campos = campos_obrigatorios_cadastro(m)
    pendentes = []

    for nome, valor in campos.items():
        if valor is None:
            pendentes.append(nome)
        elif isinstance(valor, str) and not valor.strip():
            pendentes.append(nome)

    tatuagem = getattr(m, "tatuagem", None)
    local_tatuagem = getattr(m, "local_tatuagem", None)

    if tatuagem is True and (not local_tatuagem or not str(local_tatuagem).strip()):
        pendentes.append("local_tatuagem")

    return pendentes


def cadastro_esta_completo(m):
    return len(get_campos_pendentes_cadastro(m)) == 0
