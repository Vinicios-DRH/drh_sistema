-- =============================================================================
-- SIGDP — MÓDULO JUNTA MÉDICA
-- Migração de banco para produção (PostgreSQL / Supabase)
--
-- Data......: 09/09/2026
-- Aplica....: colunas novas em `licencas`, catálogo de restrições,
--             vínculo N:N de restrições por parecer, carga inicial e
--             backfill dos registros antigos.
--
-- COMO RODAR
--   Supabase → SQL Editor → cole este arquivo inteiro → Run.
--   (ou: psql "$DATABASE_URL" -f 2026-09-09_junta_medica.sql)
--
-- SEGURANÇA
--   • Roda inteiro dentro de UMA transação: ou aplica tudo, ou não aplica nada.
--   • É idempotente — rodar de novo não duplica nada nem dá erro.
--   • Só ADICIONA estruturas. Nenhum DROP, nenhuma coluna alterada de tipo,
--     nenhum dado existente apagado. O único UPDATE preenche uma coluna nova
--     em linhas onde ela está NULL.
--
-- PRÉ-REQUISITOS (já devem existir no banco)
--   tabelas: licencas, curso, militar, "user"
-- =============================================================================

BEGIN;


-- -----------------------------------------------------------------------------
-- 0) Confere os pré-requisitos antes de mexer em qualquer coisa.
--    Se faltar alguma tabela, aborta com mensagem clara em vez de estourar
--    um erro obscuro lá na frente.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    faltando text;
BEGIN
    SELECT string_agg(t, ', ')
      INTO faltando
      FROM (VALUES ('licencas'), ('curso'), ('militar'), ('user')) AS v(t)
     WHERE to_regclass('public.' || quote_ident(t)) IS NULL;

    IF faltando IS NOT NULL THEN
        RAISE EXCEPTION
            'Migração abortada: tabela(s) obrigatória(s) não encontrada(s): %',
            faltando;
    END IF;
END
$$;


-- -----------------------------------------------------------------------------
-- 1) COLUNAS NOVAS EM `licencas`
--
--    data_sessao — data em que a Junta se reuniu. É o primeiro campo que o
--                  operador preenche na tela. Fica NULL-able por causa dos
--                  registros antigos; o passo 6 preenche todos eles.
--    curso_id    — curso do catálogo, quando a inspeção é "para fins de curso".
--    curso_nome  — nome do curso gravado por extenso. Sempre preenchido nas
--                  inspeções de curso, inclusive quando o operador digita um
--                  curso novo em "Outros". É denormalizado de propósito: a
--                  nota do BG precisa do texto exato daquele dia, mesmo que o
--                  catálogo mude depois.
-- -----------------------------------------------------------------------------
ALTER TABLE public.licencas
    ADD COLUMN IF NOT EXISTS data_sessao DATE;

ALTER TABLE public.licencas
    ADD COLUMN IF NOT EXISTS curso_id INTEGER;

ALTER TABLE public.licencas
    ADD COLUMN IF NOT EXISTS curso_nome VARCHAR(150);

CREATE INDEX IF NOT EXISTS ix_licencas_data_sessao
    ON public.licencas (data_sessao);

CREATE INDEX IF NOT EXISTS ix_licencas_curso_id
    ON public.licencas (curso_id);


-- Chave estrangeira de curso_id.
-- O Postgres não tem "ADD CONSTRAINT IF NOT EXISTS", daí o bloco condicional.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'fk_licencas_curso'
           AND conrelid = 'public.licencas'::regclass
    ) THEN
        ALTER TABLE public.licencas
            ADD CONSTRAINT fk_licencas_curso
            FOREIGN KEY (curso_id) REFERENCES public.curso (id);
    END IF;
END
$$;


-- -----------------------------------------------------------------------------
-- 2) CATÁLOGO DE TIPOS DE RESTRIÇÃO
--
--    É a lista de checkboxes que aparece no parecer de "APTO COM RESTRIÇÕES /
--    RECOMENDAÇÕES". Quando o operador digita uma restrição nova no campo
--    "Outros", ela entra aqui e já fica marcável no próximo lançamento.
--
--    `ativo` permite aposentar uma restrição sem apagar o histórico de quem
--    já a recebeu. `ordem` controla a sequência na tela.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.junta_restricao_tipo (
    id          SERIAL       PRIMARY KEY,
    nome        VARCHAR(160) NOT NULL UNIQUE,
    ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
    ordem       INTEGER      NOT NULL DEFAULT 100,
    created_at  TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus')
);

