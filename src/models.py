import pytz
from sqlalchemy.orm import backref, foreign

from src import database, login_manager
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy.event import listens_for


class PostoGrad(database.Model):
    __tablename__ = "posto_grad"
    id = database.Column(database.Integer, primary_key=True)
    sigla = database.Column(database.String(40))
    usuario = database.relationship(
        'Militar', backref='posto_grad_militar', lazy=True)


class Quadro(database.Model):
    __tablename__ = "quadro"
    id = database.Column(database.Integer, primary_key=True)
    quadro = database.Column(database.String(40))
    descricao = database.Column(database.String(50))
    usuario = database.relationship(
        'Militar', backref='quadro_militar', lazy=True)


class Obm(database.Model):
    __tablename__ = "obm"
    id = database.Column(database.Integer, primary_key=True)
    sigla = database.Column(database.String(50))
    militares_obms = database.relationship(
        'MilitarObmFuncao', back_populates='obm', lazy=True)


class Funcao(database.Model):
    __tablename__ = "funcao"
    id = database.Column(database.Integer, primary_key=True)
    ocupacao = database.Column(database.String(80))
    militares_funcoes = database.relationship(
        'MilitarObmFuncao', back_populates='funcao', lazy=True)


class Localidade(database.Model):
    __tablename__ = "localidade"
    id = database.Column(database.Integer, primary_key=True)
    sigla = database.Column(database.String(50))
    militar = database.relationship(
        'Militar', backref='localidade_militares', lazy=True)


class EstadoCivil(database.Model):
    __tablename__ = "estado_civil"
    id = database.Column(database.Integer, primary_key=True)
    estado = database.Column(database.String(50))
    militar = database.relationship(
        'Militar', backref='estado_civil_militares', lazy=True)


class Especialidade(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    ocupacao = database.Column(database.String(50))
    militar = database.relationship(
        'Militar', backref='especialidade_militar', lazy=True)


class Destino(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    local = database.Column(database.String(50))
    militar = database.relationship(
        'Militar', backref='destino_militar', lazy=True)


class Situacao(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    condicao = database.Column(database.String(50))
    militar = database.relationship(
        'Militar', backref='situacao_militar', lazy=True)


class Agregacoes(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    tipo = database.Column(database.String(50))
    militar = database.relationship(
        'Militar', backref='agregacoes_militar', lazy=True)


class PublicacaoBg(database.Model):
    __tablename__ = "publicacaobg"
    id = database.Column(database.Integer, primary_key=True)
    boletim_geral = database.Column(database.String(100))
    # Tipo de BG, como transferência, promoção, etc.
    tipo_bg = database.Column(database.String(50))
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    militar = database.relationship(
        'Militar', backref='bg_publicacao', overlaps="militar_publicacoes_bg")


class MilitaresADisposicao(database.Model):
    __tablename__ = "militares_a_disposicao"
    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))
    quadro_id = database.Column(
        database.Integer, database.ForeignKey('quadro.id'))
    destino_id = database.Column(
        database.Integer, database.ForeignKey('destino.id'))
    situacao_id = database.Column(
        database.Integer, database.ForeignKey('situacao.id'))
    inicio_periodo = database.Column(database.Date)
    fim_periodo_disposicao = database.Column(database.Date)
    status = database.Column(database.String(50))
    publicacao_bg_id = database.Column(
        database.Integer, database.ForeignKey('publicacaobg.id'))

    email_30_dias_enviado_disposicao = database.Column(
        database.Boolean, default=False)
    email_15_dias_enviado_disposicao = database.Column(
        database.Boolean, default=False)

    militar = database.relationship('Militar', backref='militar_disposicao')
    posto_grad = database.relationship('PostoGrad')
    quadro = database.relationship('Quadro')
    destino = database.relationship('Destino')
    situacao = database.relationship('Situacao')
    publicacao_bg = database.relationship(
        'PublicacaoBg', overlaps="militar,bg_publicacao")

    def atualizar_status(self):
        today = datetime.today().date()
        if self.inicio_periodo and self.fim_periodo_disposicao:
            if self.inicio_periodo <= today <= self.fim_periodo_disposicao:
                self.status = 'Vigente'
            else:
                self.status = 'Término da Diposição'


class MilitaresAgregados(database.Model):
    __tablename__ = "militares_agregados"
    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))
    quadro_id = database.Column(
        database.Integer, database.ForeignKey('quadro.id'))
    destino_id = database.Column(
        database.Integer, database.ForeignKey('destino.id'))
    situacao_id = database.Column(
        database.Integer, database.ForeignKey('situacao.id'))
    inicio_periodo = database.Column(database.Date)
    fim_periodo_agregacao = database.Column(database.Date)
    status = database.Column(database.String(50))
    publicacao_bg_id = database.Column(
        database.Integer, database.ForeignKey('publicacaobg.id'))

    email_30_dias_enviado = database.Column(database.Boolean, default=False)
    email_15_dias_enviado = database.Column(database.Boolean, default=False)

    militar = database.relationship('Militar', backref='militar_agregado')
    posto_grad = database.relationship('PostoGrad')
    quadro = database.relationship('Quadro')
    destino = database.relationship('Destino')
    situacao = database.relationship('Situacao')
    publicacao_bg = database.relationship('PublicacaoBg')

    def atualizar_status(self):
        today = datetime.today().date()
        if self.inicio_periodo and self.fim_periodo_agregacao:
            if self.inicio_periodo <= today <= self.fim_periodo_agregacao:
                self.status = 'Vigente'
            else:
                self.status = 'Término de Agregação'


