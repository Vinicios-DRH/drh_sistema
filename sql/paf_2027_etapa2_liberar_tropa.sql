-- =============================================================================
-- PAF 2027 — ETAPA 2: liberar o PAF para o restante da tropa
-- Supabase > SQL Editor. Rodar quando os oficiais superiores já tiverem preenchido.
--
-- Libera menu + formulário + "Minhas Solicitações" para todo usuário cujo CPF
-- é de um militar ativo. Não apaga nem altera PAFs já enviados.
-- =============================================================================


-- 0) Quanto falta dos oficiais superiores (só leitura) — confira antes de liberar
select pg.sigla as posto,
       count(distinct m.id) as militares,
       count(distinct p.militar_id) as ja_enviaram,
       count(distinct m.id) - count(distinct p.militar_id) as faltam
from militar m
join posto_grad pg on pg.id = m.posto_grad_id
left join novo_paf p on p.militar_id = m.id and p.ano_referencia = 2027
where m.inativo is not true
  and pg.sigla in ('CEL', 'TC', 'MAJ')
group by pg.sigla
order by pg.sigla;


begin;

insert into user_permissao (user_id, codigo, ativo)
select distinct u.id, c.codigo, true
from "user" u
join militar m
  on regexp_replace(m.cpf::text, '[^0-9]', '', 'g') = regexp_replace(u.cpf::text, '[^0-9]', '', 'g')
 and regexp_replace(u.cpf::text, '[^0-9]', '', 'g') <> ''
cross join (values ('NAV_PAF_SOLICITANTE'), ('NAV_PAF_NOVO'), ('NAV_PAF_MINHAS')) as c(codigo)
where m.inativo is not true
on conflict (user_id, codigo) do update set ativo = true;

commit;


-- Conferência final (só leitura): usuários liberados por posto/graduação
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
