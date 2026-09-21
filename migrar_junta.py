"""
Migração do módulo da Junta Médica.

Autocontido de propósito — não depende de nenhum arquivo .sql externo (já
aconteceu mais de uma vez de esses arquivos sumirem do disco depois de rodados
manualmente no Supabase). Este script é a fonte única da migração, tanto pra
desenvolvimento quanto como referência de produção.

Roda uma vez (é idempotente — pode rodar de novo sem quebrar nada):

    python migrar_junta.py

Pra produção (Supabase): rode este mesmo arquivo com o DATABASE_URL apontando
pro banco de produção, ou copie os comandos de `SQL` abaixo pro SQL Editor.
"""
from sqlalchemy import text

from src import app, database as db
from src.models import JuntaRestricaoTipo

DDL = [
    # --- estrutura original: colunas de sessão/curso em `licencas` ---
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS data_sessao DATE",
    "CREATE INDEX IF NOT EXISTS ix_licencas_data_sessao ON licencas (data_sessao)",

    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS curso_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_licencas_curso_id ON licencas (curso_id)",

    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS curso_nome VARCHAR(150)",

    # --- catálogo de tipos de restrição ---
    """
    CREATE TABLE IF NOT EXISTS junta_restricao_tipo (
        id          SERIAL PRIMARY KEY,
        nome        VARCHAR(160) NOT NULL UNIQUE,
        ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
        ordem       INTEGER      NOT NULL DEFAULT 100,
        created_at  TIMESTAMP    NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Manaus')
    )
    """,

    # --- restrições de cada lançamento (N:N) ---
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

    # --- reavaliação ao término, inspeção on-line, resultado livre ---
    #
    # reavaliar_ao_termino tem DEFAULT FALSE no banco (e é a caixinha que
    # começa desmarcada na tela): o padrão passou a ser "não precisa
    # reavaliar" — quem decide o contrário é a própria Junta, marcando.
    # ADD COLUMN IF NOT EXISTS não mexe em coluna que já existe, então o
    # ALTER COLUMN logo abaixo garante que um banco que já rodou uma versão
    # anterior desta migração (com DEFAULT TRUE) também fique atualizado.
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS resultado_detalhe VARCHAR(160)",
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS reavaliar_ao_termino BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE licencas ALTER COLUMN reavaliar_ao_termino SET DEFAULT FALSE",
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS online BOOLEAN NOT NULL DEFAULT FALSE",

    # --- errata ---
    "ALTER TABLE junta_fechamento_bg ADD COLUMN IF NOT EXISTS eh_errata BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE junta_fechamento_bg ADD COLUMN IF NOT EXISTS fechamento_original_id INTEGER",
    "ALTER TABLE junta_fechamento_bg ADD COLUMN IF NOT EXISTS numero_bg_publicacao VARCHAR(80)",
    "ALTER TABLE junta_fechamento_bg ADD COLUMN IF NOT EXISTS data_bg_publicacao DATE",
    "ALTER TABLE junta_fechamento_bg ADD COLUMN IF NOT EXISTS onde_se_le TEXT",
    "ALTER TABLE junta_fechamento_bg ADD COLUMN IF NOT EXISTS leia_se TEXT",

    # --- AO (Exame de Controle de Atestado de Origem) e ISO (Parecer
    # Técnico de Inquérito Sanitário de Origem) ---
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS portaria VARCHAR(255)",
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS data_publicacao DATE",
    "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS data_acidente DATE",
]

# Postgres não tem "ADD CONSTRAINT IF NOT EXISTS" — cada FK checa antes.
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

FK_ERRATA = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fechamento_original'
    ) THEN
        ALTER TABLE junta_fechamento_bg
            ADD CONSTRAINT fk_fechamento_original
            FOREIGN KEY (fechamento_original_id) REFERENCES junta_fechamento_bg (id);
    END IF;