class LicencaEspecial(database.Model):
    __tablename__ = "licenca_especial"
    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))
    quadro_id = database.Column(
        database.Integer, database.ForeignKey('quadro.id'))
    destino_id = database.Column(
        database.Integer, database.ForeignKey('destino.id'))
    situacao_id = database.Column(
        database.Integer, database.ForeignKey('situacao.id'))
    inicio_periodo_le = database.Column(database.Date)
    fim_periodo_le = database.Column(database.Date)
    status = database.Column(database.String(50))
    publicacao_bg_id = database.Column(
        database.Integer, database.ForeignKey('publicacaobg.id'))

    email_30_dias_enviado_le = database.Column(database.Boolean, default=False)
    email_15_dias_enviado_le = database.Column(database.Boolean, default=False)

    militar = database.relationship('Militar', backref='militar_le')
    posto_grad = database.relationship('PostoGrad')
    quadro = database.relationship('Quadro')
    destino = database.relationship('Destino')
    situacao = database.relationship('Situacao')
    publicacao_bg = database.relationship('PublicacaoBg')

    def atualizar_status(self):
        today = datetime.today().date()
        if self.inicio_periodo_le and self.fim_periodo_le:
            if self.inicio_periodo_le <= today <= self.fim_periodo_le:
                self.status = 'Vigente'
            else:
                self.status = 'Término da Licença Especial'


class LicencaParaTratamentoDeSaude(database.Model):
    __tablename__ = "licenca_para_tratamento_de_saude"
    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))
    quadro_id = database.Column(
        database.Integer, database.ForeignKey('quadro.id'))
    destino_id = database.Column(
        database.Integer, database.ForeignKey('destino.id'))
    situacao_id = database.Column(
        database.Integer, database.ForeignKey('situacao.id'))
    inicio_periodo_lts = database.Column(database.Date)
    fim_periodo_lts = database.Column(database.Date)
    status = database.Column(database.String(50))
    publicacao_bg_id = database.Column(
        database.Integer, database.ForeignKey('publicacaobg.id'))

    email_30_dias_enviado_lts = database.Column(
        database.Boolean, default=False)
    email_15_dias_enviado_lts = database.Column(
        database.Boolean, default=False)

    militar = database.relationship('Militar', backref='militar_lts')
    posto_grad = database.relationship('PostoGrad')
    quadro = database.relationship('Quadro')
    destino = database.relationship('Destino')
    situacao = database.relationship('Situacao')
    publicacao_bg = database.relationship('PublicacaoBg')

    def atualizar_status(self):
        today = datetime.today().date()
        if self.inicio_periodo_lts and self.fim_periodo_lts:
            if self.inicio_periodo_lts <= today <= self.fim_periodo_lts:
                self.status = 'Vigente'
            else:
                self.status = 'Término da Licença para Tratamento de Saúde'


