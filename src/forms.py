
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, SubmitField, BooleanField, SelectField, DateField, IntegerField,
                     MultipleFileField, FileField)
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, NumberRange, Email, Optional
from src.models import Militar, User


def coerce_int_or_none(value):
    if value == '' or value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class FormMilitar(FlaskForm):
    nome_completo = StringField('Nome do Militar')
    nome_guerra = StringField('Nome de Guerra')
    estado_civil = SelectField("Estado Civil", choices=[])
    nome_pai = StringField('Nome do Pai')
    nome_mae = StringField('Nome da Mãe')
    posto_grad_id = SelectField('Posto/Graduação', choices=[])
    quadro_id = SelectField('Quadro', choices=[])
    obm_ids_1 = SelectField('OBM', choices=[], coerce=coerce_int_or_none)
    funcao_ids_1 = SelectField('Função', choices=[], coerce=coerce_int_or_none)
    obm_ids_2 = SelectField('Segunda OBM', choices=[], coerce=coerce_int_or_none)
    funcao_ids_2 = SelectField('Segunda Função', choices=[], coerce=coerce_int_or_none)
    localidade_id = SelectField('Localidade', choices=[])
    funcao_gratificada_id = SelectField('Função Gratificada', choices=[])
    transferencia = StringField("Transferência")
    antiguidade = StringField("Antiguidade")
    sexo = StringField("Sexo")
    raca = StringField("Raça")
    data_nascimento = DateField("Data de Nascimento", format='%Y-%m-%d', validators=[Optional()])
    idade_atual = IntegerField("Idade Atual", validators=[NumberRange(0, 120)])
    inclusao = DateField("Inclusão", format='%Y-%m-%d')
    completa_25_inclusao = StringField("Completa 25 anos de inclusão")
    completa_30_inclusao = StringField("Completa 30 anos de inclusão")
    punicao_id = SelectField("Punição", choices=[])
    comportamento_id = SelectField("Comportamento", choices=[])
    efetivo_servico = DateField("Efetivo Serviço", format='%Y-%m-%d', validators=[Optional()])
    completa_25_anos_sv = StringField("Completa 25 anos de Serviço")
    completa_30_anos_sv = StringField("Completa 30 anos de Serviço")
    anos = IntegerField("Anos")
    meses = IntegerField("Meses")
    dias = IntegerField("Dias")
    total_dias = IntegerField("Total em dias")
    idade_reserva_grad = StringField("Idade para reserva por Grad.")
    especialidade_id = SelectField("Especialidade", choices=[])
    matricula = StringField("Matrícula", render_kw={"placeholder": "123.456-7 A"})
    rg = StringField("RG", render_kw={"placeholder": "1234"})
    pis_pasep = StringField("PIS/PASEP", render_kw={"placeholder": "123.45678.90-1"})
    cpf = StringField("CPF", render_kw={"placeholder": "123.456.789-01"})
    num_titulo_eleitor = StringField("Número do Título de Eleitor", render_kw={"placeholder": "123465789"})
    digito_titulo_eleitor = StringField("Dígito do Título de Eleitor", render_kw={"placeholder": "00"})
    zona = StringField("Zona")
    secao = StringField("Seção")
    pronto = SelectField("Pronto", choices=[('sim', 'Sim'), ('nao', 'Não')])
    situacao_id = SelectField("Situação", choices=[])
    agregacoes_id = SelectField("Agregações", choices=[])
    destino_id = SelectField("Destino", choices=[])
    inicio_periodo = DateField("INÍCIO", format='%Y-%m-%d', validators=[Optional()])
    fim_periodo = DateField("TÉRMINO", format='%Y-%m-%d', validators=[Optional()])
    situacao_militar = StringField("Publicação")
    ltip_afastamento_cargo_eletivo = StringField("LTIP: Afastamento/Cargo Eletivo", default="NÃO")
    periodo_ltip = StringField("Período")
    total_ltip = StringField("Total")
    completa_25_anos_ltip = StringField("Completa 25 anos de serviço com desconto de LTIP")
    completa_30_anos_ltip = StringField("Completa 30 anos de serviço com desconto de LTIP")
    cursos = StringField("Cursos")
    grau_instrucao = StringField("Grau de Instrução")
    graduacao = StringField("Graduação")
    pos_graduacao = StringField("Pós-Graduação")
    mestrado = StringField("Mestrado")
    doutorado = StringField("Doutorado")
    cfsd = StringField("CFSD")
    cfc = StringField("CFC")
    cfs = StringField("CFS")
    cas = StringField("CAS")
    choa = StringField("CHOA")
    cfo = StringField("CFO")
    cbo = StringField("CBO")
    cao = StringField("CAO")
    csbm = StringField("CSBM")
    cursos_civis = StringField("Cursos Civis")
    endereco = StringField('Endereço', render_kw={"placeholder": "Rua, Avenida, Nº"})
    complemento = StringField('Complemento', render_kw={"placeholder": "Bloco, Apt, Casa"})
    cidade = StringField('Cidade')
    estado = StringField('Estado', render_kw={"placeholder": "Sigla"})
    cep = StringField('CEP', render_kw={"placeholder": "69000-000"})
    celular = StringField("Celular")
    email = StringField("E-mail")
    inclusao_bg = StringField("Inclusão")
    soldado_tres = StringField("Soldado 3")
    soldado_dois = StringField("Soldado 2")
    soldado_um = StringField("Soldado 1")
    cabo = StringField("Cabo")
    terceiro_sgt = StringField("3º Sargento")
    segundo_sgt = StringField("2º Sargento")
    primeiro_sgt = StringField("1º Sargento")
    subtenente = StringField("Subtenente")
    segundo_tenente = StringField("2º TEN")
    publicidade_segundo_tenente = StringField("Publicidade")
    primeiro_tenente = StringField("1º TEN")
    publicidade_primeiro_tenente = StringField("Publicidade")
    cap = StringField("CAP")
    pub_cap = StringField("Publicidade")
    maj = StringField("MAJ")
    pub_maj = StringField("Publicidade")
    tc = StringField("TC")
    pub_tc = StringField("Publicidade")
    cel = StringField("CEL")
    pub_cel = StringField("Publicidade")
    alteracao_nome_guerra = StringField("Alteração de nome de guerra")
    pub_alteracao = StringField("Publicidade")
    botao_submit = SubmitField('Salvar')
    arquivo = MultipleFileField('Adicionar Boletins Gerais.')

    def validate_nome(self, cpf):
        usuario = Militar.query.filter_by(cpf=cpf.data).first()
        if usuario:
            raise ValidationError('Militar já cadastrado.')


