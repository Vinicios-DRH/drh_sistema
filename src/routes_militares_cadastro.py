
from flask import current_app
from flask_login import login_required
from flask import abort, request, jsonify, make_response, current_app
import os
import pytz
from src.decorators.utils_acumulo import b2_bucket_name, b2_client, b2_delete_all_versions, b2_upload_fileobj
from flask import render_template, redirect, url_for, request, flash, jsonify, make_response, \
    Response, stream_with_context
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from src import app, database, bcrypt
from src.forms import (FormMilitarInativo, FormMilitar, FormCriarUsuario)
from src.models import (DocumentoMilitar, Militar, MilitaresInativos, PostoGrad, Quadro, Obm, Localidade, Funcao, User, FuncaoUser, PublicacaoBg,
                        EstadoCivil, Especialidade, Destino, Motivo, Modalidade, Punicao, Comportamento, MilitarObmFuncao,
                        FuncaoGratificada,
                        MilitarGraduacao, MilitarContatoEmergencia, MilitarConjuge, Curso, MilitarCurso, AuditoriaAtualizacaoCadastral, now_manaus_naive)
from src.decorators.control import checar_ocupacao
from datetime import datetime, date, timedelta
from sqlalchemy import or_
from src.security.perms import has_perm
from src.authz import is_super_or_perm
from src.services.militar_situacao_service import (
    parse_date_flex,
    sincronizar_blocos_funcionais,
)

from src.routes_helpers import (
    somente_numeros,
    calcular_datas_servico,
    _to_manaus,
    _pode_pegar_doc,
)


@app.route("/criar-conta", methods=['GET', 'POST'])
@login_required
def criar_conta():
    if current_user.id != 1:
        abort(403)

    form_criar_usuario = FormCriarUsuario()

    choices = [(funcao_user.id, funcao_user.ocupacao)
               for funcao_user in FuncaoUser.query.all()]
    choices.insert(0, ('', '-- Selecione uma opção --'))

    form_criar_usuario.obm_id_1.choices = [('', '-- Selecione uma opção --')] + [
        (obm.id, obm.sigla) for obm in Obm.query.all()
    ]
    form_criar_usuario.obm_id_2.choices = [('', '-- Selecione uma opção --')] + [
        (obm.id, obm.sigla) for obm in Obm.query.all()
    ]
    form_criar_usuario.localidade_id.choices = [('', '-- Selecione uma opção --')] + [
        (localidade.id, localidade.sigla) for localidade in Localidade.query.all()
    ]
    form_criar_usuario.funcao_user_id.choices = choices

    if form_criar_usuario.validate_on_submit():
        cpf_limpo = somente_numeros(form_criar_usuario.cpf.data)

        militar = Militar.query.filter(
            or_(
                Militar.cpf == cpf_limpo,
                Militar.cpf == form_criar_usuario.cpf.data
            )
        ).first()

        usuario_existente = User.query.filter(
            or_(
                User.cpf == cpf_limpo,
                User.cpf == form_criar_usuario.cpf.data,
                User.cpf_norm == cpf_limpo
            )
        ).first()

        if usuario_existente:
            # Atualiza o usuário já existente
            usuario_existente.nome = form_criar_usuario.nome.data
            usuario_existente.email = form_criar_usuario.email.data
            usuario_existente.cpf = form_criar_usuario.cpf.data
            usuario_existente.cpf_norm = cpf_limpo
            usuario_existente.funcao_user_id = form_criar_usuario.funcao_user_id.data
            usuario_existente.obm_id_1 = form_criar_usuario.obm_id_1.data or None
            usuario_existente.obm_id_2 = form_criar_usuario.obm_id_2.data or None
            usuario_existente.localidade_id = form_criar_usuario.localidade_id.data or None

            if militar:
                usuario_existente.militar_id = militar.id
                militar.usuario_id = usuario_existente.id

            # só atualiza senha se tiver sido preenchida
            if form_criar_usuario.senha.data:
                senha_cript = bcrypt.generate_password_hash(
                    form_criar_usuario.senha.data
                ).decode('utf-8')
                usuario_existente.senha = senha_cript

            database.session.commit()
            flash("Usuário já existia. Dados atualizados com sucesso!",
                  "alert-warning")
            return redirect(url_for('home'))

        # cria novo usuário se não existir
        senha_cript = bcrypt.generate_password_hash(
            form_criar_usuario.senha.data
        ).decode('utf-8')

        novo_usuario = User(
            nome=form_criar_usuario.nome.data,
            email=form_criar_usuario.email.data,
            cpf=cpf_limpo,
            cpf_norm=cpf_limpo,
            funcao_user_id=form_criar_usuario.funcao_user_id.data,
            obm_id_1=form_criar_usuario.obm_id_1.data or None,
            obm_id_2=form_criar_usuario.obm_id_2.data or None,
            localidade_id=form_criar_usuario.localidade_id.data or None,
            senha=senha_cript,
            militar_id=militar.id if militar else None
        )

        database.session.add(novo_usuario)
        database.session.flush()

        if militar:
            militar.usuario_id = novo_usuario.id

        database.session.commit()
        flash("Usuário cadastrado com sucesso!", "alert-success")
        return redirect(url_for('home'))

    return render_template('criar_conta.html', form_criar_usuario=form_criar_usuario)


# @app.route("/adicionar-militar", methods=['GET', 'POST'])
# @login_required
# @checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH')
# def adicionar_militar():
#     form_militar = FormMilitar()

#     form_militar.funcao_gratificada_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(funcao_gratificada.id, funcao_gratificada.gratificacao) for
#          funcao_gratificada in FuncaoGratificada.query.all()]

#     form_militar.posto_grad_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(posto.id, posto.sigla) for posto in PostoGrad.query.all()]

#     form_militar.quadro_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(quadro.id, quadro.quadro) for quadro in Quadro.query.all()]

#     form_militar.localidade_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(localidade.id, localidade.sigla) for localidade in
#          Localidade.query.all()]

#     form_militar.obm_ids_1.choices = [
#         ('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
#                                               Obm.query.all()]

#     form_militar.funcao_ids_1.choices = [
#         ('', '-- Selecione uma opção --')] + [(funcao.id, funcao.ocupacao) for
#                                               funcao in Funcao.query.all()]

#     form_militar.obm_ids_2.choices = [
#         ('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
#                                               Obm.query.all()]

#     form_militar.funcao_ids_2.choices = [
#         ('', '-- Selecione uma opção --')] + [(funcao.id, funcao.ocupacao) for
#                                               funcao in Funcao.query.all()]

#     form_militar.modalidade_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(situacao.id, situacao.condicao) for situacao in Situacao.query.all()]

#     form_militar.estado_civil.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(estado.id, estado.estado) for estado in EstadoCivil.query.all()]

#     form_militar.especialidade_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(especialidade.id, especialidade.ocupacao) for especialidade in
#          Especialidade.query.all()]

#     form_militar.destino_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(destino.id, destino.local) for destino in Destino.query.all()]

#     form_militar.motivo_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(agregacoes.id, agregacoes.tipo) for agregacoes in Agregacoes.query.all()]

#     form_militar.punicao_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(punicao.id, punicao.sancao) for punicao in Punicao.query.all()]

#     form_militar.comportamento_id.choices = [
#         ('', '-- Selecione uma opção --')
#     ] + [(comportamento.id, comportamento.conduta) for comportamento in
#          Comportamento.query.all()]

#     if form_militar.validate_on_submit():