COMMENT ON TABLE public.junta_restricao_tipo IS
    'Catálogo de restrições que a Junta Médica marca nos pareceres.';


-- -----------------------------------------------------------------------------
-- 3) RESTRIÇÕES DE CADA PARECER (N:N)
--
--    É N:N de propósito: o mesmo militar pode receber várias restrições no
--    mesmo parecer, e ganhar outras em pareceres seguintes.
--
--    ON DELETE CASCADE no lançamento: se o parecer for removido, os vínculos
--    vão junto. Já o tipo de restrição NÃO tem cascade — apagar um tipo em uso
--    deve falhar, e não sumir silenciosamente com o histórico.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.licenca_restricao (
    id                 SERIAL       PRIMARY KEY,
    licenca_id         INTEGER      NOT NULL
                       REFERENCES public.licencas (id) ON DELETE CASCADE,
    restricao_tipo_id  INTEGER      NOT NULL
                       REFERENCES public.junta_restricao_tipo (id),
    detalhe            VARCHAR(255),
    created_at         TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus'),

    CONSTRAINT uq_licenca_restricao UNIQUE (licenca_id, restricao_tipo_id)
);

CREATE INDEX IF NOT EXISTS ix_licenca_restricao_licenca
    ON public.licenca_restricao (licenca_id);

CREATE INDEX IF NOT EXISTS ix_licenca_restricao_tipo
    ON public.licenca_restricao (restricao_tipo_id);

COMMENT ON TABLE public.licenca_restricao IS
    'Restrições marcadas em cada parecer da Junta Médica.';


-- -----------------------------------------------------------------------------
-- 3.1) Alinha o DEFAULT de created_at ao fuso do sistema.
--
--      O sistema grava horário de Manaus em coluna sem fuso. O Supabase roda
--      em UTC, então um `now()` puro gravaria 4 horas à frente em qualquer
--      inserção feita fora da aplicação (SQL Editor, carga manual). Estes
--      ALTERs garantem o default correto mesmo se as tabelas já existirem de
--      uma execução anterior deste script.
-- -----------------------------------------------------------------------------
ALTER TABLE public.junta_restricao_tipo
    ALTER COLUMN created_at SET DEFAULT (now() AT TIME ZONE 'America/Manaus');

ALTER TABLE public.licenca_restricao
    ALTER COLUMN created_at SET DEFAULT (now() AT TIME ZONE 'America/Manaus');


-- -----------------------------------------------------------------------------
-- 4) CARGA INICIAL DO CATÁLOGO DE RESTRIÇÕES
--
--    Lista de partida. O ON CONFLICT deixa o script re-executável e preserva
--    qualquer restrição que a Junta já tenha cadastrado pela tela.
-- -----------------------------------------------------------------------------
INSERT INTO public.junta_restricao_tipo (nome, ativo, ordem) VALUES
    ('Dispensa de esforço físico',                   TRUE,  10),
    ('Dispensa de TAF',                              TRUE,  20),
    ('Dispensa de serviço operacional',              TRUE,  30),
    ('Dispensa de escala de serviço',                TRUE,  40),
    ('Dispensa de guarda / plantão',                 TRUE,  50),
    ('Restrição para atividade em altura',           TRUE,  60),
    ('Restrição para mergulho / atividade aquática', TRUE,  70),
    ('Restrição para combate a incêndio',            TRUE,  80),
    ('Restrição para uso de arma de fogo',           TRUE,  90),
    ('Restrição para condução de viatura',           TRUE, 100),
    ('Restrição para exposição solar prolongada',    TRUE, 110),
    ('Restrição para levantamento de peso',          TRUE, 120),
    ('Somente serviço administrativo / interno',     TRUE, 130),
    ('Uso de calçado apropriado',                    TRUE, 140)
ON CONFLICT (nome) DO NOTHING;


