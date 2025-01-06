import psycopg2

# Função para ler o conteúdo do arquivo SQL
def ler_arquivo_sql(nome_arquivo):
    with open(nome_arquivo, 'r') as file:
        sql_script = file.read()
    return sql_script

# Conectar ao banco de dados Supabase (PostgreSQL)
pg_conn = psycopg2.connect(
    host="db.cselsnczhbsinizmwtcv.supabase.co",
    port="5432",
    database="postgres",
    user="postgres",
    password="drhsistema2025"
)
pg_cursor = pg_conn.cursor()

# Ler o arquivo SQL
sql_script = ler_arquivo_sql('C:\Flask\DRH-SISTEMA\DRH2.sql')

try:
    # Executar o script SQL
    pg_cursor.execute(sql_script)
    pg_conn.commit()
    print("Todos os dados foram inseridos com sucesso!")
except Exception as e:
    print(f"Erro ao executar o script SQL: {e}")
    pg_conn.rollback()
finally:
    # Fechar as conexões
    pg_cursor.close()
    pg_conn.close()