#         completa_25_inclusao = datetime.strptime(
#             form_militar.completa_25_inclusao.data, '%d/%m/%Y').date()
#         completa_30_inclusao = datetime.strptime(
#             form_militar.completa_30_inclusao.data, '%d/%m/%Y').date()
#         completa_25_anos_sv = datetime.strptime(
#             form_militar.completa_25_anos_sv.data, '%d/%m/%Y').date()
#         completa_30_anos_sv = datetime.strptime(
#             form_militar.completa_30_anos_sv.data, '%d/%m/%Y').date()

#         militar = Militar(
#             nome_completo=form_militar.nome_completo.data,
#             nome_guerra=form_militar.nome_guerra.data,
#             cpf=form_militar.cpf.data,
#             rg=form_militar.rg.data,
#             nome_pai=form_militar.nome_pai.data,
#             nome_mae=form_militar.nome_mae.data,
#             matricula=form_militar.matricula.data,
#             pis_pasep=form_militar.pis_pasep.data,
#             num_titulo_eleitor=form_militar.num_titulo_eleitor.data,
#             digito_titulo_eleitor=form_militar.digito_titulo_eleitor.data,
#             zona=form_militar.zona.data,
#             secao=form_militar.secao.data,
#             posto_grad_id=form_militar.posto_grad_id.data,
#             quadro_id=form_militar.quadro_id.data,
#             localidade_id=form_militar.localidade_id.data,
#             antiguidade=form_militar.antiguidade.data,
#             sexo=form_militar.sexo.data,
#             raca=form_militar.raca.data,
#             data_nascimento=form_militar.data_nascimento.data,
#             inclusao=form_militar.inclusao.data,
#             completa_25_inclusao=completa_25_inclusao,
#             completa_30_inclusao=completa_30_inclusao,
#             punicao_id=form_militar.punicao_id.data,
#             comportamento_id=form_militar.comportamento_id.data or None,
#             efetivo_servico=form_militar.efetivo_servico.data,
#             completa_25_anos_sv=completa_25_anos_sv,
#             completa_30_anos_sv=completa_30_anos_sv,
#             anos=form_militar.anos.data,
#             meses=form_militar.meses.data,
#             dias=form_militar.dias.data,
#             total_dias=form_militar.total_dias.data or None,
#             idade_reserva_grad=0,
#             estado_civil=form_militar.estado_civil.data,
#             especialidade_id=form_militar.especialidade_id.data,
#             pronto=form_militar.pronto.data,
#             modalidade_id=form_militar.modalidade_id.data or None,
#             motivo_id=form_militar.motivo_id.data or None,
#             destino_id=form_militar.destino_id.data or None,
#             inicio_periodo=form_militar.inicio_periodo.data,
#             fim_periodo=form_militar.fim_periodo.data,
#             ltip_afastamento_cargo_eletivo=form_militar.ltip_afastamento_cargo_eletivo.data,
#             periodo_ltip=form_militar.periodo_ltip.data,
#             total_ltip=form_militar.total_ltip.data,
#             completa_25_anos_ltip=form_militar.completa_25_anos_ltip.data,
#             completa_30_anos_ltip=form_militar.completa_30_anos_ltip.data,
#             cursos=form_militar.cursos.data,
#             grau_instrucao=form_militar.grau_instrucao.data,
#             graduacao=form_militar.graduacao.data,
#             pos_graduacao=form_militar.pos_graduacao.data,
#             mestrado=form_militar.mestrado.data,
#             doutorado=form_militar.doutorado.data,
#             cfsd=form_militar.cfsd.data,
#             cfc=form_militar.cfc.data,
#             cfs=form_militar.cfs.data,
#             cas=form_militar.cas.data,
#             choa=form_militar.choa.data,
#             cfo=form_militar.cfo.data,
#             cbo=form_militar.cbo.data,
#             cao=form_militar.cao.data,
#             csbm=form_militar.csbm.data,
#             cursos_civis=form_militar.cursos_civis.data,
#             endereco=form_militar.endereco.data,
#             complemento=form_militar.complemento.data,
#             cidade=form_militar.cidade.data,
#             estado=form_militar.estado.data,
#             cep=form_militar.cep.data,
#             celular=form_militar.celular.data,
#             email=form_militar.email.data,
#             inclusao_bg=form_militar.inclusao_bg.data,
#             soldado_tres=form_militar.soldado_tres.data,
#             soldado_dois=form_militar.soldado_dois.data,
#             soldado_um=form_militar.soldado_um.data,
#             cabo=form_militar.cabo.data,
#             terceiro_sgt=form_militar.terceiro_sgt.data,
#             segundo_sgt=form_militar.segundo_sgt.data,
#             primeiro_sgt=form_militar.primeiro_sgt.data,
#             subtenente=form_militar.subtenente.data,
#             segundo_tenente=form_militar.segundo_tenente.data,
#             primeiro_tenente=form_militar.primeiro_tenente.data,
#             cap=form_militar.cap.data,
#             maj=form_militar.maj.data,
#             tc=form_militar.tc.data,
#             cel=form_militar.cel.data,
#             funcao_gratificada_id=form_militar.funcao_gratificada_id.data,
#             alteracao_nome_guerra=form_militar.alteracao_nome_guerra.data,
#             inativo=False,
#             ip_address=get_user_ip(),
#             usuario_id=current_user.id
#         )
#         # arquivos = form_militar.arquivo.data

#         # # Se for um único arquivo, transforme-o em uma lista para uniformizar o processamento
#         # if not isinstance(arquivos, list):
#         #     arquivos = [arquivos]

#         # for arquivo in arquivos:
#         #     if isinstance(arquivo, str):
#         #         # Esse erro não deve acontecer se o upload foi feito corretamente, mas informe o usuário se ocorrer
#         #         print(f"Erro: Esperado um objeto FileStorage, mas obtido uma string: {arquivo}")
#         #     elif arquivo:  # Verifica se o arquivo não está vazio
#         #         nome_seguro = secure_filename(arquivo.filename)
#         #         caminho = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config["UPLOAD_FOLDER"],
#         #                                nome_seguro)
#         #         arquivo.save(caminho)  # Salva o arquivo no caminho especificado
#         #         print(f"Arquivo {nome_seguro} salvo com sucesso em {caminho}")
#         #     else:
#         #         print("Erro: O arquivo está vazio ou é inválido.")

#         database.session.add(militar)
#         database.session.commit()

#         # Adicionando as OBMs e Funções
#         obm_funcao_pairs = zip(request.form.getlist(
#             'obm_ids_1'), request.form.getlist('funcao_ids_1'))

#         # Itera sobre as combinações selecionadas de OBMs e funções
#         for obm_id, funcao_id in obm_funcao_pairs:
#             # Verifica se obm_id e funcao_id não estão vazios
#             if obm_id and funcao_id:
#                 militar_obm_funcao = MilitarObmFuncao(
#                     militar_id=militar.id,
#                     # Certifique-se de que o ID é um número inteiro
#                     obm_id=int(obm_id),
#                     tipo=1,
#                     # Certifique-se de que o ID é um número inteiro
#                     funcao_id=int(funcao_id)
#                 )
#                 database.session.add(militar_obm_funcao)

#         # Repetindo o processo para o segundo conjunto de OBMs e funções (caso exista)
#         obm_funcao_pairs_2 = zip(request.form.getlist(
#             'obm_ids_2'), request.form.getlist('funcao_ids_2'))

#         for obm_id_2, funcao_id_2 in obm_funcao_pairs_2:
#             if obm_id_2 and funcao_id_2:
#                 militar_obm_funcao = MilitarObmFuncao(
#                     militar_id=militar.id,
#                     # Certifique-se de que o ID é um número inteiro
#                     obm_id=int(obm_id_2),
#                     tipo=2,
#                     # Certifique-se de que o ID é um número inteiro
#                     funcao_id=int(funcao_id_2)
#                 )
#                 database.session.add(militar_obm_funcao)

