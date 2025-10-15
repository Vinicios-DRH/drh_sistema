
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (FieldList, FloatField, FormField, HiddenField, StringField, PasswordField, SubmitField, BooleanField, SelectField, DateField, IntegerField,
                     MultipleFileField, FileField, DecimalField, TextAreaField, TimeField)
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, NumberRange, Email, Optional, InputRequired, Regexp
from src.models import Militar, User, SituacaoConvocacao


TIPO_DECLARACAO_CHOICES = [
    ("positiva", "Positiva (com vínculo)"), ("negativa", "Negativa (sem vínculo)")]

EMPREGADOR_TIPO_CHOICES = [("publico", "Público"), ("privado", "Privado"),
                           ("cooperativa", "Cooperativa"), ("autonomo", "Autônomo")]

NATUREZA_VINCULO_CHOICES = [("efetivo", "Efetivo"), ("contratado", "Contratado"), (
    "prestacao_servicos", "Prestação de serviços"), ("autonomo", "Autônomo")]


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
    obm_ids_2 = SelectField('Segunda OBM', choices=[],
                            coerce=coerce_int_or_none)
    funcao_ids_2 = SelectField(
        'Segunda Função', choices=[], coerce=coerce_int_or_none)
    localidade_id = SelectField('Localidade', choices=[])
    funcao_gratificada_id = SelectField('Função Gratificada', choices=[])
    transferencia = StringField("Transferência")
    antiguidade = StringField("Antiguidade")
    sexo = StringField("Sexo")
    raca = StringField("Raça")
    data_nascimento = DateField(
        "Data de Nascimento", format='%Y-%m-%d', validators=[Optional()])
    idade_atual = IntegerField("Idade Atual", validators=[NumberRange(0, 120)])
    inclusao = DateField("Inclusão", format='%Y-%m-%d')
    completa_25_inclusao = StringField("Completa 25 anos de inclusão")
    completa_30_inclusao = StringField("Completa 30 anos de inclusão")
    punicao_id = SelectField("Punição", choices=[])
    comportamento_id = SelectField("Comportamento", choices=[])
    efetivo_servico = DateField(
        "Efetivo Serviço", format='%Y-%m-%d', validators=[Optional()])
    completa_25_anos_sv = StringField("Completa 25 anos de Serviço")
    completa_30_anos_sv = StringField("Completa 30 anos de Serviço")
    anos = IntegerField("Anos")
    meses = IntegerField("Meses")
    dias = IntegerField("Dias")
    total_dias = IntegerField("Total em dias")
    idade_reserva_grad = StringField("Idade para reserva por Grad.")
    especialidade_id = SelectField("Especialidade", choices=[])
    matricula = StringField("Matrícula", render_kw={
                            "placeholder": "123.456-7 A"})
    rg = StringField("RG", render_kw={"placeholder": "1234"})
    pis_pasep = StringField(
        "PIS/PASEP", render_kw={"placeholder": "123.45678.90-1"})
    cpf = StringField("CPF", render_kw={"placeholder": "123.456.789-01"})
    num_titulo_eleitor = StringField("Número do Título de Eleitor", render_kw={
                                     "placeholder": "1234657890"})
    digito_titulo_eleitor = StringField(
        "Dígito do Título de Eleitor", render_kw={"placeholder": "00"})
    zona = StringField("Zona")
    secao = StringField("Seção")
    pronto = SelectField("Pronto", choices=[('sim', 'Sim'), ('nao', 'Não')])
    situacao_id = SelectField("Situação", choices=[])
    agregacoes_id = SelectField("Agregações", choices=[])
    destino_id = SelectField("Destino", choices=[])
    inicio_periodo = DateField(
        "INÍCIO", format='%Y-%m-%d', validators=[Optional()])
    fim_periodo = DateField("TÉRMINO", format='%Y-%m-%d',
                            validators=[Optional()])
    situacao_militar = StringField("Publicação")
    ltip_afastamento_cargo_eletivo = StringField(
        "LTIP: Afastamento/Cargo Eletivo", default="NÃO")
    periodo_ltip = StringField("Período")
    total_ltip = StringField("Total")
    completa_25_anos_ltip = StringField(
        "Completa 25 anos de serviço com desconto de LTIP")
    completa_30_anos_ltip = StringField(
        "Completa 30 anos de serviço com desconto de LTIP")
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
    endereco = StringField('Endereço', render_kw={
                           "placeholder": "Rua, Avenida, Nº"})
    complemento = StringField('Complemento', render_kw={
                              "placeholder": "Bloco, Apt, Casa"})
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
    cpf = StringField('CPF', )
    senha = PasswordField('Senha', validators=[Length(6, 20)])
    lembrar_dados = BooleanField('Lembre-se de mim')
    botao_submit_login = SubmitField('Entrar')


