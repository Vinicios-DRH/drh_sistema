-- =============================================================================
-- PAF 2027 — ETAPA 1: preparar o banco e liberar só CEL, TC e MAJ
-- Supabase > SQL Editor. Rodar DEPOIS do deploy do código novo do PAF.
--
-- O que faz:
--   1) Cria as vagas por mês de 2027 (1/12 do efetivo ativo), se ainda não existirem.
--   2) Tira o acesso ao formulário do PAF de todo mundo.
--   3) Libera o acesso para os usuários cujo CPF é de um CEL, TC ou MAJ ativo.
-- Não apaga nenhum registro. Para liberar o restante da tropa, use a ETAPA 2.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 0) CONFERÊNCIAS (só leitura) — rode e confira antes do bloco de alterações
-- -----------------------------------------------------------------------------

-- 0.1 PAFs que já existem para 2027 (o esperado é nenhum; se houver, avalie
--     antes de liberar — cada militar só pode ter 1 PAF por ano)
select p.id, p.militar_id, m.nome_completo, p.status, p.opcao_1, p.opcao_2, p.opcao_3, p.created_at
from novo_paf p
join militar m on m.id = p.militar_id
where p.ano_referencia = 2027
order by p.created_at;

-- 0.2 Vagas de 2027 já cadastradas (se já houver, o passo 1 não sobrescreve)
select mes, limite from paf_capacidade where ano = 2027 order by mes;

-- 0.3 Quem será liberado nesta etapa (posto, militares e usuários)
select pg.sigla as posto,
       count(distinct m.id) as militares,
       count(distinct u.id) as usuarios
from "user" u
join militar m
  on regexp_replace(m.cpf::text, '[^0-9]', '', 'g') = regexp_replace(u.cpf::text, '[^0-9]', '', 'g')
 and regexp_replace(u.cpf::text, '[^0-9]', '', 'g') <> ''
join posto_grad pg on pg.id = m.posto_grad_id
where m.inativo is not true
  and pg.sigla in ('CEL', 'TC', 'MAJ')
group by pg.sigla
order by pg.sigla;


-- -----------------------------------------------------------------------------
-- ALTERAÇÕES
-- -----------------------------------------------------------------------------
begin;

-- 1) Vagas por mês de 2027: efetivo ativo / 12 (o resto vai para os primeiros
--    meses), mesma regra do botão "distribuir automaticamente" da tela de
--    Capacidade. Se 2027 já tiver vagas cadastradas, mantém as existentes.
with efetivo as (
    select count(distinct militar_id) as n
    from militar_obm_funcao
    where data_fim is null
)
insert into paf_capacidade (ano, mes, limite)
select 2027,
       mes,
       efetivo.n / 12 + case when mes <= efetivo.n % 12 then 1 else 0 end
from efetivo, generate_series(1, 12) as mes
on conflict (ano, mes) do nothing;

-- 2) Ninguém preenche até ser liberado (SUPER USER continua com acesso)
update user_permissao
set ativo = false
where codigo in ('NAV_PAF_SOLICITANTE', 'NAV_PAF_NOVO', 'NAV_PAF_MINHAS');

-- 3) Libera CEL, TC e MAJ ativos (menu + formulário + "Minhas Solicitações")
insert into user_permissao (user_id, codigo, ativo)
select distinct u.id, c.codigo, true
from "user" u
join militar m
  on regexp_replace(m.cpf::text, '[^0-9]', '', 'g') = regexp_replace(u.cpf::text, '[^0-9]', '', 'g')
 and regexp_replace(u.cpf::text, '[^0-9]', '', 'g') <> ''
join posto_grad pg on pg.id = m.posto_grad_id
cross join (values ('NAV_PAF_SOLICITANTE'), ('NAV_PAF_NOVO'), ('NAV_PAF_MINHAS')) as c(codigo)
where m.inativo is not true
  and pg.sigla in ('CEL', 'TC', 'MAJ')
on conflict (user_id, codigo) do update set ativo = true;

commit;


-- -----------------------------------------------------------------------------
-- 4) CONFERÊNCIA FINAL (só leitura)
-- -----------------------------------------------------------------------------

-- 4.1 Vagas de 2027
select mes, limite from paf_capacidade where ano = 2027 order by mes;

-- 4.2 Usuários com o formulário liberado, por posto (deve dar só CEL, TC e MAJ)
select coalesce(pg.sigla, '(sem militar)') as posto, count(distinct p.user_id) as usuarios_liberados
from user_permissao p
join "user" u on u.id = p.user_id
left join militar m
  on regexp_replace(m.cpf::text, '[^0-9]', '', 'g') = regexp_replace(u.cpf::text, '[^0-9]', '', 'g')
 and regexp_replace(u.cpf::text, '[^0-9]', '', 'g') <> ''
 and m.inativo is not true
left join posto_grad pg on pg.id = m.posto_grad_id
where p.codigo = 'NAV_PAF_NOVO' and p.ativo
group by 1
order by 1;