class FuncaoUser(database.Model):
    __tablename__ = "funcao_user"
    id = database.Column(database.Integer, primary_key=True)
    ocupacao = database.Column(database.String(50))
    user = database.relationship('User', backref='user_funcao')


@login_manager.user_loader
def load_usuario(id_usuario):
    return User.query.get(int(id_usuario))


class User(database.Model, UserMixin):
    __tablename__ = "user"
    id = database.Column(database.Integer, primary_key=True)
    nome = database.Column(database.String(100))
    email = database.Column(database.String(50))
    cpf = database.Column(database.String(50), unique=True)
    senha = database.Column(database.String(500))
    funcao_user_id = database.Column(
        database.Integer, database.ForeignKey('funcao_user.id'))
    obm_id_1 = database.Column(database.Integer, database.ForeignKey('obm.id'))
    obm_id_2 = database.Column(database.Integer, database.ForeignKey('obm.id'))
    localidade_id = database.Column(
        database.Integer, database.ForeignKey('localidade.id'))

    ip_address = database.Column(database.String(45))
    data_criacao = database.Column(
        database.DateTime, default=datetime.utcnow())
    data_ultimo_acesso = database.Column(
        database.DateTime, default=datetime.utcnow())
    endereco_acesso = database.Column(database.String(100))

    obm1 = database.relationship('Obm', foreign_keys=[obm_id_1])
    obm2 = database.relationship('Obm', foreign_keys=[obm_id_2])
    funcao_user = database.relationship(
        'FuncaoUser', foreign_keys=[funcao_user_id])
    localidade = database.relationship(
        'Localidade', foreign_keys=[localidade_id])


class Comportamento(database.Model):
    __tablename__ = "comportamento"
    id = database.Column(database.Integer, primary_key=True)
    conduta = database.Column(database.String(40))
    militar = database.relationship('Militar', backref='comportamento_militar')


class Punicao(database.Model):
    __tablename__ = "punicao"
    id = database.Column(database.Integer, primary_key=True)
    sancao = database.Column(database.String(30))
    militar = database.relationship('Militar', backref='punicao_militar')


class FuncaoGratificada(database.Model):
    __tablename__ = "funcao_gratificada"
    id = database.Column(database.Integer, primary_key=True)
    gratificacao = database.Column(database.String(40))
    militar = database.relationship('Militar', backref='gratificacao_militar')


class GC(database.Model):
    __tablename__ = "gc"
    id = database.Column(database.Integer, primary_key=True)
    # Ex: "ESPEC.", "MESTRE", "DOUT."
    descricao = database.Column(database.String(20))

    militares = database.relationship("Militar", back_populates="gc")