class FormCriarUsuario(FlaskForm):
    nome = StringField('Nome Completo', )
    cpf = StringField('CPF', )
    email = StringField('E-mail', validators=[Email()])
    funcao_user_id = SelectField(
        'Função', choices=[], )
    obm_id_1 = SelectField('OBM 1', choices=[], coerce=coerce_int_or_none)
    obm_id_2 = SelectField('OBM 2', choices=[], coerce=coerce_int_or_none)
    localidade_id = SelectField(
        'Localidade', choices=[], coerce=coerce_int_or_none)
    senha = PasswordField('Senha', validators=[Optional(), Length(6, 20)])
    confirmar_senha = PasswordField('Confirmar Senha', validators=[
                                    Optional(), EqualTo('senha')])
    botao_submit_criar_conta = SubmitField('Salvar')

    def validate_email(self, email):
        # Obtenha o usuário do formulário, se disponível
        current_user_id = getattr(self, 'current_user_id', None)
        if current_user_id:
            usuario = User.query.filter(
                User.email == email.data, User.id != current_user_id).first()
        else:
            usuario = User.query.filter_by(email=email.data).first()

        if usuario:
            raise ValidationError(
                'E-mail já cadastrado. Cadastre-se com outro e-mail ou faça Login para continuar.')


class FormMilitaresDisposicao(FlaskForm):
    posto_grad = StringField('POSTO/GRAD')


class FormMilitarFerias(FlaskForm):
    posto_grad_id = SelectField('Posto/Graduação', choices=[])
    nome_completo = StringField('Nome do Militar')
    matricula = StringField('Matricula')
    quadro_id = SelectField('Quadro', choices=[])
    mes_usufruto = SelectField("Mês de usufruto", choices=[])
    qtd_dias_primeiro_periodo = IntegerField(
        'Quantidade de dias do 1º período de férias')
    primeiro_periodo_ferias = DateField(
        "1º Período de férias", format='%Y-%m-%d', validators=[Optional()])
    fim_primeiro_periodo = DateField(
        "Fim do 1º Período de Férias", format='%Y-%m-%d', validators=[Optional()])
    qtd_dias_segundo_periodo = IntegerField(
        "Quantidade de dias do 2º período de férias")
    segundo_periodo_ferias = DateField(
        "2º Período de férias", format='%Y-%m-%d', validators=[Optional()])
    fim_segundo_periodo = DateField(
        "Fim do 2º Período de Férias", format='%Y-%m-%d', validators=[Optional()])
    qtd_dias_terceiro_periodo = IntegerField(
        "Quantidade de dias do 3º período de férias")
    terceiro_periodo_ferias = DateField(
        "3º Período de férias", format='%Y-%m-%d', validators=[Optional()])
    fim_terceiro_periodo = DateField(
        "Fim do 3º Período de Férias", format='%Y-%m-%d', validators=[Optional()])
    troca_mes_ferias = SelectField(
        "Alteração de mês de usufruto das Férias", choices=[])


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


