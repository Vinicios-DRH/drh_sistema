"""
<<<<<<< HEAD
Migração do módulo da Junta Médica.

Este script é a fonte única da migração — o `sql/2026-09-09_junta_medica.sql`
que existia antes foi removido no commit 8116d14. Para PRODUÇÃO, rode este
mesmo arquivo com o DATABASE_URL apontando pro banco de produção.
=======
Migração do módulo da Junta Médica — atalho para desenvolvimento.

Executa `sql/2026-09-10_junta_medica.sql` (a mesma migração usada em produção)
contra o banco configurado em DATABASE_URL. Só existe pra não precisar copiar
e colar o SQL manualmente em dev — a fonte da verdade é sempre o arquivo .sql.
>>>>>>> ccbdd07 (melhorias no módulo da JUNTA)

Roda uma vez (é idempotente — pode rodar de novo sem quebrar nada):

    python migrar_junta.py
"""
from pathlib import Path

from sqlalchemy import text

from src import app, database as db

CAMINHO_SQL = Path(__file__).parent / "sql" / "2026-09-10_junta_medica.sql"


def main():
    sql = CAMINHO_SQL.read_text(encoding="utf-8")

    # O arquivo tem BEGIN/COMMIT próprios pra rodar sozinho no Supabase SQL
    # Editor. Aqui quem controla a transação é o SQLAlchemy, então eles saem
    # — o efeito é o mesmo (tudo aplica, ou nada aplica, numa transação só).
    sql = sql.replace("\nBEGIN;", "\n-- BEGIN (dev)")
    sql = sql.replace("\nCOMMIT;", "\n-- COMMIT (dev)")

    with app.app_context():
        db.session.execute(text(sql))
        db.session.commit()
        print(f"[OK] {CAMINHO_SQL.name} aplicado com sucesso.")


if __name__ == "__main__":
    main()