class Militar(database.Model):
    __tablename__ = "militar"
    id = database.Column(database.Integer, primary_key=True)
    nome_completo = database.Column(database.String(100))
    nome_guerra = database.Column(database.String(50))
    cpf = database.Column(database.String(40))
    rg = database.Column(database.String(10))
    nome_pai = database.Column(database.String(100))
    nome_mae = database.Column(database.String(100))
    matricula = database.Column(database.String(50))
    pis_pasep = database.Column(database.String(50))
    num_titulo_eleitor = database.Column(database.String(9))
    digito_titulo_eleitor = database.Column(database.String(2))
    zona = database.Column(database.String(5))
    secao = database.Column(database.String(5))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))
    quadro_id = database.Column(
        database.Integer, database.ForeignKey('quadro.id'))
    localidade_id = database.Column(
        database.Integer, database.ForeignKey('localidade.id'))
    antiguidade = database.Column(database.String(50))
    sexo = database.Column(database.String(40))
    raca = database.Column(database.String(40))
    data_nascimento = database.Column(database.Date)
    inclusao = database.Column(database.Date)
    completa_25_inclusao = database.Column(database.Date)
    completa_30_inclusao = database.Column(database.Date)
    punicao_id = database.Column(
        database.Integer, database.ForeignKey('punicao.id'))
    comportamento_id = database.Column(
        database.Integer, database.ForeignKey('comportamento.id'))
    efetivo_servico = database.Column(database.Date)
    completa_25_anos_sv = database.Column(database.Date)
    completa_30_anos_sv = database.Column(database.Date)
    anos = database.Column(database.Integer)
    meses = database.Column(database.Integer)
    dias = database.Column(database.Integer)
    total_dias = database.Column(database.Integer)
    idade_reserva_grad = database.Column(database.Integer)
    estado_civil = database.Column(
        database.Integer, database.ForeignKey('estado_civil.id'))
    especialidade_id = database.Column(
        database.Integer, database.ForeignKey('especialidade.id'))
    pronto = database.Column(database.String(5))
    situacao_id = database.Column(
        database.Integer, database.ForeignKey('situacao.id'))
    agregacoes_id = database.Column(
        database.Integer, database.ForeignKey('agregacoes.id'))
    destino_id = database.Column(
        database.Integer, database.ForeignKey('destino.id'))
    inicio_periodo = database.Column(database.Date)
    fim_periodo = database.Column(database.Date)
    ltip_afastamento_cargo_eletivo = database.Column(database.String(5))
    periodo_ltip = database.Column(database.String(50))
    total_ltip = database.Column(database.String(50))
    completa_25_anos_ltip = database.Column(database.String(50))
    completa_30_anos_ltip = database.Column(database.String(50))
    cursos = database.Column(database.String(50))
    grau_instrucao = database.Column(database.String(50))
    graduacao = database.Column(database.String(50))
    pos_graduacao = database.Column(database.String(50))
    mestrado = database.Column(database.String(50))
    doutorado = database.Column(database.String(50))
    cfsd = database.Column(database.String(50))
    cfc = database.Column(database.String(50))
    cfs = database.Column(database.String(50))
    cas = database.Column(database.String(50))
    choa = database.Column(database.String(50))
    cfo = database.Column(database.String(50))
    cbo = database.Column(database.String(50))
    cao = database.Column(database.String(50))
    csbm = database.Column(database.String(50))
    cursos_civis = database.Column(database.String(50))
    endereco = database.Column(database.String(100))
    complemento = database.Column(database.String(50))
    cidade = database.Column(database.String(50))
    estado = database.Column(database.String(50))
    cep = database.Column(database.String(50))
    celular = database.Column(database.String(50))
    email = database.Column(database.String(100))
    inclusao_bg = database.Column(database.String(50))
    soldado_tres = database.Column(database.String(50))
    soldado_dois = database.Column(database.String(50))
    soldado_um = database.Column(database.String(50))
    cabo = database.Column(database.String(50))
    terceiro_sgt = database.Column(database.String(50))
    segundo_sgt = database.Column(database.String(50))
    primeiro_sgt = database.Column(database.String(50))
    subtenente = database.Column(database.String(50))
    segundo_tenente = database.Column(database.String(50))
    primeiro_tenente = database.Column(database.String(50))
    cap = database.Column(database.String(50))
    maj = database.Column(database.String(50))
    tc = database.Column(database.String(50))
    cel = database.Column(database.String(50))
    alteracao_nome_guerra = database.Column(database.String(50))
    gc_id = database.Column(database.Integer, database.ForeignKey("gc.id"))

    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    ip_address = database.Column(database.String(45))
    funcao_gratificada_id = database.Column(
        database.Integer, database.ForeignKey('funcao_gratificada.id'))
    inativo = database.Column(
        database.Boolean, default=False)

    publicacoes_bg = database.relationship(
        'PublicacaoBg', backref='militar_pub', lazy=True)
    obm_funcoes = database.relationship(
        'MilitarObmFuncao', back_populates='militar', lazy=True)
    posto_grad = database.relationship(
        'PostoGrad', foreign_keys=[posto_grad_id])
    gc = database.relationship("GC", back_populates="militares")

    quadro = database.relationship('Quadro', foreign_keys=[quadro_id])
    especialidade = database.relationship(
        'Especialidade', backref='militares', foreign_keys=[especialidade_id])
    localidade = database.relationship(
        'Localidade', backref='militares_loc', foreign_keys=[localidade_id])
    situacao = database.relationship(
        'Situacao', backref='militares_situcao', foreign_keys=[situacao_id])