-- -----------------------------------------------------------------------------
-- 5) BACKFILL DE `data_sessao` NOS REGISTROS ANTIGOS
--
--    Os pareceres lançados antes desta versão não têm data de sessão. Usa a
--    data de criação do registro, que é a melhor aproximação disponível —
--    o lançamento era feito no mesmo dia da sessão.
--
--    Sem isso, os registros antigos ficariam de fora do consolidado mensal,
--    que agrupa justamente por `data_sessao`.
-- -----------------------------------------------------------------------------
UPDATE public.licencas
   SET data_sessao = created_at::date
 WHERE data_sessao IS NULL;


COMMIT;


-- =============================================================================
-- CONFERÊNCIA — rode depois do COMMIT para validar o resultado.
-- Esperado: as 3 colunas novas, as 2 tabelas novas, 14 restrições
-- (ou mais, se a Junta já tiver cadastrado outras) e 0 registros sem sessão.
-- =============================================================================
SELECT 'colunas novas em licencas' AS verificacao,
       count(*)::text || ' de 3' AS resultado
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name = 'licencas'
   AND column_name IN ('data_sessao', 'curso_id', 'curso_nome')

UNION ALL
SELECT 'tabelas novas criadas',
       count(*)::text || ' de 2'
  FROM information_schema.tables
 WHERE table_schema = 'public'
   AND table_name IN ('junta_restricao_tipo', 'licenca_restricao')

UNION ALL
SELECT 'índices novos',
       count(*)::text || ' de 4'
  FROM pg_indexes
 WHERE schemaname = 'public'
   AND indexname IN ('ix_licencas_data_sessao', 'ix_licencas_curso_id',
                     'ix_licenca_restricao_licenca', 'ix_licenca_restricao_tipo')

UNION ALL
SELECT 'chave estrangeira do curso',
       count(*)::text || ' de 1'
  FROM pg_constraint
 WHERE conname = 'fk_licencas_curso'

UNION ALL
SELECT 'tipos de restrição no catálogo',
       count(*)::text
  FROM public.junta_restricao_tipo

UNION ALL
SELECT 'registros ainda sem data_sessao (deve ser 0)',
       count(*)::text
  FROM public.licencas
 WHERE data_sessao IS NULL;


-- =============================================================================
-- OPCIONAL — LIBERAÇÃO DE ACESSO AO MÓDULO
--
-- As permissões ficam no CÓDIGO (src/permissoes.py), então o deploy da
-- aplicação já as faz aparecer na tela de Administração > Permissões. Não é
-- preciso rodar nada aqui: o normal é conceder pela tela, marcando os
-- militares responsáveis.
--
-- Este bloco existe só como atalho, para liberar tudo de uma vez a um usuário
-- específico. Para usar: troque o e-mail e remova o comentário do bloco.
--
-- Códigos do módulo:
--   NAV_JUNTA               menu: grupo Junta Médica
--   NAV_JUNTA_NOVA          menu: Nova Inspeção / Licença
--   NAV_JUNTA_LICENCAS      menu: Registros e Licenças
--   NAV_JUNTA_RENOVACOES    menu: Painel de Renovações
--   NAV_JUNTA_ESTATISTICAS  menu: Consolidado Mensal
--   JUNTA_READ              consultar registros, histórico e relatório
--   JUNTA_CREATE            lançar inspeções e restrições
--   JUNTA_EXPORT            exportar Excel
--   JUNTA_BG_FECHAR         finalizar o dia e gerar a nota do BG
--   JUNTA_RENOVACOES_READ   consultar o painel de renovações
-- =============================================================================

-- INSERT INTO public.user_permissao (user_id, codigo, ativo)
-- SELECT u.id, c.codigo, TRUE
--   FROM public."user" u
--  CROSS JOIN (VALUES
--         ('NAV_JUNTA'), ('NAV_JUNTA_NOVA'), ('NAV_JUNTA_LICENCAS'),
--         ('NAV_JUNTA_RENOVACOES'), ('NAV_JUNTA_ESTATISTICAS'),
--         ('JUNTA_READ'), ('JUNTA_CREATE'), ('JUNTA_EXPORT'),
--         ('JUNTA_BG_FECHAR'), ('JUNTA_RENOVACOES_READ')
--       ) AS c(codigo)
--  WHERE u.email = 'troque.pelo@email.do.usuario'
--    AND NOT EXISTS (
--        SELECT 1 FROM public.user_permissao p
--         WHERE p.user_id = u.id AND p.codigo = c.codigo
--    );
