from datetime import datetime


def formatar_data_extenso(data_str):
    meses = {
        "01": "janeiro", "02": "fevereiro", "03": "março", "04": "abril",
        "05": "maio", "06": "junho", "07": "julho", "08": "agosto",
        "09": "setembro", "10": "outubro", "11": "novembro", "12": "dezembro"
    }
    dt = datetime.strptime(data_str, "%Y-%m-%d")
    dia = str(int(dt.strftime("%d")))
    mes = meses[dt.strftime("%m")]
    ano = dt.strftime("%Y")
    return f"{dia} de {mes} de {ano}"


def formatar_data_sem_zero(data_str):
    dt = datetime.strptime(data_str, "%Y-%m-%d")
    return f"{dt.day}/{dt.month}/{dt.year}"