class MilitarObmFuncao(database.Model):
    __tablename__ = 'militar_obm_funcao'

    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    obm_id = database.Column(database.Integer, database.ForeignKey('obm.id'))
    funcao_id = database.Column(
        database.Integer, database.ForeignKey('funcao.id'))
    tipo = database.Column(database.Integer)
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    data_fim = database.Column(database.DateTime)

    militar = database.relationship('Militar', back_populates='obm_funcoes')
    obm = database.relationship('Obm', back_populates='militares_obms')
    funcao = database.relationship(
        'Funcao', back_populates='militares_funcoes')


class Meses(database.Model):
    __tablename__ = 'meses'

    id = database.Column(database.Integer, primary_key=True)
    mes = database.Column(database.String(50))


class Paf(database.Model):
    __tablename__ = 'paf'

    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(database.Integer, database.ForeignKey('militar.id'),
                                 nullable=True)  # Relaciona com Militar
    mes_usufruto = database.Column(database.String(50))
    qtd_dias_primeiro_periodo = database.Column(database.Integer)
    primeiro_periodo_ferias = database.Column(database.Date)
    fim_primeiro_periodo = database.Column(database.Date)
    qtd_dias_segundo_periodo = database.Column(database.Integer)
    segundo_periodo_ferias = database.Column(database.Date)
    fim_segundo_periodo = database.Column(database.Date)
    qtd_dias_terceiro_periodo = database.Column(database.Integer)
    terceiro_periodo_ferias = database.Column(database.Date)
    fim_terceiro_periodo = database.Column(database.Date)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))

    # Relacionamentos
    militar = database.relationship('Militar', backref='ferias', lazy=True)
    usuario = database.relationship('User', foreign_keys=[usuario_id])


class Categoria(database.Model):
    __tablename__ = 'categoria'

    id = database.Column(database.Integer, primary_key=True)
    sigla = database.Column(database.String(50))


class Motoristas(database.Model):
    __tablename__ = 'motoristas'

    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(database.Integer, database.ForeignKey('militar.id'),
                                 nullable=True)
    categoria_id = database.Column(database.Integer, database.ForeignKey('categoria.id'),
                                   nullable=True)
    siged = database.Column(database.String(200))
    boletim_geral = database.Column(database.String(200))
    created = database.Column(database.DateTime, default=datetime.utcnow)
    modified = database.Column(database.DateTime)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))
    vencimento_cnh = database.Column(database.DateTime)
    cnh_imagem = database.Column(database.String(255))
    desclassificar = database.Column(database.String(30))

    # Relacionamentos
    militar = database.relationship('Militar', backref='motoristas', lazy=True)
    categoria = database.relationship(
        'Categoria', backref='motorista_categoria', lazy=True)
    usuario = database.relationship('User', foreign_keys=[usuario_id])


class TabelaVencimento(database.Model):
    __tablename__ = "tabela_vencimento"

    id = database.Column(database.Integer, primary_key=True)
    nome = database.Column(database.String(100))
    lei = database.Column(database.String(100))
    data_inicio = database.Column(database.Date)
    data_fim = database.Column(database.Date)

    valores = database.relationship(
        'ValorDetalhadoPostoGrad', back_populates='tabela', lazy=True)


