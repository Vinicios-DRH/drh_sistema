# utils_cpf.py
def so_digitos(s: str) -> str:
    return ''.join(filter(str.isdigit, s or ''))

def formatar_cpf(cpf: str) -> str:
    d = so_digitos(cpf)
    if len(d) != 11:
        return cpf  # deixa como veio se não tiver 11
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"