#         database.session.commit()

#         # Salvando as publicações de BG
#         campos_bg = [
#             'transferencia', 'situacao_militar', 'cfsd', 'cfc', 'cfs', 'cas',
#             'choa', 'cfo', 'cbo', 'cao', 'csbm', 'soldado_tres',
#             'soldado_dois', 'soldado_um', 'cabo', 'terceiro_sgt',
#             'segundo_sgt', 'primeiro_sgt', 'subtenente',
#             'publicidade_segundo_tenente', 'publicidade_primeiro_tenente',
#             'pub_cap', 'pub_maj', 'pub_tc', 'pub_cel', 'pub_alteracao'
#         ]

#         for campo in campos_bg:
#             boletim_geral = getattr(form_militar, campo).data
#             if boletim_geral:
#                 publicacao_bg = PublicacaoBg(
#                     militar_id=militar.id,
#                     boletim_geral=boletim_geral,
#                     tipo_bg=campo
#                 )
#                 database.session.add(publicacao_bg)

#         # Verifica se a situação selecionada é "AGREGADO"
#         situacao_selecionada = Situacao.query.get(
#             form_militar.modalidade_id.data)
#         if situacao_selecionada and situacao_selecionada.condicao == 'AGREGADO':

#             # Verifica se há uma publicação BG associada ao militar e à situação
#             publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
#                                                                   tipo_bg='situacao_militar').first()

#             if publicacao_situacao_bg:
#                 # Criando o registro em 'militares_agregados'
#                 militar_agregado = MilitaresAgregados(
#                     militar_id=militar.id,
#                     posto_grad_id=form_militar.posto_grad_id.data,
#                     quadro_id=form_militar.quadro_id.data,
#                     destino_id=form_militar.destino_id.data,
#                     modalidade_id=situacao_selecionada.id,
#                     inicio_periodo=form_militar.inicio_periodo.data,
#                     fim_periodo_agregacao=form_militar.fim_periodo.data,
#                     publicacao_bg_id=publicacao_situacao_bg.id
#                 )

#                 # Atualizando a posição da agregação (vigente ou término)
#                 militar_agregado.atualizar_status()

#                 # Adiciona o registro de agregação e faz o commit no banco
#                 database.session.add(militar_agregado)
#                 database.session.commit()
#             else:
#                 # Caso não exista publicação BG associada, você pode decidir o que fazer
#                 print("Publicação BG não encontrada para o militar agregado.")

#         if situacao_selecionada and situacao_selecionada.condicao == 'À DISPOSIÇÃO':

#             # Verifica se há uma publicação BG associada ao militar e à situação
#             publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
#                                                                   tipo_bg='situacao_militar').first()

#             if publicacao_situacao_bg:
#                 # Criando o registro em 'militares_a_disposicao'
#                 militar_a_disposicao = MilitaresADisposicao(
#                     militar_id=militar.id,
#                     posto_grad_id=form_militar.posto_grad_id.data,
#                     quadro_id=form_militar.quadro_id.data,
#                     destino_id=form_militar.destino_id.data,
#                     modalidade_id=situacao_selecionada.id,
#                     inicio_periodo=form_militar.inicio_periodo.data,
#                     fim_periodo_disposicao=form_militar.fim_periodo.data,
#                     publicacao_bg_id=publicacao_situacao_bg.id
#                 )

#                 militar_a_disposicao.atualizar_status()

#                 # Adiciona o registro de agregação e faz o commit no banco
#                 database.session.add(militar_a_disposicao)
#                 database.session.commit()
#             else:
#                 flash(
#                     'Publicação BG não encontrada para o militar à disposição.', 'alert-danger')

#         if situacao_selecionada and situacao_selecionada.condicao == 'LICENÇA ESPECIAL':
#             publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
#                                                                   tipo_bg='situacao_militar').first()
#             if publicacao_situacao_bg:
#                 militar_le = LicencaEspecial(
#                     militar_id=militar.id,
#                     posto_grad_id=form_militar.posto_grad_id.data,
#                     quadro_id=form_militar.quadro_id.data,
#                     destino_id=form_militar.destino_id.data,
#                     modalidade_id=situacao_selecionada.id,
#                     inicio_periodo_le=form_militar.inicio_periodo.data,
#                     fim_periodo_le=form_militar.fim_periodo.data,
#                     publicacao_bg_id=publicacao_situacao_bg.id
#                 )

#                 militar_le.atualizar_status()

#                 database.session.add(militar_le)
#                 database.session.commit()
#             else:
#                 flash(
#                     'Publicação BG não encontrada para a Licença Especial.', 'alert-danger')

#         if situacao_selecionada and situacao_selecionada.condicao == 'LTS':
#             publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
#                                                                   tipo_bg='situacao_militar').first()
#             if publicacao_situacao_bg:
#                 militar_lts = LicencaParaTratamentoDeSaude(
#                     militar_id=militar.id,
#                     posto_grad_id=form_militar.posto_grad_id.data,
#                     quadro_id=form_militar.quadro_id.data,
#                     destino_id=form_militar.destino_id.data,
#                     modalidade_id=situacao_selecionada.id,
#                     inicio_periodo_lts=form_militar.inicio_periodo.data,
#                     fim_periodo_lts=form_militar.fim_periodo.data,
#                     publicacao_bg_id=publicacao_situacao_bg.id
#                 )

#                 militar_lts.atualizar_status()

#                 database.session.add(militar_lts)
#                 database.session.commit()
#             else:
#                 flash('Publicação BG não encontrada para LTS.', 'alert-danger')

#         database.session.commit()

#         flash('Militar adicionado com sucesso!', 'alert-success')
#         return redirect(url_for('home'))

#     return render_template('adicionar_militar.html', form_militar=form_militar)


@app.route("/adicionar-militar-inativo", methods=["GET", "POST"])
@login_required
def adicionar_militar_inativo():
    """Rota para adicionar um militar inativo."""
    form_militar = FormMilitarInativo()  # Usando a nova form específica

    form_militar.posto_grad_id.choices = [('', '-- Selecione uma opção --')] + [
        (posto.id, posto.sigla) for posto in PostoGrad.query.all()
    ]
    form_militar.quadro_id.choices = [('', '-- Selecione uma opção --')] + [
        (quadro.id, quadro.quadro) for quadro in Quadro.query.all()
    ]
    form_militar.estado_civil_id.choices = [('', '-- Selecione uma opção --')] + [
        (estado.id, estado.estado) for estado in EstadoCivil.query.all()
    ]

    form_militar.inativo.data = True

    if form_militar.validate_on_submit():
        novo = MilitaresInativos(
            nome_completo=form_militar.nome_completo.data,
            nome_guerra=form_militar.nome_guerra.data,
            estado_civil_id=form_militar.estado_civil_id.data,  # <== aqui a correção
            nome_pai=form_militar.nome_pai.data,
            nome_mae=form_militar.nome_mae.data,
            matricula=form_militar.matricula.data,
            rg=form_militar.rg.data,
            cpf=form_militar.cpf.data,
            pis_pasep=form_militar.pis_pasep.data,
            posto_grad_id=form_militar.posto_grad_id.data,
            quadro_id=form_militar.quadro_id.data,
            sexo=form_militar.sexo.data,
            data_nascimento=form_militar.data_nascimento.data,
            idade_atual=form_militar.idade_atual.data,
            endereco=form_militar.endereco.data,
            complemento=form_militar.complemento.data,
            cidade=form_militar.cidade.data,
            estado=form_militar.estado.data,
            cep=form_militar.cep.data,
            celular=form_militar.celular.data,
            email=form_militar.email.data,
            modalidade=form_militar.modalidade.data,
            doe=form_militar.doe.data,
            usuario_id=current_user.id,
            ip_address=request.remote_addr,
        )

        database.session.add(novo)
        database.session.commit()
        flash("Militar inativo adicionado com sucesso!", "success")
        return redirect(url_for("listar_militares_inativos"))

    return render_template("adicionar_militar_inativo.html", form_militar=form_militar)