class TabelaVencimentoForm(FlaskForm):
    nome = StringField("Nome da Tabela", )
    lei = StringField("Lei", )
    data_inicio = DateField(
        "Data de Início", format='%Y-%m-%d', )
    data_fim = DateField("Data de Fim", format='%Y-%m-%d',
                         validators=[Optional()])
    posto_grad = SelectField("Posto/Graduação", choices=[])

    # Campos genéricos para um posto, devem ser duplicados dinamicamente no template com base nos postos existentes
    soldo = DecimalField("Soldo", validators=[Optional()])
    grat_tropa = DecimalField("Gratificação de Tropa", validators=[Optional()])
    gams = DecimalField("GAMS", validators=[Optional()])
    valor_bruto = DecimalField("Valor Bruto", validators=[Optional()])
    curso_25 = DecimalField("Espec. 25%", validators=[Optional()])
    curso_30 = DecimalField("Mestre 30%", validators=[Optional()])
    curso_35 = DecimalField("Dout. 35%", validators=[Optional()])
    bruto_esp = DecimalField("Bruto + ESPEC.", validators=[Optional()])
    bruto_mestre = DecimalField("Bruto + MESTRE", validators=[Optional()])
    bruto_dout = DecimalField("Bruto + DOUT.", validators=[Optional()])
    fg_1 = DecimalField("FG-1", validators=[Optional()])
    fg_2 = DecimalField("FG-2", validators=[Optional()])
    fg_3 = DecimalField("FG-3", validators=[Optional()])
    fg_4 = DecimalField("FG-4", validators=[Optional()])
    aux_moradia = DecimalField("Auxílio Moradia", validators=[Optional()])
    etapas_capital = StringField("Etapas Capital", validators=[Optional()])
    etapas_interior = StringField("Etapas Interior", validators=[Optional()])
    seg_hora = DecimalField("SEG Hora", validators=[Optional()])

    motorista_a = DecimalField("Motorista A", validators=[Optional()])
    motorista_b = DecimalField("Motorista B", validators=[Optional()])
    motorista_ab = DecimalField("Motorista AB", validators=[Optional()])
    motorista_cde = DecimalField("Motorista CDE", validators=[Optional()])
    tecnico_raiox = DecimalField("Técnico Raio-X", validators=[Optional()])
    tecnico_lab = DecimalField("Técnico Lab", validators=[Optional()])
    mecanico = DecimalField("Mecânico", validators=[Optional()])
    fluvial = DecimalField("Fluvial", validators=[Optional()])
    explosivista = DecimalField("Explosivista", validators=[Optional()])
    coe = DecimalField("COE", validators=[Optional()])
    tripulante = DecimalField("Tripulante", validators=[Optional()])
    piloto = DecimalField("Piloto", validators=[Optional()])
    aviacao = DecimalField("Aviação", validators=[Optional()])
    mergulhador = DecimalField("Mergulhador", validators=[Optional()])

    submit = SubmitField("Salvar Tabela")


class ImpactoForm(FlaskForm):
    data_inicio = DateField(
        "Data de Início", format='%Y-%m-%d', )
    data_fim = DateField("Data de Fim", format='%Y-%m-%d',
                         )

    posto_origem = SelectField(
        "Posto/Graduação Atual", coerce=int, )
    posto_destino = SelectField(
        "Posto/Graduação da Promoção", coerce=int, )

    efetivo = IntegerField("Efetivo", validators=[
        NumberRange(min=1, max=1000,
                    message="Insira um número entre 1 e 1000")
    ])

    submit = SubmitField("Calcular Impacto")


class ControleConvocacaoForm(FlaskForm):
    classificacao = StringField('Classificação', validators=[Length(max=50)])
    inscricao = StringField('Inscrição', validators=[Length(max=50)])
    nome = SelectField(
        'Nome', choices=[], coerce=int)
    nota_final = StringField('Nota Final', validators=[Length(max=50)])
    ordem_de_convocacao = StringField(
        'Ordem de Convocação', validators=[Length(max=50)])
    apresentou = BooleanField('Apresentou?')
    situacao_convocacao_id = SelectField(
        'Situação da Convocação', coerce=int, )
    matricula = BooleanField('Efetivou Matrícula?')
    numero_da_matricula_doe = StringField(
        'Número da Matrícula (DOE)', validators=[Length(max=50)])
    bg_matricula_doe = StringField(
        'BG Matrícula (DOE)', validators=[Length(max=50)])
    portaria_convocacao = StringField(
        'Portaria de Convocação', validators=[Length(max=50)])
    bg_portaria_convocacao = StringField(
        'BG Portaria de Convocação', validators=[Length(max=50)])
    doe_portaria_convocacao = StringField(
        'DOE Portaria de Convocação', validators=[Length(max=50)])
    notificacao_pessoal = BooleanField('Notificação Pessoal?')
    termo_desistencia = BooleanField('Termo de Desistência Assinado?')
    siged_desistencia = StringField(
        'SIGED da Desistência', validators=[Length(max=50)])
    submit = SubmitField('Salvar')


