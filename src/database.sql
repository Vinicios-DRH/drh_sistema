-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.agregacoes (
  id integer NOT NULL DEFAULT nextval('agregacoes_id_seq'::regclass),
  tipo character varying,
  CONSTRAINT agregacoes_pkey PRIMARY KEY (id)
);
CREATE TABLE public.alunos_inativos (
  id integer NOT NULL DEFAULT nextval('alunos_inativos_id_seq'::regclass),
  ficha_aluno_id integer NOT NULL UNIQUE,
  motivo_saida character varying NOT NULL,
  data_saida date NOT NULL,
  usuario_id integer,
  CONSTRAINT alunos_inativos_pkey PRIMARY KEY (id),
  CONSTRAINT alunos_inativos_ficha_aluno_id_fkey FOREIGN KEY (ficha_aluno_id) REFERENCES public.ficha_alunos(id),
  CONSTRAINT alunos_inativos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.auditoria_declaracao (
  id bigint NOT NULL DEFAULT nextval('auditoria_declaracao_id_seq'::regclass),
  declaracao_id bigint NOT NULL,
  de_status character varying,
  para_status character varying NOT NULL,
  motivo text,
  alterado_por_user_id bigint,
  data_alteracao timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT auditoria_declaracao_pkey PRIMARY KEY (id),
  CONSTRAINT auditoria_declaracao_declaracao_id_fkey FOREIGN KEY (declaracao_id) REFERENCES public.declaracao_acumulo(id),
  CONSTRAINT auditoria_declaracao_alterado_por_user_id_fkey FOREIGN KEY (alterado_por_user_id) REFERENCES public.user(id)
);
CREATE TABLE public.categoria (
  id integer NOT NULL,
  sigla character varying,
  CONSTRAINT categoria_pkey PRIMARY KEY (id)
);
CREATE TABLE public.comportamento (
  id integer NOT NULL DEFAULT nextval('comportamento_id_seq'::regclass),
  conduta character varying,
  CONSTRAINT comportamento_pkey PRIMARY KEY (id)
);
CREATE TABLE public.controle_convocacao (
  id integer NOT NULL DEFAULT nextval('controle_convocacao_id_seq'::regclass),
  classificacao character varying NOT NULL,
  inscricao character varying NOT NULL,
  nome character varying NOT NULL,
  nota_final character varying NOT NULL,
  ordem_de_convocacao character varying NOT NULL,
  apresentou boolean NOT NULL,
  situacao_convocacao_id integer,
  matricula boolean NOT NULL,
  numero_da_matricula_doe character varying NOT NULL,
  bg_matricula_doe character varying NOT NULL,
  portaria_convocacao character varying NOT NULL,
  bg_portaria_convocacao character varying NOT NULL,
  doe_portaria_convocacao character varying NOT NULL,
  notificacao_pessoal boolean NOT NULL,
  termo_desistencia boolean NOT NULL,
  siged_desistencia character varying NOT NULL,
  data_criacao timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT controle_convocacao_pkey PRIMARY KEY (id),
  CONSTRAINT controle_convocacao_situacao_convocacao_id_fkey FOREIGN KEY (situacao_convocacao_id) REFERENCES public.situacao_convocacao(id)
);
CREATE TABLE public.convocacao (
  id integer NOT NULL DEFAULT nextval('convocacao_id_seq'::regclass),
  data date NOT NULL,
  convocados integer NOT NULL,
  faltaram integer NOT NULL,
  desistiram integer NOT NULL,
  vagas_abertas integer NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  semana text,
  CONSTRAINT convocacao_pkey PRIMARY KEY (id)
);
CREATE TABLE public.declaracao_acumulo (
  id bigint NOT NULL DEFAULT nextval('declaracao_acumulo_id_seq'::regclass),
  militar_id bigint NOT NULL,
  ano_referencia integer NOT NULL CHECK (ano_referencia >= 2000 AND ano_referencia <= (EXTRACT(year FROM now())::integer + 1)),
  tipo USER-DEFINED NOT NULL,
  meio_entrega USER-DEFINED NOT NULL DEFAULT 'digital'::meio_entrega,
  data_entrega timestamp with time zone NOT NULL DEFAULT now(),
  status USER-DEFINED NOT NULL DEFAULT 'pendente'::status_declaracao,
  recebido_por_user_id bigint,
  arquivo_declaracao character varying,
  observacoes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone,
  recebido_em timestamp with time zone,
  arquivo_modelo_assinado character varying,
  arquivo_declaracao_orgao character varying,
  CONSTRAINT declaracao_acumulo_pkey PRIMARY KEY (id),
  CONSTRAINT declaracao_acumulo_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT declaracao_acumulo_recebido_por_user_id_fkey FOREIGN KEY (recebido_por_user_id) REFERENCES public.user(id)
);
CREATE TABLE public.dep_acao_log (
  id bigint NOT NULL DEFAULT nextval('dep_acao_log_id_seq'::regclass),
  processo_id bigint NOT NULL,
  acao character varying NOT NULL CHECK (acao::text = ANY (ARRAY['MILITAR_ENVIOU'::character varying::text, 'MILITAR_REENVIOU'::character varying::text, 'DRH_CONFERIU'::character varying::text, 'DRH_DEFERIU'::character varying::text, 'DRH_INDEFERIU'::character varying::text, 'DRH_OBSERVACAO'::character varying::text])),
  user_id bigint,
  ip character varying,
  criado_em timestamp with time zone NOT NULL DEFAULT now(),
  detalhes text,
  CONSTRAINT dep_acao_log_pkey PRIMARY KEY (id),
  CONSTRAINT dep_acao_log_processo_id_fkey FOREIGN KEY (processo_id) REFERENCES public.dep_processo(id),
  CONSTRAINT dep_acao_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user(id)
);
CREATE TABLE public.dep_arquivo (
  id bigint NOT NULL DEFAULT nextval('dep_arquivo_id_seq'::regclass),
  processo_id bigint NOT NULL,
  object_key text NOT NULL,
  nome_original character varying,
  content_type character varying,
  criado_em timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT dep_arquivo_pkey PRIMARY KEY (id),
  CONSTRAINT dep_arquivo_processo_id_fkey FOREIGN KEY (processo_id) REFERENCES public.dep_processo(id)
);
CREATE TABLE public.dep_processo (
  id bigint NOT NULL DEFAULT nextval('dep_processo_id_seq'::regclass),
  protocolo character varying NOT NULL UNIQUE,
  militar_id bigint NOT NULL,
  ano integer NOT NULL,
  status character varying NOT NULL DEFAULT 'ENVIADO'::character varying CHECK (status::text = ANY (ARRAY['ENVIADO'::character varying, 'EM_ANALISE'::character varying, 'DEFERIDO'::character varying, 'INDEFERIDO'::character varying]::text[])),
  enviado_em timestamp with time zone NOT NULL DEFAULT now(),
  enviado_ip character varying,
  conferido_em timestamp with time zone,
  conferido_ip character varying,
  conferido_por_id bigint,
  indeferido_motivo text,
  indeferido_em timestamp with time zone,
  indeferido_por_id bigint,
  indeferido_ip character varying,
  dependente_nome text,
  grau_parentesco text,
  idade_dependente text,
  fim_imposto_renda boolean NOT NULL DEFAULT false,
  fim_cadastro_sistema boolean NOT NULL DEFAULT false,
  criado_em timestamp with time zone NOT NULL DEFAULT now(),
  dependentes_json jsonb,
  dependentes_qtd integer,
  CONSTRAINT dep_processo_pkey PRIMARY KEY (id),
  CONSTRAINT dep_processo_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT dep_processo_conferido_por_id_fkey FOREIGN KEY (conferido_por_id) REFERENCES public.user(id),
  CONSTRAINT dep_processo_indeferido_por_fk FOREIGN KEY (indeferido_por_id) REFERENCES public.user(id)
);
CREATE TABLE public.destino (
  id integer NOT NULL DEFAULT nextval('destino_id_seq'::regclass),
  local character varying,
  CONSTRAINT destino_pkey PRIMARY KEY (id)
);
CREATE TABLE public.documento_militar (
  id bigint NOT NULL DEFAULT nextval('documento_militar_id_seq'::regclass),
  militar_id bigint NOT NULL,
  destinatario_cpf character varying NOT NULL,
  nome_original character varying NOT NULL,
  content_type character varying NOT NULL,
  tamanho_bytes integer,
  object_key character varying NOT NULL UNIQUE,
  criado_em timestamp with time zone NOT NULL DEFAULT now(),
  baixado_em timestamp with time zone,
  criado_por_user_id bigint,
  observacao text,
  CONSTRAINT documento_militar_pkey PRIMARY KEY (id),
  CONSTRAINT documento_militar_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT documento_militar_criado_por_user_id_fkey FOREIGN KEY (criado_por_user_id) REFERENCES public.user(id)
);
CREATE TABLE public.draft_declaracao_acumulo (
  id bigint NOT NULL DEFAULT nextval('draft_declaracao_acumulo_id_seq'::regclass),
  militar_id integer NOT NULL,
  ano_referencia integer NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT draft_declaracao_acumulo_pkey PRIMARY KEY (id),
  CONSTRAINT draft_declaracao_acumulo_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id)
);
CREATE TABLE public.especialidade (
  id integer NOT NULL DEFAULT nextval('especialidade_id_seq'::regclass),
  ocupacao character varying,
  CONSTRAINT especialidade_pkey PRIMARY KEY (id)
);
CREATE TABLE public.estado_civil (
  id integer NOT NULL DEFAULT nextval('estado_civil_id_seq'::regclass),
  estado character varying,
  CONSTRAINT estado_civil_pkey PRIMARY KEY (id)
);
CREATE TABLE public.ficha_alunos (
  id integer NOT NULL DEFAULT nextval('ficha_alunos_id_seq'::regclass),
  nome_completo character varying NOT NULL,
  nome_guerra character varying,
  idade_atual integer,
  cpf character varying,
  rg character varying,
  estado_civil character varying,
  nome_pai character varying,
  nome_mae character varying,
  pelotao character varying,
  email character varying,
  telefone character varying,
  telefone_emergencia character varying,
  rua character varying,
  bairro character varying,
  complemento character varying,
  caso_aluno_nao_resida_em_manaus character varying,
  estado character varying,
  formacao_academica character varying,
  tipo_sanguineo character varying,
  categoria_cnh character varying,
  classificacao_final_concurso character varying,
  comportamento character varying,
  foto character varying,
  nota_comportamento numeric DEFAULT 5.00,
  ativo boolean DEFAULT true,
  matricula character varying,
  CONSTRAINT ficha_alunos_pkey PRIMARY KEY (id)
);
CREATE TABLE public.funcao (
  id integer NOT NULL DEFAULT nextval('funcao_id_seq'::regclass),
  ocupacao character varying,
  CONSTRAINT funcao_pkey PRIMARY KEY (id)
);
CREATE TABLE public.funcao_gratificada (
  id integer NOT NULL DEFAULT nextval('funcao_gratificada_id_seq'::regclass),
  gratificacao character varying,
  CONSTRAINT funcao_gratificada_pkey PRIMARY KEY (id)
);
CREATE TABLE public.funcao_user (
  id integer NOT NULL DEFAULT nextval('funcao_user_id_seq'::regclass),
  ocupacao character varying NOT NULL,
  CONSTRAINT funcao_user_pkey PRIMARY KEY (id)
);
CREATE TABLE public.gc (
  id integer NOT NULL DEFAULT nextval('gc_id_seq'::regclass),
  descricao character varying NOT NULL,
  CONSTRAINT gc_pkey PRIMARY KEY (id)
);
CREATE TABLE public.licenca_especial (
  id integer NOT NULL DEFAULT nextval('licenca_especial_id_seq'::regclass),
  militar_id integer,
  posto_grad_id integer,
  quadro_id integer,
  destino_id integer,
  situacao_id integer,
  inicio_periodo_le date,
  fim_periodo_le date,
  status character varying,
  publicacao_bg_id integer,
  email_30_dias_enviado_le boolean,
  email_15_dias_enviado_le boolean,
  CONSTRAINT licenca_especial_pkey PRIMARY KEY (id),
  CONSTRAINT licenca_especial_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT licenca_especial_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id),
  CONSTRAINT licenca_especial_quadro_id_fkey FOREIGN KEY (quadro_id) REFERENCES public.quadro(id),
  CONSTRAINT licenca_especial_destino_id_fkey FOREIGN KEY (destino_id) REFERENCES public.destino(id),
  CONSTRAINT licenca_especial_situacao_id_fkey FOREIGN KEY (situacao_id) REFERENCES public.situacao(id),
  CONSTRAINT licenca_especial_publicacao_bg_id_fkey FOREIGN KEY (publicacao_bg_id) REFERENCES public.publicacaobg(id)
);
CREATE TABLE public.licenca_para_tratamento_de_saude (
  id integer NOT NULL DEFAULT nextval('licenca_para_tratamento_de_saude_id_seq'::regclass),
  militar_id integer,
  posto_grad_id integer,
  quadro_id integer,
  destino_id integer,
  situacao_id integer,
  inicio_periodo_lts date,
  fim_periodo_lts date,
  status character varying,
  publicacao_bg_id integer,
  email_30_dias_enviado_lts boolean,
  email_15_dias_enviado_lts boolean,
  CONSTRAINT licenca_para_tratamento_de_saude_pkey PRIMARY KEY (id),
  CONSTRAINT licenca_para_tratamento_de_saude_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT licenca_para_tratamento_de_saude_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id),
  CONSTRAINT licenca_para_tratamento_de_saude_quadro_id_fkey FOREIGN KEY (quadro_id) REFERENCES public.quadro(id),
  CONSTRAINT licenca_para_tratamento_de_saude_destino_id_fkey FOREIGN KEY (destino_id) REFERENCES public.destino(id),
  CONSTRAINT licenca_para_tratamento_de_saude_situacao_id_fkey FOREIGN KEY (situacao_id) REFERENCES public.situacao(id),
  CONSTRAINT licenca_para_tratamento_de_saude_publicacao_bg_id_fkey FOREIGN KEY (publicacao_bg_id) REFERENCES public.publicacaobg(id)
);
CREATE TABLE public.localidade (
  id integer NOT NULL DEFAULT nextval('localidade_id_seq'::regclass),
  sigla character varying,
  CONSTRAINT localidade_pkey PRIMARY KEY (id)
);
CREATE TABLE public.lts_alunos (
  id integer NOT NULL DEFAULT nextval('lts_alunos_id_seq'::regclass),
  ficha_aluno_id integer NOT NULL,
  boletim_interno character varying NOT NULL,
  data_inicio date NOT NULL,
  data_fim date NOT NULL,
  usuario_id integer,
  data_criacao timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Manaus'::text),
  CONSTRAINT lts_alunos_pkey PRIMARY KEY (id),
  CONSTRAINT lts_alunos_ficha_aluno_id_fkey FOREIGN KEY (ficha_aluno_id) REFERENCES public.ficha_alunos(id),
  CONSTRAINT lts_alunos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.meses (
  id integer NOT NULL DEFAULT nextval('meses_id_seq'::regclass),
  mes character varying,
  CONSTRAINT meses_pkey PRIMARY KEY (id)
);
CREATE TABLE public.militar (
  id integer NOT NULL DEFAULT nextval('militar_id_seq'::regclass) UNIQUE,
  nome_completo character varying,
  nome_guerra character varying,
  cpf character varying,
  rg character varying,
  nome_pai character varying,
  nome_mae character varying,
  matricula character varying,
  pis_pasep character varying,
  num_titulo_eleitor character varying,
  digito_titulo_eleitor character varying,
  zona character varying,
  secao character varying,
  posto_grad_id integer,
  quadro_id integer,
  localidade_id integer,
  antiguidade character varying,
  sexo character varying,
  raca character varying,
  data_nascimento date,
  inclusao date,
  completa_25_inclusao date,
  completa_30_inclusao date,
  punicao_id integer,
  comportamento_id integer,
  efetivo_servico date,
  completa_25_anos_sv date,
  completa_30_anos_sv date,
  anos integer,
  meses integer,
  dias integer,
  total_dias integer,
  idade_reserva_grad integer,
  estado_civil integer,
  especialidade_id integer,
  pronto character varying,
  situacao_id integer,
  agregacoes_id integer,
  destino_id integer,
  inicio_periodo date,
  fim_periodo date,
  ltip_afastamento_cargo_eletivo character varying,
  periodo_ltip character varying,
  total_ltip character varying,
  completa_25_anos_ltip character varying,
  completa_30_anos_ltip character varying,
  cursos character varying,
  grau_instrucao character varying,
  graduacao character varying,
  pos_graduacao character varying,
  mestrado character varying,
  doutorado character varying,
  cfsd character varying,
  cfc character varying,
  cfs character varying,
  cas character varying,
  choa character varying,
  cfo character varying,
  cbo character varying,
  cao character varying,
  csbm character varying,
  cursos_civis character varying,
  endereco character varying,
  complemento character varying,
  cidade character varying,
  estado character varying,
  cep character varying,
  celular character varying,
  email character varying,
  inclusao_bg character varying,
  soldado_tres character varying,
  soldado_dois character varying,
  soldado_um character varying,
  cabo character varying,
  terceiro_sgt character varying,
  segundo_sgt character varying,
  primeiro_sgt character varying,
  subtenente character varying,
  segundo_tenente character varying,
  primeiro_tenente character varying,
  cap character varying,
  maj character varying,
  tc character varying,
  cel character varying,
  alteracao_nome_guerra character varying,
  usuario_id integer,
  data_criacao timestamp without time zone,
  ip_address character varying,
  funcao_gratificada_id integer,
  gc_id integer,
  inativo boolean DEFAULT false,
  situacao2_id integer,
  agregacoes2_id integer,
  inicio_situacao2 date,
  fim_situacao2 date,
  inativado_em timestamp without time zone,
  inativado_por_id integer,
  motivo_inativacao character varying,
  CONSTRAINT militar_pkey PRIMARY KEY (id),
  CONSTRAINT militar_gc_id_fkey FOREIGN KEY (gc_id) REFERENCES public.gc(id),
  CONSTRAINT militar_situacao2_id_fkey FOREIGN KEY (situacao2_id) REFERENCES public.situacao(id),
  CONSTRAINT militar_agregacoes2_id_fkey FOREIGN KEY (agregacoes2_id) REFERENCES public.agregacoes(id),
  CONSTRAINT militar_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id),
  CONSTRAINT militar_quadro_id_fkey FOREIGN KEY (quadro_id) REFERENCES public.quadro(id),
  CONSTRAINT militar_localidade_id_fkey FOREIGN KEY (localidade_id) REFERENCES public.localidade(id),
  CONSTRAINT militar_punicao_id_fkey FOREIGN KEY (punicao_id) REFERENCES public.punicao(id),
  CONSTRAINT militar_comportamento_id_fkey FOREIGN KEY (comportamento_id) REFERENCES public.comportamento(id),
  CONSTRAINT militar_estado_civil_fkey FOREIGN KEY (estado_civil) REFERENCES public.estado_civil(id),
  CONSTRAINT militar_especialidade_id_fkey FOREIGN KEY (especialidade_id) REFERENCES public.especialidade(id),
  CONSTRAINT militar_situacao_id_fkey FOREIGN KEY (situacao_id) REFERENCES public.situacao(id),
  CONSTRAINT militar_agregacoes_id_fkey FOREIGN KEY (agregacoes_id) REFERENCES public.agregacoes(id),
  CONSTRAINT militar_destino_id_fkey FOREIGN KEY (destino_id) REFERENCES public.destino(id),
  CONSTRAINT militar_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id),
  CONSTRAINT militar_funcao_gratificada_id_fkey FOREIGN KEY (funcao_gratificada_id) REFERENCES public.funcao_gratificada(id)
);
CREATE TABLE public.militar_obm_funcao (
  id integer NOT NULL DEFAULT nextval('militar_obm_funcao_id_seq'::regclass),
  militar_id integer,
  obm_id integer,
  funcao_id integer,
  tipo integer,
  data_criacao timestamp without time zone,
  data_fim timestamp without time zone,
  CONSTRAINT militar_obm_funcao_pkey PRIMARY KEY (id),
  CONSTRAINT militar_obm_funcao_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT militar_obm_funcao_obm_id_fkey FOREIGN KEY (obm_id) REFERENCES public.obm(id),
  CONSTRAINT militar_obm_funcao_funcao_id_fkey FOREIGN KEY (funcao_id) REFERENCES public.funcao(id)
);
CREATE TABLE public.militares_a_disposicao (
  id integer NOT NULL DEFAULT nextval('militares_a_disposicao_id_seq'::regclass),
  militar_id integer,
  posto_grad_id integer,
  quadro_id integer,
  destino_id integer,
  situacao_id integer,
  inicio_periodo date,
  fim_periodo_disposicao date,
  status character varying,
  publicacao_bg_id integer,
  email_30_dias_enviado_disposicao boolean,
  email_15_dias_enviado_disposicao boolean,
  CONSTRAINT militares_a_disposicao_pkey PRIMARY KEY (id),
  CONSTRAINT militares_a_disposicao_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT militares_a_disposicao_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id),
  CONSTRAINT militares_a_disposicao_quadro_id_fkey FOREIGN KEY (quadro_id) REFERENCES public.quadro(id),
  CONSTRAINT militares_a_disposicao_destino_id_fkey FOREIGN KEY (destino_id) REFERENCES public.destino(id),
  CONSTRAINT militares_a_disposicao_situacao_id_fkey FOREIGN KEY (situacao_id) REFERENCES public.situacao(id),
  CONSTRAINT militares_a_disposicao_publicacao_bg_id_fkey FOREIGN KEY (publicacao_bg_id) REFERENCES public.publicacaobg(id)
);
CREATE TABLE public.militares_agregados (
  id integer NOT NULL DEFAULT nextval('militares_agregados_id_seq'::regclass),
  militar_id integer,
  posto_grad_id integer,
  quadro_id integer,
  destino_id integer,
  situacao_id integer,
  inicio_periodo date,
  fim_periodo_agregacao date,
  status character varying,
  publicacao_bg_id integer,
  email_30_dias_enviado boolean,
  email_15_dias_enviado boolean,
  CONSTRAINT militares_agregados_pkey PRIMARY KEY (id),
  CONSTRAINT militares_agregados_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT militares_agregados_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id),
  CONSTRAINT militares_agregados_quadro_id_fkey FOREIGN KEY (quadro_id) REFERENCES public.quadro(id),
  CONSTRAINT militares_agregados_destino_id_fkey FOREIGN KEY (destino_id) REFERENCES public.destino(id),
  CONSTRAINT militares_agregados_situacao_id_fkey FOREIGN KEY (situacao_id) REFERENCES public.situacao(id),
  CONSTRAINT militares_agregados_publicacao_bg_id_fkey FOREIGN KEY (publicacao_bg_id) REFERENCES public.publicacaobg(id)
);
CREATE TABLE public.militares_inativos (
  id integer NOT NULL DEFAULT nextval('militares_inativos_id_seq'::regclass),
  nome_completo character varying NOT NULL,
  nome_guerra character varying,
  estado_civil_id integer,
  nome_pai character varying,
  nome_mae character varying,
  matricula character varying,
  rg character varying,
  cpf character varying,
  pis_pasep character varying,
  posto_grad_id integer,
  quadro_id integer,
  sexo character varying,
  data_nascimento date,
  idade_atual integer,
  endereco character varying,
  complemento character varying,
  cidade character varying,
  estado character varying,
  cep character varying,
  celular character varying,
  email character varying,
  usuario_id integer,
  data_criacao timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  ip_address character varying,
  modalidade character varying,
  doe character varying,
  CONSTRAINT militares_inativos_pkey PRIMARY KEY (id),
  CONSTRAINT militares_inativos_estado_civil_id_fkey FOREIGN KEY (estado_civil_id) REFERENCES public.estado_civil(id),
  CONSTRAINT militares_inativos_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id),
  CONSTRAINT militares_inativos_quadro_id_fkey FOREIGN KEY (quadro_id) REFERENCES public.quadro(id),
  CONSTRAINT militares_inativos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.motoristas (
  id integer NOT NULL DEFAULT nextval('motoristas_id_seq'::regclass),
  militar_id integer NOT NULL,
  categoria_id integer,
  siged character varying,
  boletim_geral character varying,
  created timestamp with time zone DEFAULT now(),
  modified timestamp with time zone DEFAULT now(),
  usuario_id integer,
  desclassificar character varying,
  vencimento_cnh timestamp with time zone,
  cnh_imagem character varying,
  desclassificar_por integer,
  desclassificar_em timestamp without time zone,
  desclassificar_motivo text,
  CONSTRAINT motoristas_pkey PRIMARY KEY (id),
  CONSTRAINT motoristas_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT motoristas_categoria_id_fkey FOREIGN KEY (categoria_id) REFERENCES public.categoria(id),
  CONSTRAINT motoristas_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id),
  CONSTRAINT motoristas_desclassificar_por_fkey FOREIGN KEY (desclassificar_por) REFERENCES public.user(id)
);
CREATE TABLE public.nome_convocado (
  id integer NOT NULL DEFAULT nextval('nome_convocado_id_seq'::regclass),
  nome character varying NOT NULL,
  inscricao character varying,
  classificacao character varying,
  nota_final character varying,
  CONSTRAINT nome_convocado_pkey PRIMARY KEY (id)
);
CREATE TABLE public.novo_paf (
  id integer NOT NULL DEFAULT nextval('novo_paf_id_seq'::regclass),
  militar_id integer NOT NULL,
  ano_referencia integer NOT NULL,
  opcao_1 smallint NOT NULL,
  opcao_2 smallint NOT NULL,
  opcao_3 smallint NOT NULL,
  status character varying NOT NULL DEFAULT 'enviado'::character varying,
  justificativa text,
  mes_definido smallint,
  recebido_por_user_id integer,
  recebido_em timestamp with time zone,
  aprovado_por_user_id integer,
  aprovado_em timestamp with time zone,
  validado_por_user_id integer,
  validado_em timestamp with time zone,
  observacoes text,
  data_entrega timestamp with time zone NOT NULL DEFAULT now(),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT novo_paf_pkey PRIMARY KEY (id),
  CONSTRAINT novo_paf_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT novo_paf_recebido_por_user_id_fkey FOREIGN KEY (recebido_por_user_id) REFERENCES public.user(id),
  CONSTRAINT novo_paf_aprovado_por_user_id_fkey FOREIGN KEY (aprovado_por_user_id) REFERENCES public.user(id),
  CONSTRAINT novo_paf_validado_por_user_id_fkey FOREIGN KEY (validado_por_user_id) REFERENCES public.user(id)
);
CREATE TABLE public.numero_emergencia (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  militar_id bigint,
  numero_emergencia character varying,
  responsavel character varying,
  criado_em timestamp with time zone DEFAULT now(),
  CONSTRAINT numero_emergencia_pkey PRIMARY KEY (id),
  CONSTRAINT numero_emergencia_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id)
);
CREATE TABLE public.obm (
  id integer NOT NULL DEFAULT nextval('obm_id_seq'::regclass),
  sigla character varying,
  CONSTRAINT obm_pkey PRIMARY KEY (id)
);
CREATE TABLE public.obm_gestao (
  id integer NOT NULL DEFAULT nextval('obm_gestao_id_seq'::regclass),
  obm_gestora_id integer NOT NULL,
  obm_gerida_id integer NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  CONSTRAINT obm_gestao_pkey PRIMARY KEY (id),
  CONSTRAINT obm_gestao_obm_gestora_id_fkey FOREIGN KEY (obm_gestora_id) REFERENCES public.obm(id),
  CONSTRAINT obm_gestao_obm_gerida_id_fkey FOREIGN KEY (obm_gerida_id) REFERENCES public.obm(id)
);
CREATE TABLE public.paf (
  id integer NOT NULL DEFAULT nextval('paf_id_seq'::regclass),
  militar_id integer NOT NULL,
  qtd_dias_primeiro_periodo integer,
  primeiro_periodo_ferias date,
  fim_primeiro_periodo date,
  qtd_dias_segundo_periodo integer,
  segundo_periodo_ferias date,
  fim_segundo_periodo date,
  qtd_dias_terceiro_periodo integer,
  terceiro_periodo_ferias date,
  fim_terceiro_periodo date,
  usuario_id integer,
  mes_usufruto character varying,
  data_alteracao timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  ano_referencia integer NOT NULL,
  CONSTRAINT paf_pkey PRIMARY KEY (id),
  CONSTRAINT paf_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT paf_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.paf_capacidade (
  id bigint NOT NULL DEFAULT nextval('paf_capacidade_id_seq'::regclass),
  ano integer NOT NULL,
  mes smallint NOT NULL CHECK (mes >= 1 AND mes <= 12),
  limite integer NOT NULL CHECK (limite >= 0),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT paf_capacidade_pkey PRIMARY KEY (id)
);
CREATE TABLE public.paf_ferias_plano (
  id bigint NOT NULL DEFAULT nextval('paf_ferias_plano_id_seq'::regclass),
  militar_id bigint NOT NULL,
  usuario_id bigint NOT NULL,
  ano_referencia integer NOT NULL,
  direito_total_dias integer NOT NULL CHECK (direito_total_dias = ANY (ARRAY[30, 40])),
  qtd_dias_p1 integer NOT NULL CHECK (qtd_dias_p1 = ANY (ARRAY[10, 15, 20, 30])),
  inicio_p1 date NOT NULL,
  fim_p1 date NOT NULL,
  mes_usufruto_p1 smallint NOT NULL CHECK (mes_usufruto_p1 >= 1 AND mes_usufruto_p1 <= 12),
  qtd_dias_p2 integer CHECK (qtd_dias_p2 = ANY (ARRAY[10, 15, 20])),
  inicio_p2 date,
  fim_p2 date,
  mes_usufruto_p2 smallint CHECK (mes_usufruto_p2 >= 1 AND mes_usufruto_p2 <= 12),
  qtd_dias_p3 integer CHECK (qtd_dias_p3 = ANY (ARRAY[10, 15])),
  inicio_p3 date,
  fim_p3 date,
  mes_usufruto_p3 smallint CHECK (mes_usufruto_p3 >= 1 AND mes_usufruto_p3 <= 12),
  status text DEFAULT 'enviado'::text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT paf_ferias_plano_pkey PRIMARY KEY (id),
  CONSTRAINT paf_ferias_plano_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT paf_ferias_plano_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.posto_grad (
  id integer NOT NULL DEFAULT nextval('posto_grad_id_seq'::regclass),
  sigla character varying,
  CONSTRAINT posto_grad_pkey PRIMARY KEY (id)
);
CREATE TABLE public.publicacaobg (
  id integer NOT NULL DEFAULT nextval('publicacaobg_id_seq'::regclass),
  boletim_geral character varying,
  tipo_bg character varying,
  militar_id integer,
  CONSTRAINT publicacaobg_pkey PRIMARY KEY (id),
  CONSTRAINT publicacaobg_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id)
);
CREATE TABLE public.punicao (
  id integer NOT NULL DEFAULT nextval('punicao_id_seq'::regclass),
  sancao character varying,
  CONSTRAINT punicao_pkey PRIMARY KEY (id)
);
CREATE TABLE public.quadro (
  id integer NOT NULL DEFAULT nextval('quadro_id_seq'::regclass),
  quadro character varying,
  descricao character varying,
  CONSTRAINT quadro_pkey PRIMARY KEY (id)
);
CREATE TABLE public.recompensas_alunos (
  id integer NOT NULL DEFAULT nextval('recompensas_alunos_id_seq'::regclass),
  ficha_aluno_id integer NOT NULL,
  natureza character varying NOT NULL,
  autoridade character varying NOT NULL,
  boletim character varying NOT NULL,
  discriminacao text NOT NULL,
  usuario_id integer,
  data_criacao timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Manaus'::text),
  CONSTRAINT recompensas_alunos_pkey PRIMARY KEY (id),
  CONSTRAINT recompensas_alunos_ficha_aluno_id_fkey FOREIGN KEY (ficha_aluno_id) REFERENCES public.ficha_alunos(id),
  CONSTRAINT recompensas_alunos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.restricoes_alunos (
  id integer NOT NULL DEFAULT nextval('restricoes_alunos_id_seq'::regclass),
  ficha_aluno_id integer NOT NULL,
  descricao text NOT NULL,
  data_inicio date NOT NULL,
  data_fim date NOT NULL,
  usuario_id integer,
  data_criacao timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Manaus'::text),
  CONSTRAINT restricoes_alunos_pkey PRIMARY KEY (id),
  CONSTRAINT restricoes_alunos_ficha_aluno_id_fkey FOREIGN KEY (ficha_aluno_id) REFERENCES public.ficha_alunos(id),
  CONSTRAINT restricoes_alunos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.sancoes_alunos (
  id integer NOT NULL DEFAULT nextval('sancoes_alunos_id_seq'::regclass),
  ficha_aluno_id integer NOT NULL,
  natureza character varying NOT NULL,
  numero_dias integer NOT NULL,
  boletim character varying NOT NULL,
  data_inicio date NOT NULL,
  data_fim date NOT NULL,
  discriminacao text NOT NULL,
  usuario_id integer,
  data_criacao timestamp without time zone DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Manaus'::text),
  CONSTRAINT sancoes_alunos_pkey PRIMARY KEY (id),
  CONSTRAINT sancoes_alunos_ficha_aluno_id_fkey FOREIGN KEY (ficha_aluno_id) REFERENCES public.ficha_alunos(id),
  CONSTRAINT sancoes_alunos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.user(id)
);
CREATE TABLE public.segundo_vinculo (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  militar_id bigint,
  possui_vinculo boolean,
  quantidade_vinculos integer,
  descricao_vinculo text,
  horario_inicio time without time zone,
  horario_fim time without time zone,
  data_registro timestamp with time zone DEFAULT now(),
  CONSTRAINT segundo_vinculo_pkey PRIMARY KEY (id),
  CONSTRAINT segundo_vinculo_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id)
);
CREATE TABLE public.situacao (
  id integer NOT NULL DEFAULT nextval('situacao_id_seq'::regclass),
  condicao character varying,
  CONSTRAINT situacao_pkey PRIMARY KEY (id)
);
CREATE TABLE public.situacao_convocacao (
  id integer NOT NULL DEFAULT nextval('situacao_convocacao_id_seq'::regclass),
  situacao character varying NOT NULL,
  CONSTRAINT situacao_convocacao_pkey PRIMARY KEY (id)
);
CREATE TABLE public.tabela_vencimento (
  id integer NOT NULL DEFAULT nextval('tabela_vencimento_id_seq'::regclass),
  nome character varying,
  lei character varying,
  data_inicio date NOT NULL,
  data_fim date NOT NULL,
  CONSTRAINT tabela_vencimento_pkey PRIMARY KEY (id)
);
CREATE TABLE public.tarefa_atualizacao_cadete (
  id integer NOT NULL DEFAULT nextval('tarefa_atualizacao_cadete_id_seq'::regclass),
  cadete_user_id integer NOT NULL,
  cadete_militar_id integer NOT NULL,
  militar_id integer NOT NULL,
  status character varying DEFAULT 'PENDENTE'::character varying,
  atualizado_em timestamp without time zone,
  criado_em timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  locked_by_user_id integer,
  locked_at timestamp without time zone,
  CONSTRAINT tarefa_atualizacao_cadete_pkey PRIMARY KEY (id),
  CONSTRAINT fk_cadete_user FOREIGN KEY (cadete_user_id) REFERENCES public.user(id),
  CONSTRAINT fk_cadete_militar FOREIGN KEY (cadete_militar_id) REFERENCES public.militar(id),
  CONSTRAINT fk_militar FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT fk_locked_user FOREIGN KEY (locked_by_user_id) REFERENCES public.user(id)
);
CREATE TABLE public.token_verificacao (
  id integer NOT NULL DEFAULT nextval('token_verificacao_id_seq'::regclass),
  cpf character varying NOT NULL,
  token character varying NOT NULL,
  criado_em timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  usado boolean DEFAULT false,
  CONSTRAINT token_verificacao_pkey PRIMARY KEY (id)
);
CREATE TABLE public.user (
  id integer NOT NULL DEFAULT nextval('user_id_seq'::regclass),
  nome character varying,
  email character varying,
  cpf character varying UNIQUE,
  senha character varying,
  funcao_user_id integer,
  obm_id_1 integer,
  obm_id_2 integer,
  localidade_id integer,
  ip_address character varying,
  data_criacao timestamp without time zone,
  data_ultimo_acesso timestamp without time zone,
  endereco_acesso character varying,
  user_domain_role USER-DEFINED NOT NULL DEFAULT 'comum'::user_domain_role,
  cpf_norm character varying,
  militar_id integer,
  tipo_perfil character varying,
  CONSTRAINT user_pkey PRIMARY KEY (id),
  CONSTRAINT fk_user_militar_id FOREIGN KEY (militar_id) REFERENCES public.militar(id),
  CONSTRAINT user_funcao_user_id_fkey FOREIGN KEY (funcao_user_id) REFERENCES public.funcao_user(id),
  CONSTRAINT user_obm_id_1_fkey FOREIGN KEY (obm_id_1) REFERENCES public.obm(id),
  CONSTRAINT user_obm_id_2_fkey FOREIGN KEY (obm_id_2) REFERENCES public.obm(id),
  CONSTRAINT user_localidade_id_fkey FOREIGN KEY (localidade_id) REFERENCES public.localidade(id)
);
CREATE TABLE public.user_obm_acesso (
  id bigint NOT NULL DEFAULT nextval('user_obm_acesso_id_seq'::regclass),
  user_id bigint NOT NULL,
  obm_id bigint NOT NULL,
  tipo character varying NOT NULL DEFAULT 'DELEGADO'::character varying,
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamp without time zone NOT NULL DEFAULT timezone('America/Manaus'::text, now()),
  CONSTRAINT user_obm_acesso_pkey PRIMARY KEY (id),
  CONSTRAINT user_obm_acesso_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user(id),
  CONSTRAINT user_obm_acesso_obm_id_fkey FOREIGN KEY (obm_id) REFERENCES public.obm(id)
);
CREATE TABLE public.user_permissao (
  id integer NOT NULL DEFAULT nextval('user_permissao_id_seq'::regclass),
  user_id integer NOT NULL,
  codigo character varying NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT user_permissao_pkey PRIMARY KEY (id),
  CONSTRAINT user_permissao_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user(id)
);
CREATE TABLE public.valor_detalhado_posto_grad (
  id integer NOT NULL DEFAULT nextval('valor_detalhado_posto_grad_id_seq'::regclass),
  tabela_id integer,
  posto_grad_id integer,
  soldo numeric,
  grat_tropa numeric,
  gams numeric,
  valor_bruto numeric,
  curso_25 numeric,
  curso_30 numeric,
  curso_35 numeric,
  bruto_esp numeric,
  bruto_mestre numeric,
  bruto_dout numeric,
  fg_1 numeric,
  fg_2 numeric,
  fg_3 numeric,
  fg_4 numeric,
  aux_moradia numeric,
  etapas_capital character varying,
  etapas_interior character varying,
  seg_hora numeric,
  motorista_a numeric,
  motorista_b numeric,
  motorista_ab numeric,
  motorista_cde numeric,
  tecnico_raiox numeric,
  tecnico_lab numeric,
  mecanico numeric,
  fluvial numeric,
  explosivista numeric,
  coe numeric,
  tripulante numeric,
  piloto numeric,
  aviacao numeric,
  mergulhador numeric,
  CONSTRAINT valor_detalhado_posto_grad_pkey PRIMARY KEY (id),
  CONSTRAINT valor_detalhado_posto_grad_tabela_id_fkey FOREIGN KEY (tabela_id) REFERENCES public.tabela_vencimento(id),
  CONSTRAINT valor_detalhado_posto_grad_posto_grad_id_fkey FOREIGN KEY (posto_grad_id) REFERENCES public.posto_grad(id)
);
CREATE TABLE public.viatura_militar (
  id bigint NOT NULL DEFAULT nextval('viatura_militar_id_seq'::regclass),
  viatura_id bigint NOT NULL,
  militar_id bigint NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT viatura_militar_pkey PRIMARY KEY (id),
  CONSTRAINT viatura_militar_viatura_id_fkey FOREIGN KEY (viatura_id) REFERENCES public.viaturas(id),
  CONSTRAINT viatura_militar_militar_id_fkey FOREIGN KEY (militar_id) REFERENCES public.militar(id)
);
CREATE TABLE public.viaturas (
  id bigint NOT NULL DEFAULT nextval('viaturas_id_seq'::regclass),
  marca_modelo text,
  placa text,
  prefixo text,
  obm_id bigint,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT viaturas_pkey PRIMARY KEY (id),
  CONSTRAINT viaturas_obm_id_fkey FOREIGN KEY (obm_id) REFERENCES public.obm(id),
  CONSTRAINT viaturas_obm_fk FOREIGN KEY (obm_id) REFERENCES public.obm(id)
);
CREATE TABLE public.vinculo_externo (
  id bigint NOT NULL DEFAULT nextval('vinculo_externo_id_seq'::regclass),
  declaracao_id bigint NOT NULL,
  empregador_nome character varying NOT NULL,
  empregador_doc character varying NOT NULL CHECK (empregador_doc::text ~ '^[0-9]{11}$'::text OR empregador_doc::text ~ '^[0-9]{14}$'::text),
  natureza_vinculo USER-DEFINED NOT NULL DEFAULT 'efetivo'::natureza_vinculo_efetivo,
  cargo_funcao character varying NOT NULL,
  carga_horaria_semanal integer NOT NULL,
  horario_inicio time without time zone NOT NULL,
  horario_fim time without time zone NOT NULL,
  data_inicio date NOT NULL,
  compatibilidade_horaria boolean,
  conflito_descricao text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone,
  jornada_trabalho USER-DEFINED,
  empregador_tipo USER-DEFINED NOT NULL,
  licenca USER-DEFINED,
  CONSTRAINT vinculo_externo_pkey PRIMARY KEY (id),
  CONSTRAINT vinculo_externo_declaracao_id_fkey FOREIGN KEY (declaracao_id) REFERENCES public.declaracao_acumulo(id)
);