@app.route("/militares-inativos")
@login_required
def listar_militares_inativos():
    hierarquia = {
        "CEL": 1,
        "TC": 2,
        "MAJ": 3,
        "CAP": 4,
        "1 TEN": 5,
        "2 TEN": 6,
        "ASP": 7,
        "SUBTENENTE": 8,
        "1 SGT": 9,
        "2 SGT": 10,
        "3 SGT": 11,
        "CB": 12,
        "SD": 13,
    }

    militares = MilitaresInativos.query.join(
        MilitaresInativos.posto_grad).all()

    # Ordenar pela hierarquia definida acima
    militares.sort(key=lambda m: hierarquia.get(
        m.posto_grad.sigla.strip(), 99))

    return render_template("listar_militares_inativos.html", militares=militares)


@app.route("/editar-militar-inativo/<int:id>", methods=["GET", "POST"])
@login_required
def editar_militar_inativo(id):
    militar = MilitaresInativos.query.get_or_404(id)

    form = FormMilitarInativo(obj=militar)

    # ⚠️ Preencha os choices antes de qualquer validação
    form.posto_grad_id.choices = [(p.id, p.sigla)
                                  for p in PostoGrad.query.all()]
    form.quadro_id.choices = [(q.id, q.quadro) for q in Quadro.query.all()]

    form.estado_civil_id.choices = [
        (0, '-- Selecione uma opção --')
    ] + [(estado.id, estado.estado) for estado in EstadoCivil.query.all()]

    if form.validate_on_submit():
        form.populate_obj(militar)
        database.session.commit()
        flash("Dados atualizados com sucesso!", "success")
        return redirect(url_for("listar_militares_inativos"))

    return render_template("adicionar_militar_inativo.html", form_militar=form)


@app.route('/verificar-arquivos', methods=['POST'])
@login_required
def verificar_arquivos():
    data = request.get_json()
    filenames = data.get('filenames', [])

    existing_files = []
    upload_folder = os.path.join(os.path.abspath(
        os.path.dirname(__file__)), app.config["UPLOAD_FOLDER"])

    for filename in filenames:
        file_path = os.path.join(upload_folder, secure_filename(filename))
        if os.path.exists(file_path):
            existing_files.append(filename)

    return jsonify({'exists': existing_files})


MODALIDADES_VALIDAS = {
    'AGUARDANDO',
    'À DISPOSIÇÃO',
    'LICENÇA ESPECIAL',
    'LICENÇA MATERNIDADE',
    'LTS',
    'ORDEM DE SERVIÇO',
    'PRONTO',
    'EM CURSO',
}


