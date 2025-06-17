def formatar_cpf(cpf):
    # Transforma 12345678900 em 123.456.789-00
    cpf = ''.join(filter(str.isdigit, cpf))
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