class FichaAlunosForm(FlaskForm):
    foto = FileField('Foto do Aluno', validators=[FileAllowed(['jpg','jpeg','png'])])
    nome_completo = StringField('Nome Completo', validators=[Optional(), Length(max=100)])
    nome_guerra = StringField('Nome de Guerra', validators=[Optional(), Length(max=50)])
    idade_atual = IntegerField("Idade Atual", validators=[Optional(), NumberRange(0, 120)])
    cpf = StringField('CPF', validators=[Optional(), Length(max=14)])
    rg  = StringField('RG',  validators=[Optional(), Length(max=14)])

    # IMPORTANTES: permitem vazio
    estado_civil = SelectField('Estado civil', choices=[], validators=[Optional()], validate_choice=False)
    pelotao      = SelectField('Pelotão',       choices=[], validators=[Optional()], validate_choice=False)
    estado       = SelectField('Estado',        choices=[], validators=[Optional()], validate_choice=False)
    categoria_cnh= SelectField('Categoria CNH', choices=[], validators=[Optional()], validate_choice=False)

    nome_pai = StringField('Nome do pai', validators=[Optional(), Length(max=100)])
    nome_mae = StringField('Nome da mãe', validators=[Optional(), Length(max=100)])
    email    = StringField('E-mail', validators=[Optional(), Email()])
    telefone = StringField('Telefone para contato', validators=[Optional(), Length(max=15)])
    telefone_emergencia = StringField('Telefone de emergência', validators=[Optional(), Length(max=15)])

    rua = StringField('Rua', validators=[Optional(), Length(max=200)])
    bairro = StringField('Bairro', validators=[Optional(), Length(max=200)])
    complemento = StringField('Complemento', validators=[Optional(), Length(max=200)])
    estado = SelectField('Estado', choices=[], validators=[Optional()], validate_choice=False)

    formacao_academica = StringField('Formação Acadêmica', validators=[Optional(), Length(max=200)])
    tipo_sanguineo     = StringField('Tipo Sanguíneo e Fator', validators=[Optional(), Length(max=10)])

    comportamento = SelectField('Comportamento',
        choices=[('Excepcional','Excepcional'),('Ótimo','Ótimo'),('Bom','Bom'),
                 ('Insuficiente','Insuficiente'),('Mau','Mau')],
        validators=[Optional()], validate_choice=False)

    # AGORA OPCIONAL, com default
    nota_comportamento = FloatField('Nota do Comportamento',
                                    validators=[Optional(), NumberRange(min=0, max=10)],
                                    default=5.0)

    hospedagem_aluno_de_fora = StringField('Hospedagem (se fora de Manaus )',
                                           validators=[Optional(), Length(max=200)])
    matricula = StringField('Matrícula', validators=[Optional(), Length(max=50)])  # relaxei o max
    botao_submit = SubmitField('Salvar')
    

class InativarAlunoForm(FlaskForm):
    motivo_saida = SelectField('Motivo da Saída', choices=[
        ('Desistência', 'Desistência'),
        ('Desligamento por Conduta', 'Desligamento por Conduta'),
        ('Motivo de Saúde', 'Motivo de Saúde'),
        ('Outros', 'Outros')
    ], validators=[InputRequired()])
    data_saida = DateField('Data da Saída', validators=[InputRequired()])
    botao_submit = SubmitField('Confirmar Inativação')


class LtsAlunoForm(FlaskForm):
    boletim_interno = StringField("Boletim Interno (BI)", validators=[
                                  InputRequired(), Length(max=50)])
    data_inicio = DateField("Data de Início", validators=[InputRequired()])
    data_fim = DateField("Data de Término", validators=[InputRequired()])
    botao_submit = SubmitField("Registrar LTS")


class RestricaoAlunoForm(FlaskForm):
    descricao = TextAreaField(
        "Motivo/Descrição da Restrição", validators=[InputRequired()])
    data_inicio = DateField("Data de Início", validators=[InputRequired()])
    data_fim = DateField("Data de Término", validators=[InputRequired()])
    botao_submit = SubmitField("Registrar Restrição")