@app.route("/exibir-militar/<int:militar_id>", methods=["GET", "POST"])
@login_required
@checar_ocupacao("DRH", "MAPA DA FORÇA", "SUPER USER", "DIRETOR DRH", "ATUALIZACAO CADASTRAL")
def exibir_militar(militar_id):
    if not is_super_or_perm("MILITAR_READ"):
        abort(403)

    if request.method == "GET":
        if not has_perm("MILITAR_READ"):
            abort(403)
    else:
        if not has_perm("MILITAR_UPDATE"):
            abort(403)

    militar = Militar.query.get_or_404(militar_id)
    database.session.expire_all()

    graduacoes = (
        MilitarGraduacao.query
        .filter_by(militar_id=militar.id)
        .order_by(MilitarGraduacao.id.asc())
        .all()
    )

    contatos_emergencia = (
        MilitarContatoEmergencia.query
        .filter_by(militar_id=militar.id)
        .order_by(MilitarContatoEmergencia.id.asc())
        .all()
    )

    conjuge = MilitarConjuge.query.filter_by(militar_id=militar.id).first()

    obm_funcao_tipo_1 = (
        MilitarObmFuncao.query
        .filter_by(militar_id=militar_id, tipo=1)
        .filter(MilitarObmFuncao.data_fim.is_(None))
        .first()
    )

    obm_funcao_tipo_2 = (
        MilitarObmFuncao.query
        .filter_by(militar_id=militar_id, tipo=2)
        .filter(MilitarObmFuncao.data_fim.is_(None))
        .first()
    )

    form_militar = FormMilitar(obj=militar)

    # =========================================================================
    # 1. DEFINIÇÃO DE CHOICES (FORA DO GET PARA O POST PODER VALIDAR)
    # =========================================================================
    form_militar.funcao_gratificada_id.choices = [
        (fg.id, fg.gratificacao) for fg in FuncaoGratificada.query.all()]
    form_militar.posto_grad_id.choices = [
        (posto.id, posto.sigla) for posto in PostoGrad.query.all()]
    form_militar.quadro_id.choices = [
        (quadro.id, quadro.quadro) for quadro in Quadro.query.all()]
    form_militar.localidade_id.choices = [
        (loc.id, loc.sigla) for loc in Localidade.query.all()]

    form_militar.obm_ids_1.choices = [
        ("", "-- Selecione uma opção --")] + [(obm.id, obm.sigla) for obm in Obm.query.all()]
    form_militar.funcao_ids_1.choices = [("", "-- Selecione uma opção --")] + [
        (funcao.id, funcao.ocupacao) for funcao in Funcao.query.all()]
    form_militar.obm_ids_2.choices = [
        ("", "-- Selecione uma opção --")] + [(obm.id, obm.sigla) for obm in Obm.query.all()]
    form_militar.funcao_ids_2.choices = [("", "-- Selecione uma opção --")] + [
        (funcao.id, funcao.ocupacao) for funcao in Funcao.query.all()]

    modalidades = Modalidade.query.filter(Modalidade.descricao.in_(
        MODALIDADES_VALIDAS)).order_by(Modalidade.descricao.asc()).all()
    form_militar.modalidade_id.choices = [
        ("", "-- Selecione --")] + [(m.id, m.descricao) for m in modalidades]

    form_militar.estado_civil.choices = [
        (estado.id, estado.estado) for estado in EstadoCivil.query.all()]
    form_militar.especialidade_id.choices = [
        (esp.id, esp.ocupacao) for esp in Especialidade.query.all()]
    form_militar.destino_id.choices = [
        ("", "-- Selecione uma opção --")] + [(dest.id, dest.local) for dest in Destino.query.all()]

    motivos = Motivo.query.order_by(Motivo.descricao.asc()).all()
    form_militar.motivo_id.choices = [
        ("", "-- Selecione --")] + [(m.id, m.descricao) for m in motivos]

    form_militar.punicao_id.choices = [
        (punicao.id, punicao.sancao) for punicao in Punicao.query.all()]
    form_militar.comportamento_id.choices = [("", "-- Selecione uma opção --")] + [
        (comp.id, comp.conduta) for comp in Comportamento.query.all()]

    form_militar.cursos_ids.choices = [
        (curso.id, curso.nome) for curso in Curso.query.order_by(Curso.nome.asc()).all()
    ]
    campos_bg = [
        "transferencia", "situacao_militar", "cfsd", "cfc", "cfs", "cas",
        "choa", "cfo", "cbo", "cao", "csbm", "soldado_tres",
        "soldado_dois", "soldado_um", "cabo", "terceiro_sgt",
        "segundo_sgt", "primeiro_sgt", "subtenente",
        "publicidade_segundo_tenente", "publicidade_primeiro_tenente",
        "pub_cap", "pub_maj", "pub_tc", "pub_cel", "pub_alteracao",
        "situacao_militar_2",
    ]

    # Variável auxiliar para o template não quebrar no Jinja
    bg_sit2_val = ""

    # =========================================================================
    # 2. PREENCHIMENTO DE DADOS PARA EXIBIÇÃO (APENAS GET)
    # =========================================================================
    if request.method == "GET":
        if militar.completa_25_inclusao:
            form_militar.completa_25_inclusao.data = militar.completa_25_inclusao.strftime(
                "%d/%m/%Y")
        if militar.completa_30_inclusao:
            form_militar.completa_30_inclusao.data = militar.completa_30_inclusao.strftime(
                "%d/%m/%Y")
            
        calculo_servico = calcular_datas_servico(militar.efetivo_servico)

        form_militar.completa_25_anos_sv.data = (
            calculo_servico["completa_25_anos_sv"].strftime("%d/%m/%Y")
            if calculo_servico["completa_25_anos_sv"] else ""
        )

        form_militar.completa_30_anos_sv.data = (
            calculo_servico["completa_30_anos_sv"].strftime("%d/%m/%Y")
            if calculo_servico["completa_30_anos_sv"] else ""
        )

        form_militar.anos.data = calculo_servico["anos"]
        form_militar.meses.data = calculo_servico["meses"]
        form_militar.dias.data = calculo_servico["dias"]
        form_militar.total_dias.data = calculo_servico["total_dias"]

        if obm_funcao_tipo_1:
            form_militar.obm_ids_1.data = obm_funcao_tipo_1.obm_id
            form_militar.funcao_ids_1.data = obm_funcao_tipo_1.funcao_id

        if obm_funcao_tipo_2:
            form_militar.obm_ids_2.data = obm_funcao_tipo_2.obm_id
            form_militar.funcao_ids_2.data = obm_funcao_tipo_2.funcao_id

        form_militar.sexo.data = militar.sexo if militar.sexo else None
        form_militar.raca.data = militar.raca if militar.raca else None
        form_militar.cursos_ids.data = [
            mc.curso_id for mc in militar.cursos_especializacao]

        hoje = date.today()
        dn = militar.data_nascimento.date() if isinstance(
            militar.data_nascimento, datetime) else militar.data_nascimento
        if dn:
            idade = hoje.year - dn.year - \
                ((hoje.month, hoje.day) < (dn.month, dn.day))
        else:
            idade = None
        form_militar.idade_atual.data = idade

        publicacoes_bg = PublicacaoBg.query.filter_by(
            militar_id=militar.id).all()

        for campo in campos_bg:
            if hasattr(form_militar, campo):
                getattr(form_militar, campo).data = ""

        for pub in publicacoes_bg:
            if pub.tipo_bg in campos_bg and hasattr(form_militar, pub.tipo_bg):
                getattr(form_militar, pub.tipo_bg).data = pub.boletim_geral or ""

        bg_sit2_ultima = (
            PublicacaoBg.query
            .filter_by(militar_id=militar.id, tipo_bg="situacao_militar_2")
            .order_by(PublicacaoBg.id.desc())
            .first()
        )

        bg_sit2_val = bg_sit2_ultima.boletim_geral if bg_sit2_ultima else ""
        if hasattr(form_militar, "situacao_militar_2"):
            form_militar.situacao_militar_2.data = bg_sit2_val

        form_militar.situacao.data = militar.situacao or None
        form_militar.modalidade_id.data = militar.modalidade_id or None
        form_militar.motivo_id.data = militar.motivo_id or None
        form_militar.destino_id.data = militar.destino_id or None

    can_edit = has_perm("MILITAR_UPDATE")
    can_delete = has_perm("MILITAR_DELETE")

    # =========================================================================
    # 3. SALVAMENTO DOS DADOS (POST E VALIDAÇÃO)
    # =========================================================================
    if form_militar.validate_on_submit():

        militar.nome_completo = form_militar.nome_completo.data
        militar.nome_guerra = form_militar.nome_guerra.data
        militar.cpf = form_militar.cpf.data
        militar.rg = form_militar.rg.data
        militar.nome_pai = form_militar.nome_pai.data
        militar.nome_mae = form_militar.nome_mae.data
        militar.matricula = form_militar.matricula.data
        militar.pis_pasep = form_militar.pis_pasep.data
        militar.num_titulo_eleitor = form_militar.num_titulo_eleitor.data
        militar.digito_titulo_eleitor = form_militar.digito_titulo_eleitor.data
        militar.zona = form_militar.zona.data
        militar.secao = form_militar.secao.data
        militar.posto_grad_id = form_militar.posto_grad_id.data
        militar.quadro_id = form_militar.quadro_id.data
        militar.localidade_id = form_militar.localidade_id.data
        militar.antiguidade = form_militar.antiguidade.data
        militar.sexo = form_militar.sexo.data
        militar.raca = form_militar.raca.data
        militar.data_nascimento = form_militar.data_nascimento.data
        militar.inclusao = form_militar.inclusao.data

        militar.completa_25_inclusao = (
            datetime.strptime(
                str(form_militar.completa_25_inclusao.data), "%d/%m/%Y").date()
            if form_militar.completa_25_inclusao.data else None
        )
        militar.completa_30_inclusao = (
            datetime.strptime(
                str(form_militar.completa_30_inclusao.data), "%d/%m/%Y").date()
            if form_militar.completa_30_inclusao.data else None
        )

        militar.punicao_id = form_militar.punicao_id.data
        militar.comportamento_id = form_militar.comportamento_id.data
        militar.efetivo_servico = form_militar.efetivo_servico.data

        calculo_servico = calcular_datas_servico(militar.efetivo_servico)

        militar.completa_25_anos_sv = calculo_servico["completa_25_anos_sv"]
        militar.completa_30_anos_sv = calculo_servico["completa_30_anos_sv"]
        militar.anos = calculo_servico["anos"]
        militar.meses = calculo_servico["meses"]
        militar.dias = calculo_servico["dias"]
        militar.total_dias = calculo_servico["total_dias"]

        militar.idade_reserva_grad = 0
        militar.estado_civil = form_militar.estado_civil.data
        militar.especialidade_id = form_militar.especialidade_id.data

        # --- DADOS DE SITUAÇÃO PRINCIPAIS ---
        militar.situacao = form_militar.situacao.data or None
        militar.modalidade_id = int(
            form_militar.modalidade_id.data) if form_militar.modalidade_id.data not in ("", None) else None
        militar.motivo_id = int(
            form_militar.motivo_id.data) if form_militar.motivo_id.data not in ("", None) else None
        militar.destino_id = int(
            form_militar.destino_id.data) if form_militar.destino_id.data not in ("", None) else None
        militar.inicio_periodo = parse_date_flex(
            form_militar.inicio_periodo.data)
        militar.fim_periodo = parse_date_flex(form_militar.fim_periodo.data)

        # --- DADOS MANUAIS DA SITUAÇÃO EXTRA (CAPTURADOS DO REQUEST.FORM) ---
        situacao2_id_req = request.form.get("situacao2_id")
        militar.situacao2_id = int(
            situacao2_id_req) if situacao2_id_req else None

        agregacoes2_id_req = request.form.get("agregacoes2_id")
        militar.agregacoes2_id = int(
            agregacoes2_id_req) if agregacoes2_id_req else None

        militar.inicio_situacao2 = parse_date_flex(
            request.form.get("inicio_situacao2"))
        militar.fim_situacao2 = parse_date_flex(
            request.form.get("fim_situacao2"))

        # Capturando a publicação da Situação 2 manualmente também
        bg_sit2_input = request.form.get("situacao_militar_2")
        if bg_sit2_input is not None:
            bg_existente_sit2 = PublicacaoBg.query.filter_by(
                militar_id=militar.id, tipo_bg="situacao_militar_2").first()
            if bg_sit2_input.strip():
                if bg_existente_sit2:
                    bg_existente_sit2.boletim_geral = bg_sit2_input.strip()
                else:
                    database.session.add(PublicacaoBg(
                        militar_id=militar.id, tipo_bg="situacao_militar_2", boletim_geral=bg_sit2_input.strip()))
            elif bg_existente_sit2:
                # Se o usuário apagou o campo, podemos querer limpar a publicação
                database.session.delete(bg_existente_sit2)

        # --- DEMAIS CAMPOS ---
        militar.ltip_afastamento_cargo_eletivo = form_militar.ltip_afastamento_cargo_eletivo.data
        militar.periodo_ltip = form_militar.periodo_ltip.data
        militar.total_ltip = form_militar.total_ltip.data
        militar.completa_25_anos_ltip = form_militar.completa_25_anos_ltip.data
        militar.completa_30_anos_ltip = form_militar.completa_30_anos_ltip.data
        militar.cursos = form_militar.cursos.data
        militar.grau_instrucao = form_militar.grau_instrucao.data
        militar.graduacao = form_militar.graduacao.data
        militar.pos_graduacao = form_militar.pos_graduacao.data
        militar.mestrado = form_militar.mestrado.data
        militar.doutorado = form_militar.doutorado.data
        militar.cfsd = form_militar.cfsd.data
        militar.cfc = form_militar.cfc.data
        militar.cfs = form_militar.cfs.data
        militar.cas = form_militar.cas.data
        militar.choa = form_militar.choa.data
        militar.cfo = form_militar.cfo.data
        militar.cbo = form_militar.cbo.data
        militar.cao = form_militar.cao.data
        militar.csbm = form_militar.csbm.data
        militar.cursos_civis = form_militar.cursos_civis.data
        militar.endereco = form_militar.endereco.data
        militar.complemento = form_militar.complemento.data
        militar.cidade = form_militar.cidade.data
        militar.estado = form_militar.estado.data
        militar.cep = form_militar.cep.data
        militar.celular = form_militar.celular.data
        militar.email = form_militar.email.data

        militar.local_nascimento = form_militar.local_nascimento.data
        militar.altura = form_militar.altura.data
        militar.cor_olhos = form_militar.cor_olhos.data
        militar.cor_cabelos = form_militar.cor_cabelos.data
        militar.bigode = bool(form_militar.bigode.data)
        militar.medida_cabeca = form_militar.medida_cabeca.data
        militar.numero_sapato = form_militar.numero_sapato.data
        militar.medida_calca = form_militar.medida_calca.data
        militar.medida_camisa = form_militar.medida_camisa.data
        militar.tipo_sanguineo = form_militar.tipo_sanguineo.data
        militar.sinais_particulares = form_militar.sinais_particulares.data
        militar.tatuagem = bool(form_militar.tatuagem.data)
        militar.local_tatuagem = form_militar.local_tatuagem.data if form_militar.tatuagem.data else None

        militar.inclusao_bg = form_militar.inclusao_bg.data
        militar.soldado_tres = form_militar.soldado_tres.data
        militar.soldado_dois = form_militar.soldado_dois.data
        militar.soldado_um = form_militar.soldado_um.data
        militar.cabo = form_militar.cabo.data
        militar.terceiro_sgt = form_militar.terceiro_sgt.data
        militar.segundo_sgt = form_militar.segundo_sgt.data
        militar.primeiro_sgt = form_militar.primeiro_sgt.data
        militar.subtenente = form_militar.subtenente.data
        militar.segundo_tenente = form_militar.segundo_tenente.data
        militar.primeiro_tenente = form_militar.primeiro_tenente.data
        militar.cap = form_militar.cap.data
        militar.maj = form_militar.maj.data
        militar.tc = form_militar.tc.data
        militar.cel = form_militar.cel.data
        militar.funcao_gratificada_id = form_militar.funcao_gratificada_id.data
        militar.alteracao_nome_guerra = form_militar.alteracao_nome_guerra.data

        # --- GRADUAÇÕES ---
        graduacoes_curso = request.form.getlist("graduacoes_curso[]")
        graduacoes_instituicao = request.form.getlist(
            "graduacoes_instituicao[]")
        graduacoes_ano = request.form.getlist("graduacoes_ano[]")

        # --- LÓGICA DE SALVAMENTO DOS CURSOS (MANY-TO-MANY) ---
        cursos_selecionados = form_militar.cursos_ids.data or []

        # Mapeia os cursos que o militar JÁ possui no banco
        cursos_atuais = {
            mc.curso_id: mc for mc in militar.cursos_especializacao}

        # 1. Adiciona os cursos novos que foram marcados
        for curso_id in cursos_selecionados:
            if curso_id not in cursos_atuais:
                novo_curso = MilitarCurso(
                    militar_id=militar.id, curso_id=curso_id, criado_em=now_manaus_naive())
                database.session.add(novo_curso)

        # 2. Remove os cursos que foram desmarcados pelo operador
        for curso_id, mc in cursos_atuais.items():
            if curso_id not in cursos_selecionados:
                database.session.delete(mc)

        MilitarGraduacao.query.filter_by(militar_id=militar.id).delete()

        for i, curso in enumerate(graduacoes_curso):
            curso = (curso or "").strip()
            if not curso:
                continue

            instituicao = (graduacoes_instituicao[i] or "").strip(
            ) if i < len(graduacoes_instituicao) else ""
            ano_raw = (graduacoes_ano[i] or "").strip(
            ) if i < len(graduacoes_ano) else ""

            database.session.add(MilitarGraduacao(
                militar_id=militar.id,
                curso=curso,
                instituicao=instituicao or None,
                ano_conclusao=int(ano_raw) if ano_raw.isdigit() else None,
                criado_em=now_manaus_naive()
            ))

        # --- CONTATOS DE EMERGÊNCIA ---
        contato_nome = request.form.getlist("contato_nome[]")
        contato_parentesco = request.form.getlist("contato_parentesco[]")
        contato_telefone = request.form.getlist("contato_telefone[]")
        contato_telefone_secundario = request.form.getlist(
            "contato_telefone_secundario[]")
        contato_observacao = request.form.getlist("contato_observacao[]")

        MilitarContatoEmergencia.query.filter_by(
            militar_id=militar.id).delete()

        for i, nome in enumerate(contato_nome):
            nome = (nome or "").strip()
            telefone = (contato_telefone[i] or "").strip(
            ) if i < len(contato_telefone) else ""

            if not nome or not telefone:
                continue

            database.session.add(MilitarContatoEmergencia(
                militar_id=militar.id,
                nome=nome,
                parentesco=(contato_parentesco[i] or "").strip(
                ) if i < len(contato_parentesco) else None,
                telefone=telefone,
                telefone_secundario=(contato_telefone_secundario[i] or "").strip(
                ) if i < len(contato_telefone_secundario) else None,
                observacao=(contato_observacao[i] or "").strip(
                ) if i < len(contato_observacao) else None,
                criado_em=now_manaus_naive()
            ))

        # --- CÔNJUGE ---
        def normalizar_txt(txt):
            import unicodedata
            txt = (txt or "").strip().upper()
            txt = unicodedata.normalize("NFKD", txt).encode(
                "ASCII", "ignore").decode("ASCII")
            return " ".join(txt.split())

        estado_civil_obj = EstadoCivil.query.get(
            militar.estado_civil) if militar.estado_civil else None
        estado_nome = normalizar_txt(
            estado_civil_obj.estado if estado_civil_obj else "")

        exige_conjuge = (
            "CASAD" in estado_nome or "UNIAO ESTAVEL" in estado_nome)

        conjuge_nome = (request.form.get("conjuge_nome") or "").strip()
        conjuge_cpf = (request.form.get("conjuge_cpf") or "").strip()
        conjuge_telefone = (request.form.get("conjuge_telefone") or "").strip()
        conjuge_data_nascimento = (request.form.get(
            "conjuge_data_nascimento") or "").strip()
        conjuge_endereco = (request.form.get("conjuge_endereco") or "").strip()
        conjuge_observacao = (request.form.get(
            "conjuge_observacao") or "").strip()

        conjuge_db = MilitarConjuge.query.filter_by(
            militar_id=militar.id).first()

        tem_dado_conjuge = any([
            conjuge_nome, conjuge_cpf, conjuge_telefone,
            conjuge_data_nascimento, conjuge_endereco, conjuge_observacao,
        ])

        if exige_conjuge and tem_dado_conjuge:
            if not conjuge_db:
                conjuge_db = MilitarConjuge(
                    militar_id=militar.id, criado_em=now_manaus_naive())
                database.session.add(conjuge_db)

            conjuge_db.nome = conjuge_nome or "-"
            conjuge_db.cpf = conjuge_cpf or None
            conjuge_db.telefone = conjuge_telefone or None
            conjuge_db.data_nascimento = parse_date_flex(
                conjuge_data_nascimento)
            conjuge_db.endereco = conjuge_endereco or None
            conjuge_db.observacao = conjuge_observacao or None
        else:
            if conjuge_db:
                database.session.delete(conjuge_db)

        # --- OBM & FUNÇÃO ---
        obm_1 = form_militar.obm_ids_1.data
        funcao_1 = form_militar.funcao_ids_1.data
        obm_2 = form_militar.obm_ids_2.data
        funcao_2 = form_militar.funcao_ids_2.data

        registros_ativos = (
            MilitarObmFuncao.query
            .filter_by(militar_id=militar.id)
            .filter(MilitarObmFuncao.data_fim.is_(None))
            .all()
        )

        for registro in registros_ativos:
            if registro.tipo == 1:
                if not obm_1 or not funcao_1:
                    registro.data_fim = now_manaus_naive()
                elif registro.obm_id != obm_1 or registro.funcao_id != funcao_1:
                    registro.data_fim = now_manaus_naive()

            elif registro.tipo == 2:
                if not obm_2 or not funcao_2:
                    registro.data_fim = now_manaus_naive()
                elif registro.obm_id != obm_2 or registro.funcao_id != funcao_2:
                    registro.data_fim = now_manaus_naive()

        registro_tipo_1 = MilitarObmFuncao.query.filter_by(
            militar_id=militar.id, tipo=1).filter(MilitarObmFuncao.data_fim.is_(None)).first()
        if obm_1 and funcao_1 and not registro_tipo_1:
            database.session.add(MilitarObmFuncao(
                militar_id=militar.id, obm_id=obm_1, funcao_id=funcao_1, tipo=1, data_criacao=now_manaus_naive()
            ))

        registro_tipo_2 = MilitarObmFuncao.query.filter_by(
            militar_id=militar.id, tipo=2).filter(MilitarObmFuncao.data_fim.is_(None)).first()
        if obm_2 and funcao_2 and not registro_tipo_2:
            database.session.add(MilitarObmFuncao(
                militar_id=militar.id, obm_id=obm_2, funcao_id=funcao_2, tipo=2, data_criacao=now_manaus_naive()
            ))

        # --- PUBLICAÇÕES BG (WTFORMS) ---
        for campo in campos_bg:
            if campo == "situacao_militar_2":
                continue  # Já lidamos com isso manualmente mais acima

            if not hasattr(form_militar, campo):
                continue

            valor = getattr(form_militar, campo).data
            bg_existente = PublicacaoBg.query.filter_by(
                militar_id=militar.id, tipo_bg=campo).first()

            if valor:
                if bg_existente:
                    bg_existente.boletim_geral = valor
                else:
                    database.session.add(PublicacaoBg(
                        militar_id=militar.id, tipo_bg=campo, boletim_geral=valor))

        # --- FINALIZAÇÃO ---
        sincronizar_blocos_funcionais(militar, form_militar)

        try:
            database.session.commit()
            flash("Militar atualizado com sucesso!", "success")
            return redirect(url_for("militares"))
        except Exception as e:
            database.session.rollback()
            current_app.logger.exception("Erro ao atualizar militar")
            flash(f"Erro ao atualizar militar: {str(e)}", "danger")

    # =========================================================================
    # 4. CAPTURADOR DE ERROS SILENCIOSOS
    # =========================================================================
    elif request.method == "POST":
        for field, errors in form_militar.errors.items():
            for error in errors:
                label = getattr(form_militar, field).label.text if hasattr(
                    getattr(form_militar, field), 'label') else field
                flash(f"Erro no campo {label}: {error}", "danger")

    # =========================================================================
    # 5. AUDITORIA DA CHEFIA (Busca quem alterou a Situação pela última vez)
    # =========================================================================

    # --- DEBUG: Verifique o que tem na tabela ---
    todas_auditorias = AuditoriaAtualizacaoCadastral.query.filter_by(
        militar_id=militar.id).all()
    for a in todas_auditorias:
        print(f"DEBUG: ID={a.id}, ACAO='{a.acao}', MILITAR_ID={a.militar_id}")

    ultima_auditoria = AuditoriaAtualizacaoCadastral.query.filter_by(
        militar_id=militar.id,
        acao="ATUALIZACAO_SITUACAO_CHEFIA"
    ).order_by(AuditoriaAtualizacaoCadastral.id.desc()).first()

    auditoria_info = None
    if ultima_auditoria:
        data_aud = getattr(ultima_auditoria, 'criado_em', None) or getattr(
            ultima_auditoria, 'data_hora', None) or getattr(ultima_auditoria, 'data_criacao', None)
        data_str = data_aud.strftime(
            '%d/%m/%Y às %H:%M') if data_aud else "Data desconhecida"

        user_rel = getattr(ultima_auditoria, 'usuario', None) or getattr(
            ultima_auditoria, 'user', None)
        nome_str = "Usuário não identificado"
        if user_rel:
            nome_str = getattr(user_rel, 'nome_guerra', None) or getattr(
                user_rel, 'username', None) or getattr(user_rel, 'nome', "Usuário")

        auditoria_info = f"Modificado por {nome_str} em {data_str}"

    return render_template(
        "exibir_militar.html",
        form_militar=form_militar,
        militar=militar,
        graduacoes=graduacoes,
        contatos_emergencia=contatos_emergencia,
        conjuge=conjuge,
        can_edit=can_edit,
        can_delete=can_delete,
        bg_sit2_val=bg_sit2_val if request.method == "GET" else request.form.get(
            "situacao_militar_2", ""),
        auditoria_info=auditoria_info  # <--- NOVA LINHA AQUI
    )


