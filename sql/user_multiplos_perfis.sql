-- Permite o mesmo militar ter duas contas: uma de gestão (tipo_perfil='ADMIN',
-- ex.: chefe) e uma de militar (tipo_perfil='MILITAR', atualização cadastral).
-- A unicidade passa a ser só (cpf_norm, tipo_perfil) — índice
-- uq_user_cpf_norm_tipo, que já existe.

BEGIN;

-- 1. Acerta tipo_perfil pela função (12 → MILITAR, 14 → EXTERNO, resto →
--    ADMIN). O /criar-conta nunca preenchia esse campo, então chefes/DP
--    criados por lá ficaram como MILITAR e bloqueariam a criação da conta de
--    militar deles. Não mexe em quem, com isso, colidiria com outra conta do
--    mesmo CPF (pares que já existem com tipos trocados — revisar à mão).
WITH alvo AS (
    SELECT id,
           coalesce(cpf_norm, regexp_replace(cpf, '[^0-9]', '', 'g')) AS cn,
           CASE WHEN funcao_user_id = 12 THEN 'MILITAR'
                WHEN funcao_user_id = 14 THEN 'EXTERNO'
                ELSE 'ADMIN' END AS tp
    FROM "user"
),
livres AS (
    SELECT a.id, a.tp
    FROM alvo a
    WHERE NOT EXISTS (
        SELECT 1 FROM alvo b WHERE b.cn = a.cn AND b.tp = a.tp AND b.id <> a.id
    )
)
UPDATE "user" u
SET tipo_perfil = l.tp
FROM livres l
WHERE u.id = l.id
  AND u.tipo_perfil IS DISTINCT FROM l.tp;

-- 2. Preenche cpf_norm que ficou nulo (é ele que garante 1 conta por tipo).
UPDATE "user"
SET cpf_norm = regexp_replace(cpf, '[^0-9]', '', 'g')
WHERE cpf_norm IS NULL AND cpf IS NOT NULL;

-- 3. Tira o UNIQUE do cpf com máscara — era ele que impedia a segunda conta.
ALTER TABLE "user" DROP CONSTRAINT IF EXISTS user_cpf_key;
CREATE INDEX IF NOT EXISTS idx_user_cpf ON "user" (cpf);

COMMIT;
