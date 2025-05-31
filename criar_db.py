import os
import unicodedata
from src import database, app  # certifique-se de importar o `app` do seu projeto
from src.models import FichaAluno, User


with app.app_context():
    usuarios = User.query.all()

    print(f"{'NOME':<30} {'FUNÇÃO':<20} {'OBM 1':<25} {'OBM 2':<25}")
    print("-" * 100)

    for user in usuarios:
        nome = user.nome or "Sem nome"
        funcao = user.funcao_user.ocupacao if user.funcao_user else "Não definida"
        obm1 = user.obm1.sigla if user.obm1 else "Não definida"
        obm2 = user.obm2.sigla if user.obm2 else "Não definida"

        print(f"{nome:<30} {funcao:<20} {obm1:<25} {obm2:<25}")