@app.route('/inativar-militar/<int:militar_id>', methods=['POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER', 'DRH')
def inativar_militar(militar_id):
    militar = Militar.query.get_or_404(militar_id)

    if militar.inativo:
        flash('Este militar já está inativo.', 'alert-warning')
        return redirect(url_for('exibir_militar', militar_id=militar_id))

    militar.inativo = True

    # (Opcional, mas recomendado) Encerrar vínculos ativos de OBM/Função
    ativos = MilitarObmFuncao.query.filter_by(
        militar_id=militar_id, data_fim=None).all()
    for rel in ativos:
        rel.data_fim = datetime.now()

    # (Opcional) guardar trilha de auditoria, se tiver colunas (ver seção 3)
    militar.inativado_em = datetime.utcnow()
    militar.inativado_por_id = current_user.id
    militar.motivo_inativacao = request.form.get('motivo_inativacao') or None

    try:
        database.session.commit()
        flash('Militar inativado com sucesso.', 'alert-success')
    except Exception as e:
        database.session.rollback()
        flash(f'Erro ao inativar: {e}', 'alert-danger')

    return redirect(url_for('militares'))


@app.post("/exibir-militar/<int:militar_id>/enviar-doc")
@login_required
@checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH')
def enviar_documento_militar(militar_id):
    current_app.logger.info(
        ">>> POST enviar_documento_militar para id=%s", militar_id)

    militar = Militar.query.get_or_404(militar_id)
    file = request.files.get("doc_para_militar")

    if not file or not (file.filename or "").strip():
        flash("Selecione um arquivo.", "alert-warning")
        return redirect(url_for('exibir_militar', militar_id=militar_id))

    # calcula tamanho em bytes sem consumir o stream
    try:
        pos = file.stream.tell()
    except Exception:
        pos = 0
    try:
        file.stream.seek(0, 2)  # fim
        tamanho_bytes = file.stream.tell()
    finally:
        file.stream.seek(pos, 0)  # volta

    # sobe para o B2 (guarda só a key)
    try:
        # fica dentro de 'acumulo/'
        prefix = f"acumulo/{datetime.utcnow().year}/{militar.id}/docs"
        key = b2_upload_fileobj(file, key_prefix=prefix)
    except Exception as e:
        current_app.logger.exception("Falha ao subir doc no B2")
        flash(f"Erro ao enviar arquivo: {e}", "alert-danger")
        return redirect(url_for('exibir_militar', militar_id=militar_id))

    obs = (request.form.get("obs_para_militar") or "").strip() or None

    doc = DocumentoMilitar(
        militar_id=militar.id,
        destinatario_cpf=militar.cpf,
        nome_original=file.filename,
        content_type=file.mimetype or "application/octet-stream",
        tamanho_bytes=tamanho_bytes,
        object_key=key,
        criado_por_user_id=current_user.id,
        observacao=obs
    )

    try:
        database.session.add(doc)
        database.session.commit()
    except Exception as e:
        database.session.rollback()
        current_app.logger.exception("Falha ao gravar DocumentoMilitar")
        flash(f"Erro ao salvar no banco: {e}", "alert-danger")
        return redirect(url_for('exibir_militar', militar_id=militar_id))

    flash("Documento disponibilizado para o militar.", "alert-success")
    return redirect(url_for('exibir_militar', militar_id=militar_id))


@app.post("/documentos/<int:doc_id>/revogar")
@login_required
@checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH')
def revogar_documento_militar(doc_id):
    doc = DocumentoMilitar.query.get_or_404(doc_id)
    if doc.baixado_em:
        flash("Documento já foi baixado; não é possível revogar.", "alert-warning")
        return redirect(url_for('exibir_militar', militar_id=doc.militar_id))

    try:
        b2_delete_all_versions(doc.object_key)
    except Exception:
        current_app.logger.exception("Falha ao remover do B2 (revogar)")

    database.session.delete(doc)
    database.session.commit()
    flash("Documento revogado e removido do Backblaze.", "alert-success")
    return redirect(url_for('exibir_militar', militar_id=doc.militar_id))


TZ_MANAUS = pytz.timezone('America/Manaus')


@app.get("/meus-documentos")
@login_required
def meus_documentos():
    pendentes = (DocumentoMilitar.query
                 .filter_by(destinatario_cpf=current_user.cpf)
                 .filter(DocumentoMilitar.baixado_em.is_(None))
                 .order_by(DocumentoMilitar.criado_em.desc())
                 .all())

    baixados = (DocumentoMilitar.query
                .filter_by(destinatario_cpf=current_user.cpf)
                .filter(DocumentoMilitar.baixado_em.isnot(None))
                .order_by(DocumentoMilitar.baixado_em.desc())
                .limit(50)
                .all())

    # primeira visita
    show_intro = (request.cookies.get("meus_docs_intro_seen") != "1")

    NOVO_LIMITE_DIAS = 3
    now_mao = datetime.now(TZ_MANAUS)
    novo_limite = now_mao - timedelta(days=NOVO_LIMITE_DIAS)

    # marca cada doc como "novo" (conversão robusta para Manaus)
    for d in [*pendentes, *baixados]:
        criado_local = _to_manaus(d.criado_em)
        d.is_new = bool(criado_local and criado_local >= novo_limite)

    resp = make_response(render_template(
        "meus_documentos.html",
        pendentes=pendentes,
        baixados=baixados,
        show_intro=show_intro,
        novo_limite_dias=NOVO_LIMITE_DIAS,  # só para tooltip/texto, se quiser
    ))
    if show_intro:
        resp.set_cookie("meus_docs_intro_seen", "1",
                        max_age=60*60*24*365, httponly=False, samesite="Lax")
    return resp


@app.get("/documentos/<int:doc_id>/download")
@login_required
def download_documento(doc_id):
    doc = DocumentoMilitar.query.get_or_404(doc_id)
    if not _pode_pegar_doc(doc):
        abort(403)
    if doc.baixado_em:
        flash("Este documento já foi baixado e não está mais disponível.",
              "alert-warning")
        return redirect(url_for('meus_documentos'))

    s3 = b2_client()
    try:
        obj = s3.get_object(Bucket=b2_bucket_name(), Key=doc.object_key)
        body = obj["Body"]
    except Exception:
        current_app.logger.exception("Falha ao abrir objeto no B2")
        abort(404)

    def stream():
        try:
            for chunk in iter(lambda: body.read(8192), b""):
                yield chunk
        finally:
            try:
                body.close()
            except Exception:
                pass

    resp = Response(stream_with_context(stream()),
                    mimetype=doc.content_type or "application/octet-stream")
    resp.headers["Content-Disposition"] = f'attachment; filename="{doc.nome_original}"'

    # >>> pegue o app e dados que você precisa ANTES de fechar o contexto
    app = current_app._get_current_object()
    key = doc.object_key
    doc_id = doc.id

    @resp.call_on_close
    def _cleanup(_app=app, _key=key, _doc_id=doc_id):
        # reabre contexto da aplicação
        with _app.app_context():
            try:
                b2_delete_all_versions(_key)  # precisa permissão de delete
            except Exception:
                _app.logger.exception(
                    "Falha ao deletar objeto no B2 após download")
            try:
                # atualiza sem manter a instância anexada
                DocumentoMilitar.query.filter_by(id=_doc_id)\
                    .update({"baixado_em": datetime.utcnow()})
                database.session.commit()
            except Exception:
                database.session.rollback()
                _app.logger.exception("Falha ao marcar doc como baixado")

    return resp


@app.get("/documentos/<int:doc_id>/status")
@login_required
def status_documento(doc_id):
    doc = DocumentoMilitar.query.get_or_404(doc_id)
    if not _pode_pegar_doc(doc):
        abort(403)
    return {"baixado": bool(doc.baixado_em)}


@app.route('/militar/<int:militar_id>/excluir', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'SUPER USER')
def excluir_militar(militar_id):
    militar = Militar.query.get(militar_id)
    database.session.delete(militar)
    database.session.commit()
    flash('Militar e registros vinculados excluídos permanentemente', 'alert-danger')
    return redirect(url_for('militares'))
