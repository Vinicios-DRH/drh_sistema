import os
import unicodedata
from src import database, app  # certifique-se de importar o `app` do seu projeto
from src.models import FichaAluno

# Caminho das fotos
pasta_fotos = 'src/static/uploads/fotos'


def formatar_nome(nome):
    nome = unicodedata.normalize('NFKD', nome).encode(
        'ASCII', 'ignore').decode('utf-8')
    return nome.strip().lower().replace(' ', '_')


with app.app_context():
    fotos_disponiveis = os.listdir(pasta_fotos)
    atualizados = 0

    for aluno in FichaAluno.query.all():
        nome_formatado = formatar_nome(aluno.nome_completo)
        foto_match = next(
            (f for f in fotos_disponiveis if f.startswith(nome_formatado)), None)

        if foto_match:
            aluno.foto = f'uploads/fotos/{foto_match}'
            atualizados += 1

    database.session.commit()
    print(f'{atualizados} registros atualizados com sucesso.')