class ValorDetalhadoPostoGrad(database.Model):
    __tablename__ = "valor_detalhado_posto_grad"

    id = database.Column(database.Integer, primary_key=True)
    tabela_id = database.Column(database.Integer, database.ForeignKey(
        'tabela_vencimento.id'))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))

    # VENCIMENTOS
    soldo = database.Column(database.Numeric(10, 2))
    grat_tropa = database.Column(database.Numeric(10, 2))
    gams = database.Column(database.Numeric(10, 2))
    valor_bruto = database.Column(database.Numeric(10, 2))

    # CURSO
    curso_25 = database.Column(database.Numeric(10, 2))
    curso_30 = database.Column(database.Numeric(10, 2))
    curso_35 = database.Column(database.Numeric(10, 2))

    # VALOR BRUTO + CURSO
    bruto_esp = database.Column(database.Numeric(10, 2))
    bruto_mestre = database.Column(database.Numeric(10, 2))
    bruto_dout = database.Column(database.Numeric(10, 2))

    # FG
    fg_1 = database.Column(database.Numeric(10, 2))
    fg_2 = database.Column(database.Numeric(10, 2))
    fg_3 = database.Column(database.Numeric(10, 2))
    fg_4 = database.Column(database.Numeric(10, 2))

    aux_moradia = database.Column(database.Numeric(10, 2))
    etapas_capital = database.Column(database.String(20))
    etapas_interior = database.Column(database.String(20))
    seg_hora = database.Column(database.Numeric(10, 2))

    # GRATS TÉCNICAS
    motorista_a = database.Column(database.Numeric(10, 2))
    motorista_b = database.Column(database.Numeric(10, 2))
    motorista_ab = database.Column(database.Numeric(10, 2))
    motorista_cde = database.Column(database.Numeric(10, 2))
    tecnico_raiox = database.Column(database.Numeric(10, 2))
    tecnico_lab = database.Column(database.Numeric(10, 2))
    mecanico = database.Column(database.Numeric(10, 2))
    fluvial = database.Column(database.Numeric(10, 2))
    explosivista = database.Column(database.Numeric(10, 2))
    coe = database.Column(database.Numeric(10, 2))
    tripulante = database.Column(database.Numeric(10, 2))
    piloto = database.Column(database.Numeric(10, 2))
    aviacao = database.Column(database.Numeric(10, 2))
    mergulhador = database.Column(database.Numeric(10, 2))

    tabela = database.relationship(
        "TabelaVencimento", back_populates="valores")
    posto_grad = database.relationship("PostoGrad")


@listens_for(MilitaresADisposicao, 'before_insert')
def receive_before_insert(mapper, connection, target):
    target.atualizar_status()


@listens_for(MilitaresADisposicao, 'before_update')
def receive_before_update(mapper, connection, target):
    target.atualizar_status()


