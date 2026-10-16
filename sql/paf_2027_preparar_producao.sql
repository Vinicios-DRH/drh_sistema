-- =============================================================================
-- PAF 2027 — preparar o banco de produção
-- Supabase > SQL Editor.
--
-- Quem pode preencher o PAF agora é controlado pelo CÓDIGO (posto do militar:
-- paf_service.PAF_POSTOS_LIBERADOS = CEL, TC e MAJ). Não precisa mexer em
-- permissões aqui. Este script só cria as vagas e ajuda a limpar PAFs de teste.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1) CONFERÊNCIA (só leitura): PAFs de 2027 já enviados
--    Procure aqui o PAF que você enviou para teste e anote o "id".
-- -----------------------------------------------------------------------------
select p.id, pg.sigla as posto, m.nome_completo, p.status,
       p.opcao_1, p.opcao_2, p.opcao_3, p.mes_definido, p.created_at
from novo_paf p
join militar m on m.id = p.militar_id
left join posto_grad pg on pg.id = m.posto_grad_id
where p.ano_referencia = 2027
order by p.created_at desc;


-- -----------------------------------------------------------------------------
-- 2) APAGAR PAF DE TESTE (opcional)
--    Troque 0 pelo id anotado acima, tire os "--" das 4 linhas e rode só elas.
--    Apaga só aquele PAF de 2027; o militar poderá enviar de novo quando liberado.
-- -----------------------------------------------------------------------------
-- begin;
-- delete from paf_ferias_plano where ano_referencia = 2027 and militar_id = (select militar_id from novo_paf where id = 0 and ano_referencia = 2027);
-- delete from novo_paf where id = 0 and ano_referencia = 2027;
-- commit;


-- -----------------------------------------------------------------------------
-- 3) VAGAS POR MÊS DE 2027
--    Efetivo ativo / 12 (o resto vai para os primeiros meses) — mesma regra do
--    botão "distribuir automaticamente" da tela de Capacidade.
--    Se 2027 já tiver vagas cadastradas, mantém as existentes.
-- -----------------------------------------------------------------------------
begin;

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

commit;

-- Conferência
select mes, limite from paf_capacidade where ano = 2027 order by mes;