class FormMilitarInativo(FlaskForm):
    nome_completo = StringField('Nome Completo', validators=[DataRequired()])
    nome_guerra = StringField('Nome de Guerra')
    estado_civil_id = SelectField('Estado Civil', coerce=int)
    nome_pai = StringField('Nome do Pai')
    nome_mae = StringField('Nome da Mãe')
    matricula = StringField('Matrícula')
    rg = StringField('RG')
    pis_pasep = StringField('PIS/PASEP')
    cpf = StringField('CPF')
    posto_grad_id = SelectField('Posto/Graduação', coerce=int)
    quadro_id = SelectField('Quadro', coerce=int)
    sexo = SelectField('Sexo', choices=[('M', 'Masculino'), ('F', 'Feminino')])
    data_nascimento = DateField(
        'Data de Nascimento', format='%Y-%m-%d', validators=[Optional()])
    endereco = StringField('Endereço')
    complemento = StringField('Complemento')
    cidade = StringField('Cidade')
    estado = StringField('Estado')
    cep = StringField('CEP')
    celular = StringField('Celular')
    email = StringField('Email')
    modalidade = SelectField('Modalidade', choices=[
        ('A PEDIDO', 'A PEDIDO'),
        ('A BEM DA DISCIPLINA', 'A BEM DA DISCIPLINA'),
        ('DEMITIDO A PEDIDO', 'DEMITIDO A PEDIDO'),
        ('DEMITIDO EX-OFFICIO', 'DEMITIDO EX-OFFICIO'),
        ('EX-OFFICIO', 'EX-OFFICIO'),
        ('FALECIDOS', 'FALECIDOS'),
        ('LICENCIAMENTO', 'LICENCIAMENTO'),
        ('PROC. INVALID. DE ATO', 'PROC. INVALID. DE ATO'),
        ('REFORMA REMUNERADA', 'REFORMA REMUNERADA'),
        ('REFORMA INVALIDEZ', 'REFORMA INVALIDEZ'),
        ('RESERVA ADM', 'RESERVA ADM'),
    ], validators=[Optional()])

    doe = StringField('DOE')
    inativo = BooleanField('Inativo', default=True)
    botao_submit = SubmitField('Salvar')


class IdentificacaoForm(FlaskForm):
    cpf = StringField("CPF", validators=[DataRequired()])
    email = StringField("E-mail",
                        validators=[DataRequired(), Email()])
    submit = SubmitField("Prosseguir")


class TokenForm(FlaskForm):
    token = StringField("Token de Verificação", validators=[
                        DataRequired(), Length(min=6, max=6)])
    submit = SubmitField("Validar Token")


class CriarSenhaForm(FlaskForm):
    senha = PasswordField('Senha', validators=[
                          DataRequired(), Length(min=6, max=20)])
    confirmar_senha = PasswordField('Confirmar Senha', validators=[
                                    DataRequired(), EqualTo('senha')])
    submit = SubmitField('Criar Conta')