class FormLogin(FlaskForm):
    cpf = StringField('CPF', validators=[DataRequired()])
    senha = PasswordField('Senha', validators=[DataRequired(), Length(6, 20)])
    lembrar_dados = BooleanField('Lembre-se de mim')
    botao_submit_login = SubmitField('Entrar')


class FormCriarUsuario(FlaskForm):
    nome = StringField('Nome Completo', validators=[DataRequired()])
    cpf = StringField('CPF', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    funcao_user_id = SelectField('Função', choices=[], validators=[DataRequired()])
    obm_id_1 = SelectField('OBM 1', choices=[], coerce=coerce_int_or_none)
    obm_id_2 = SelectField('OBM 2', choices=[], coerce=coerce_int_or_none)
    localidade_id = SelectField('Localidade', choices=[], coerce=coerce_int_or_none)
    senha = PasswordField('Senha', validators=[Optional(), Length(6, 20)])
    confirmar_senha = PasswordField('Confirmar Senha', validators=[Optional(), EqualTo('senha')])
    botao_submit_criar_conta = SubmitField('Salvar')

    def validate_email(self, email):
        # Obtenha o usuário do formulário, se disponível
        current_user_id = getattr(self, 'current_user_id', None)
        if current_user_id:
            usuario = User.query.filter(User.email == email.data, User.id != current_user_id).first()
        else:
            usuario = User.query.filter_by(email=email.data).first()

        if usuario:
            raise ValidationError('E-mail já cadastrado. Cadastre-se com outro e-mail ou faça Login para continuar.')


class FormMilitaresDisposicao(FlaskForm):
    posto_grad = StringField('POSTO/GRAD')


class FormMilitarFerias(FlaskForm):
    posto_grad_id = SelectField('Posto/Graduação', choices=[])
    nome_completo = StringField('Nome do Militar')
    matricula = StringField('Matricula')
    quadro_id = SelectField('Quadro', choices=[])
    mes_usufruto = SelectField("Mês de usufruto", choices=[])
    qtd_dias_primeiro_periodo = IntegerField('Quantidade de dias do 1º período de férias')
    primeiro_periodo_ferias = DateField("1º Período de férias", format='%Y-%m-%d', validators=[Optional()])
    fim_primeiro_periodo = DateField("Fim do 1º Período de Férias", format='%Y-%m-%d', validators=[Optional()])
    qtd_dias_segundo_periodo = IntegerField("Quantidade de dias do 2º período de férias")
    segundo_periodo_ferias = DateField("2º Período de férias", format='%Y-%m-%d', validators=[Optional()])
    fim_segundo_periodo = DateField("Fim do 2º Período de Férias", format='%Y-%m-%d', validators=[Optional()])
    qtd_dias_terceiro_periodo = IntegerField("Quantidade de dias do 3º período de férias")
    terceiro_periodo_ferias = DateField("3º Período de férias", format='%Y-%m-%d', validators=[Optional()])
    fim_terceiro_periodo = DateField("Fim do 3º Período de Férias", format='%Y-%m-%d', validators=[Optional()])
    troca_mes_ferias = SelectField("Alteração de mês de usufruto das Férias", choices=[])


class FormMotoristas(FlaskForm):
    posto_grad_id = StringField('Posto/Graduação')
    nome_completo = SelectField('Nome do Militar', choices=[], coerce=int)
    matricula = StringField('Matricula')
    categoria_id = SelectField('Categoria', choices=[])
    obm_id_1 = StringField('OBM 1')
    siged = StringField('SIGED')
    boletim_geral = StringField('Boletim Geral')
    vencimento_cnh = DateField('Vencimento da CNH')
    botao_salvar_motorista = SubmitField('Salvar')
    cnh_imagem = FileField('CNH (Imagem)')  # Campo para upload de arquivo


class FormFiltroMotorista(FlaskForm):
    obm_id = SelectField('OBM', choices=[])
    categoria_id = SelectField('Categoria', choices=[])
    posto_grad_id = SelectField('Posto/Grad', choices=[])