END
$$;
"""

# Nomes antigos ainda podem existir num banco que só rodou a versão anterior
# desta migração — renomeia pro padrão atual (sem "Dispensa de"/"Restrição
# para", só o objetivo) em vez de duplicar.
RENOMEIA_RESTRICOES = {
    "Dispensa de esforço físico": "ESFORÇO FÍSICO",
    "Dispensa de TAF": "TAF",
    "Dispensa de serviço operacional": "SERVIÇOS OPERACIONAIS",
    "Dispensa de escala de serviço": "ESCALA DE SERVIÇO",
    "Dispensa de guarda / plantão": "GUARDA/PLANTÃO",
    "Restrição para atividade em altura": "ATIVIDADE EM ALTURA",
    "Restrição para mergulho / atividade aquática": "MERGULHO/ATIVIDADE AQUÁTICA",
    "Restrição para combate a incêndio": "COMBATE A INCÊNDIO",
    "Restrição para uso de arma de fogo": "PORTE DE ARMAS",
    "Restrição para condução de viatura": "CONDUÇÃO DE VIATURA",
    "Restrição para exposição solar prolongada": "EXPOSIÇÃO SOLAR PROLONGADA",
    "Restrição para levantamento de peso": "LEVANTAMENTO DE PESO",
    "Somente serviço administrativo / interno": "SERVIÇO ADMINISTRATIVO/INTERNO",
    "Uso de calçado apropriado": "CALÇADO APROPRIADO",
}

# Catálogo completo, em ordem alfabética (todo mundo com ordem=100 — a lista
# ordena por nome, então uma restrição nova em "Outros" entra naturalmente no
# lugar certo).
RESTRICOES_PADRAO = [
    "ATIVIDADE EM ALTURA",
    "CALÇADO APROPRIADO",
    "COMBATE A INCÊNDIO",
    "CONDUÇÃO DE VIATURA",
    "ESCALA DE SERVIÇO",
    "ESFORÇO FÍSICO",
    "EXPOSIÇÃO SOLAR PROLONGADA",
    "FORMATURA/ORDEM UNIDA",
    "GUARDA/PLANTÃO",
    "LEVANTAMENTO DE PESO",
    "MERGULHO/ATIVIDADE AQUÁTICA",
    "PORTE DE ARMAS",
    "SERVIÇO ADMINISTRATIVO/INTERNO",
    "SERVIÇOS NOTURNOS",
    "SERVIÇOS OPERACIONAIS",
    "TAF",
    "TFM",
]


def main():
    with app.app_context():
        for comando in DDL:
            db.session.execute(text(comando))
        db.session.execute(text(FK_CURSO))
        db.session.execute(text(FK_ERRATA))
        db.session.commit()
        print("[OK] Estrutura da Junta criada/atualizada.")

        renomeados = 0
        for antigo, novo in RENOMEIA_RESTRICOES.items():
            row = JuntaRestricaoTipo.query.filter_by(nome=antigo).first()
            if row:
                row.nome = novo
                row.ordem = 100
                renomeados += 1
        if renomeados:
            db.session.commit()
            print(f"[OK] {renomeados} restrição(ões) renomeada(s) pro padrão atual.")

        criados = 0
        for nome in RESTRICOES_PADRAO:
            if not JuntaRestricaoTipo.query.filter_by(nome=nome).first():
                db.session.add(JuntaRestricaoTipo(nome=nome, ativo=True, ordem=100))
                criados += 1
        if criados:
            db.session.commit()
            print(f"[OK] {criados} tipo(s) de restrição cadastrado(s).")
        else:
            print("[--] Catálogo de restrições já estava completo.")

        # normaliza `ordem` de tudo (inclusive restrições cadastradas via
        # "Outros" pela tela, que nasciam com ordem=999) pra ordenar por nome
        atualizados_ordem = JuntaRestricaoTipo.query.filter(
            JuntaRestricaoTipo.ordem != 100).update({"ordem": 100})
        if atualizados_ordem:
            db.session.commit()
            print(f"[OK] ordem normalizada em {atualizados_ordem} restrição(ões).")

        atualizados = db.session.execute(text(
            "UPDATE licencas SET data_sessao = created_at::date "
            "WHERE data_sessao IS NULL"
        )).rowcount
        db.session.commit()
        print(f"[OK] data_sessao preenchida em {atualizados} registro(s) antigo(s).")

        print("\nMigração concluída.")


if __name__ == "__main__":
    main()