class AtualizacaoCadastralForm(FlaskForm):
    celular = StringField('Celular', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    endereco = StringField('Endereço', validators=[DataRequired()])
    complemento = StringField('Complemento', validators=[Optional()])
    cidade = StringField('Cidade', validators=[DataRequired()])
    estado = SelectField('Estado', choices=[
        ('', '-- Selecione o Estado --'),
        ('AC', 'Acre'),
        ('AL', 'Alagoas'),
        ('AP', 'Amapá'),
        ('AM', 'Amazonas'),
        ('BA', 'Bahia'),
        ('CE', 'Ceará'),
        ('DF', 'Distrito Federal'),
        ('ES', 'Espírito Santo'),
        ('GO', 'Goiás'),
        ('MA', 'Maranhão'),
        ('MT', 'Mato Grosso'),
        ('MS', 'Mato Grosso do Sul'),
        ('MG', 'Minas Gerais'),
        ('PA', 'Pará'),
        ('PB', 'Paraíba'),
        ('PR', 'Paraná'),
        ('PE', 'Pernambuco'),
        ('PI', 'Piauí'),
        ('RJ', 'Rio de Janeiro'),
        ('RN', 'Rio Grande do Norte'),
        ('RS', 'Rio Grande do Sul'),
        ('RO', 'Rondônia'),
        ('RR', 'Roraima'),
        ('SC', 'Santa Catarina'),
        ('SP', 'São Paulo'),
        ('SE', 'Sergipe'),
        ('TO', 'Tocantins')
    ], validators=[DataRequired()])

    grau_instrucao = SelectField('Grau de Instrução', choices=[
        ('', '-- Selecione --'),
        ('Ensino Médio Incompleto', 'Ensino Médio Incompleto'),
        ('Ensino Médio Completo', 'Ensino Médio Completo'),
        ('Ensino Técnico', 'Ensino Técnico'),
        ('Ensino Superior Incompleto', 'Ensino Superior Incompleto'),
        ('Ensino Superior Completo', 'Ensino Superior Completo'),
        ('Pós-graduação', 'Pós-graduação'),
        ('Mestrado', 'Mestrado'),
        ('Doutorado', 'Doutorado'),
        ('Pós-doutorado', 'Pós-doutorado')
    ], validators=[Optional()])

    possui_vinculo = BooleanField('Possui segundo vínculo?', default=False)
    quantidade_vinculos = IntegerField('Quantidade de vínculos', validators=[
                                       Optional(), NumberRange(min=1, max=5)])
    descricao_vinculo = StringField(
        'Descrição do vínculo', validators=[Optional()])
    horario_inicio = TimeField(
        'Horário de início do serviço', validators=[Optional()])
    horario_fim = TimeField(
        'Horário de término do serviço', validators=[Optional()])

    numero_emergencia = StringField(
        'Telefone de Emergência', validators=[DataRequired()])
    responsavel_emergencia = StringField(
        'Responsável pelo Número', validators=[DataRequired()])

    submit = SubmitField('Salvar Alterações')


class MatriculaConfirmForm(FlaskForm):
    matricula_completa = StringField(
        'Matrícula completa',
        validators=[DataRequired(message="Informe sua matrícula."), Length(min=3, max=50)]
    )
    submit = SubmitField('Confirmar')


class RecompensaAlunoForm(FlaskForm):
    natureza = StringField('Natureza', validators=[DataRequired()])
    autoridade = StringField('Autoridade', validators=[DataRequired()])
    boletim = StringField('Boletim', validators=[DataRequired()])
    discriminacao = TextAreaField('Discriminação', validators=[DataRequired()])
    botao_submit = SubmitField('Registrar Recompensa')


class SancaoAlunoForm(FlaskForm):
    natureza = StringField('Natureza', validators=[DataRequired()])
    numero_dias = IntegerField('Número de Dias', validators=[DataRequired()])
    boletim = StringField('Boletim', validators=[DataRequired()])
    data_inicio = DateField('Data de Início', validators=[DataRequired()])
    data_fim = DateField('Data de Término', validators=[DataRequired()])
    discriminacao = TextAreaField(
        'Discriminação/Medidas Aplicadas', validators=[DataRequired()])
    botao_submit = SubmitField('Registrar Sanção')


class VinculoExternoSubForm(FlaskForm):
    empregador_nome = StringField("Empregador", validators=[
                                  DataRequired(), Length(max=150)])
    empregador_tipo = SelectField(
        "Tipo do empregador", choices=EMPREGADOR_TIPO_CHOICES, validators=[DataRequired()])
    empregador_doc = StringField("CNPJ/CPF do empregador", validators=[
        DataRequired(),
        Regexp(r"^\d{11}$|^\d{14}$",
               message="Apenas dígitos (11=CPF, 14=CNPJ).")
    ])
    ltip = SelectField("Está de licença?", choices=[
            ('Sim', 'Sim'),
            ('Não', 'Não'),])
    natureza_vinculo = SelectField(
        "Natureza do vínculo", choices=NATUREZA_VINCULO_CHOICES, validators=[DataRequired()])
    cargo_funcao = StringField(
        "Cargo/Função", validators=[DataRequired(), Length(max=120)])
    carga_horaria_semanal = IntegerField("Carga horária semanal (h)", validators=[
                                         DataRequired(), NumberRange(min=1, max=80)])
    horario_inicio = TimeField("Horário início", validators=[DataRequired()])
    horario_fim = TimeField("Horário fim", validators=[DataRequired()])
    data_inicio = DateField("Data de início", validators=[DataRequired()])


class DeclaracaoAcumuloForm(FlaskForm):
    militar_id = HiddenField()  # chefe/diretor escolhe antes
    ano_referencia = IntegerField("Ano", render_kw={"readonly": True})

    militar_nome = StringField("Militar", render_kw={"readonly": True})
    militar_posto_grad = StringField(
        "Posto/Graduação", render_kw={"readonly": True})
    militar_obm = StringField("OBM", render_kw={"readonly": True})

    tipo = SelectField("Tipo de declaração",
                       choices=TIPO_DECLARACAO_CHOICES, validators=[DataRequired()])
    arquivo_declaracao = FileField(
        "Arquivo da declaração assinada (PDF/JPG/PNG)",
        validators=[FileRequired(), FileAllowed(
            ["pdf", "jpg", "jpeg", "png"], "Envie PDF ou imagem.")]
    )
    observacoes = TextAreaField("Observações (opcional)", validators=[
                                Optional(), Length(max=2000)])

    vinculos = FieldList(FormField(VinculoExternoSubForm), min_entries=1)


class DistribuirAtualizacaoForm(FlaskForm):
    limpeza = SelectField(
        'Limpeza antes de distribuir',
        choices=[
            ('nenhuma', 'Nenhuma (apenas acrescenta faltantes)'),
            ('pendentes', 'Remover pendentes/em edição e redistribuir'),
            ('todas', 'Apagar todas as tarefas e redistribuir do zero')
        ],
        default='nenhuma'
    )
    submit = SubmitField('Distribuir agora')
    