class Convocacao(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    data = database.Column(database.Date)
    convocados = database.Column(database.Integer)
    faltaram = database.Column(database.Integer)
    desistiram = database.Column(database.Integer)
    vagas_abertas = database.Column(database.Integer)
    created_at = database.Column(database.DateTime, default=datetime.utcnow)
    semana = database.Column(database.String)


class NomeConvocado(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    nome = database.Column(database.String(100))
    inscricao = database.Column(database.String(50))
    classificacao = database.Column(database.String(50))
    nota_final = database.Column(database.String(50))


class SituacaoConvocacao(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    situacao = database.Column(database.String(50))


class ControleConvocacao(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    classificacao = database.Column(database.String(50))
    inscricao = database.Column(database.String(50))
    nome = database.Column(database.String(100))
    nota_final = database.Column(database.String(50))
    ordem_de_convocacao = database.Column(database.String(50))
    apresentou = database.Column(
        database.Boolean, default=False)
    situacao_convocacao_id = database.Column(
        database.Integer, database.ForeignKey('situacao_convocacao.id'))
    matricula = database.Column(
        database.Boolean, default=False)
    numero_da_matricula_doe = database.Column(
        database.String(50))
    bg_matricula_doe = database.Column(database.String(50))
    portaria_convocacao = database.Column(database.String(50))
    bg_portaria_convocacao = database.Column(
        database.String(50))
    doe_portaria_convocacao = database.Column(
        database.String(50))
    notificacao_pessoal = database.Column(
        database.Boolean, default=False)
    termo_desistencia = database.Column(
        database.Boolean, default=False)
    siged_desistencia = database.Column(database.String(50))
    data_criacao = database.Column(
        database.DateTime, default=datetime.utcnow)

    situacao = database.relationship(
        'SituacaoConvocacao', backref='convocados')


class FichaAlunos(database.Model):
    __tablename__ = 'ficha_alunos'

    id = database.Column(database.Integer, primary_key=True)
    nome_completo = database.Column(database.String(100), nullable=False)
    nome_guerra = database.Column(
        database.String(100))  # removido nullable=False
    idade_atual = database.Column(database.Integer)
    cpf = database.Column(database.String(14))
    rg = database.Column(database.String(14))
    matricula = database.Column(database.String(10), unique=True)
    estado_civil = database.Column(database.String(20))
    nome_pai = database.Column(database.String(100))
    nome_mae = database.Column(database.String(100))
    pelotao = database.Column(database.String(100))
    email = database.Column(database.String(100))
    telefone = database.Column(database.String(15))
    telefone_emergencia = database.Column(database.String(15))
    rua = database.Column(database.String(200))
    bairro = database.Column(database.String(200))
    complemento = database.Column(database.String(200))
    caso_aluno_nao_resida_em_manaus = database.Column(database.String(200))
    estado = database.Column(database.String(100))
    formacao_academica = database.Column(database.String(200))
    tipo_sanguineo = database.Column(database.String(10))
    categoria_cnh = database.Column(database.String(20))
    classificacao_final_concurso = database.Column(database.String(50))
    nota_comportamento = database.Column(database.Float, default=5.0)
    comportamento = database.Column(database.String(20), default="Bom")
    ativo = database.Column(database.Boolean, default=True)
    foto = database.Column(database.String(200))


def __repr__(self):
    return f'<FichaAluno {self.nome_completo}>'


class AlunoInativo(database.Model):
    __tablename__ = 'alunos_inativos'

    id = database.Column(database.Integer, primary_key=True)
    ficha_aluno_id = database.Column(database.Integer, database.ForeignKey(
        'ficha_alunos.id'), nullable=False, unique=True)
    motivo_saida = database.Column(database.String(200), nullable=False)
    data_saida = database.Column(database.Date, nullable=False)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))

    ficha_aluno = database.relationship(
        'FichaAlunos', backref=database.backref('inativo', uselist=False))

    def __repr__(self):
        return f'<AlunoInativo {self.ficha_aluno.nome_completo}>'


def now_manaus():
    return datetime.now(pytz.timezone('America/Manaus'))


class LtsAlunos(database.Model):
    __tablename__ = 'lts_alunos'

    id = database.Column(database.Integer, primary_key=True)
    ficha_aluno_id = database.Column(
        database.Integer, database.ForeignKey('ficha_alunos.id'), nullable=False)
    boletim_interno = database.Column(database.String(50), nullable=False)
    data_inicio = database.Column(database.Date, nullable=False)
    data_fim = database.Column(database.Date, nullable=False)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))

    data_criacao = database.Column(database.DateTime, default=now_manaus)

    ficha_aluno = database.relationship('FichaAlunos', backref='licencas_lts')
    usuario = database.relationship('User', backref='lts_adicionadas')

    def __repr__(self):
        return f'<LTS {self.boletim_interno} - {self.ficha_aluno.nome_completo}>'


class RestricaoAluno(database.Model):
    __tablename__ = 'restricoes_alunos'

    id = database.Column(database.Integer, primary_key=True)
    ficha_aluno_id = database.Column(
        database.Integer, database.ForeignKey('ficha_alunos.id'), nullable=False)
    descricao = database.Column(database.Text, nullable=False)
    data_inicio = database.Column(database.Date, nullable=False)
    data_fim = database.Column(database.Date, nullable=False)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))
    data_criacao = database.Column(database.DateTime, default=now_manaus)

    ficha_aluno = database.relationship('FichaAlunos', backref='restricoes')
    usuario = database.relationship('User', backref='restricoes_registradas')

    def __repr__(self):
        return f'<Restrição {self.ficha_aluno.nome_completo} - {self.data_inicio} a {self.data_fim}>'


