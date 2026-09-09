"""
Migração do módulo da Junta Médica — atalho para o ambiente de desenvolvimento.

Para PRODUÇÃO use `sql/2026-09-09_junta_medica.sql`, que faz exatamente as
mesmas alterações em SQL puro, numa transação só, e roda direto no Supabase.

Roda uma vez (é idempotente — pode rodar de novo sem quebrar nada):

    python migrar_junta.py

O que faz:
  1. Cria as colunas novas em `licencas` (data_sessao, curso_id, curso_nome).
  2. Cria as tabelas `junta_restricao_tipo` e `licenca_restricao`.
  3. Semeia o catálogo inicial de tipos de restrição (só se estiver vazio).
  4. Preenche `data_sessao` dos registros antigos com a data de criação deles.
"""

from sqlalchemy import text

from src import app, database as db
from src.models import JuntaRestricaoTipo

DDL = [
    # --- 1) colunas novas em licencas ---
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS data_sessao DATE",
    "CREATE INDEX IF NOT EXISTS ix_licencas_data_sessao ON licencas (data_sessao)",

    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS curso_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_licencas_curso_id ON licencas (curso_id)",

    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS curso_nome VARCHAR(150)",

    # --- 2) catálogo de tipos de restrição ---
    """
    CREATE TABLE IF NOT EXISTS junta_restricao_tipo (
        id          SERIAL PRIMARY KEY,
        nome        VARCHAR(160) NOT NULL UNIQUE,
        ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
        ordem       INTEGER      NOT NULL DEFAULT 100,
        created_at  TIMESTAMP    NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Manaus')
    )
    """,

    # --- 3) restrições de cada lançamento (N:N) ---
    """
    CREATE TABLE IF NOT EXISTS licenca_restricao (
        id                SERIAL PRIMARY KEY,
        licenca_id        INTEGER      NOT NULL
                          REFERENCES licencas (id) ON DELETE CASCADE,
        restricao_tipo_id INTEGER      NOT NULL
                          REFERENCES junta_restricao_tipo (id),
        detalhe           VARCHAR(255),
        created_at        TIMESTAMP    NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Manaus'),
        CONSTRAINT uq_licenca_restricao UNIQUE (licenca_id, restricao_tipo_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_licenca_restricao_licenca ON licenca_restricao (licenca_id)",
    "CREATE INDEX IF NOT EXISTS ix_licenca_restricao_tipo ON licenca_restricao (restricao_tipo_id)",
]

# FK de curso_id: separada porque, ao contrário das outras, o Postgres não tem
# "ADD CONSTRAINT IF NOT EXISTS" — então checamos antes.
FK_CURSO = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_licencas_curso'
    ) THEN
        ALTER TABLE licencas
            ADD CONSTRAINT fk_licencas_curso
            FOREIGN KEY (curso_id) REFERENCES curso (id);
    END IF;
END
$$;
"""

# Lista inicial de restrições. O operador pode acrescentar outras direto na
# tela pelo campo "Outros" — elas entram nesse mesmo catálogo.
RESTRICOES_PADRAO = [
    "Dispensa de esforço físico",
    "Dispensa de TAF",
    "Dispensa de serviço operacional",
    "Dispensa de escala de serviço",
    "Dispensa de guarda / plantão",
    "Restrição para atividade em altura",
    "Restrição para mergulho / atividade aquática",
    "Restrição para combate a incêndio",
    "Restrição para uso de arma de fogo",
    "Restrição para condução de viatura",
    "Restrição para exposição solar prolongada",
    "Restrição para levantamento de peso",
    "Somente serviço administrativo / interno",
    "Uso de calçado apropriado",
]


def main():
    with app.app_context():
        for comando in DDL:
            db.session.execute(text(comando))
        db.session.execute(text(FK_CURSO))
        db.session.commit()
        print("[OK] Estrutura da Junta criada/atualizada.")

        if JuntaRestricaoTipo.query.count() == 0:
            for ordem, nome in enumerate(RESTRICOES_PADRAO, start=1):
                db.session.add(JuntaRestricaoTipo(
                    nome=nome, ativo=True, ordem=ordem * 10))
            db.session.commit()
            print(
                f"[OK] {len(RESTRICOES_PADRAO)} tipos de restrição cadastrados.")
        else:
            print("[--] Catálogo de restrições já tinha registros; nada semeado.")

        atualizados = db.session.execute(text(
            "UPDATE licencas SET data_sessao = created_at::date "
            "WHERE data_sessao IS NULL"
        )).rowcount
        db.session.commit()
        print(f"[OK] data_sessao preenchida em {atualizados} registro(s) antigo(s).")

        print("\nMigração concluída.")


if __name__ == "__main__":
    main()