class MilitaresInativos(database.Model):
    __tablename__ = 'militares_inativos'

    id = database.Column(database.Integer, primary_key=True)
    nome_completo = database.Column(database.String(100), nullable=False)
    nome_guerra = database.Column(database.String(100))
    estado_civil_id = database.Column(
        database.Integer, database.ForeignKey('estado_civil.id'))
    nome_pai = database.Column(database.String(100))
    nome_mae = database.Column(database.String(100))
    matricula = database.Column(database.String(50))
    rg = database.Column(database.String(14))
    cpf = database.Column(database.String(14))
    pis_pasep = database.Column(database.String(50))
    posto_grad_id = database.Column(
        database.Integer, database.ForeignKey('posto_grad.id'))
    quadro_id = database.Column(
        database.Integer, database.ForeignKey('quadro.id'))
    sexo = database.Column(database.String(10))
    data_nascimento = database.Column(database.Date)
    idade_atual = database.Column(database.Integer)
    endereco = database.Column(database.String(200))
    complemento = database.Column(database.String(200))
    cidade = database.Column(database.String(100))
    estado = database.Column(database.String(100))
    cep = database.Column(database.String(20))
    celular = database.Column(database.String(15))
    email = database.Column(database.String(100))
    modalidade = database.Column(database.String(50))
    doe = database.Column(database.String(50))

    posto_grad = database.relationship(
        'PostoGrad', foreign_keys=[posto_grad_id])
    quadro = database.relationship('Quadro', foreign_keys=[quadro_id])

    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))
    data_criacao = database.Column(database.DateTime, default=datetime.utcnow)
    ip_address = database.Column(database.String(45))


class TokenVerificacao(database.Model):
    __tablename__ = 'token_verificacao'
    id = database.Column(database.Integer, primary_key=True)
    cpf = database.Column(database.String(50), nullable=False)
    token = database.Column(database.String(100), nullable=False)
    criado_em = database.Column(database.DateTime, default=datetime.utcnow)
    usado = database.Column(database.Boolean, default=False)


class SegundoVinculo(database.Model):
    __tablename__ = "segundo_vinculo"
    id = database.Column(database.Integer, primary_key=True)
    militar_id = database.Column(
        database.Integer, database.ForeignKey('militar.id'))
    possui_vinculo = database.Column(database.Boolean, default=False)
    quantidade_vinculos = database.Column(database.Integer)
    descricao_vinculo = database.Column(database.String(255))
    horario_inicio = database.Column(database.Time)
    horario_fim = database.Column(database.Time)
    data_registro = database.Column(database.DateTime, default=datetime.utcnow)

    militar = database.relationship('Militar', backref='segundo_vinculo')


class RecompensaAluno(database.Model):
    __tablename__ = 'recompensas_alunos'

    id = database.Column(database.Integer, primary_key=True)
    ficha_aluno_id = database.Column(
        database.Integer, database.ForeignKey('ficha_alunos.id'), nullable=False)
    natureza = database.Column(database.String(200), nullable=False)
    autoridade = database.Column(database.String(200), nullable=False)
    boletim = database.Column(database.String(50), nullable=False)
    discriminacao = database.Column(database.Text, nullable=False)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))
    data_criacao = database.Column(database.DateTime, default=now_manaus)

    ficha_aluno = database.relationship('FichaAlunos', backref='recompensas')
    usuario = database.relationship('User', backref='recompensas_registradas')


class SancaoAluno(database.Model):
    __tablename__ = 'sancoes_alunos'

    id = database.Column(database.Integer, primary_key=True)
    ficha_aluno_id = database.Column(
        database.Integer, database.ForeignKey('ficha_alunos.id'), nullable=False)
    natureza = database.Column(database.String(200), nullable=False)
    numero_dias = database.Column(database.Integer, nullable=False)
    boletim = database.Column(database.String(50), nullable=False)
    data_inicio = database.Column(database.Date, nullable=False)
    data_fim = database.Column(database.Date, nullable=False)
    discriminacao = database.Column(database.Text, nullable=False)
    usuario_id = database.Column(
        database.Integer, database.ForeignKey('user.id'))
    data_criacao = database.Column(database.DateTime, default=now_manaus)

    ficha_aluno = database.relationship('FichaAlunos', backref='sancoes')
    usuario = database.relationship('User', backref='sancoes_registradas')
