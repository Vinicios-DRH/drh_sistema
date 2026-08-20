
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
from src import app, database
from src.forms import (FormMilitarInativo, FormMilitar)
from src.models import (DocumentoMilitar, Militar, MilitaresInativos, PostoGrad, Quadro,
                        EstadoCivil, MilitarObmFuncao, MilitarGraduacao,
                        MilitarContatoEmergencia, MilitarConjuge, MilitarElogio)
from src.decorators.control import checar_ocupacao
from datetime import datetime, date, timedelta
from src.security.perms import has_perm
from src.authz import is_super_or_perm

from src.routes.helpers import (
    _to_manaus,
    _pode_pegar_doc,
)
from src.services.militar_cadastro_service import (
    criar_militar_em_branco,
    montar_choices_form_militar,
    preencher_form_para_exibicao,
    salvar_dados_militar,
    flashar_erros_formulario,
    obter_info_auditoria_situacao,
)
from src.services.elogios_service import criar_elogio, listar_elogios, remover_elogio
from src.services.militar_situacao_service import (
    criar_situacao_extra,
    listar_situacoes_extras,
    parse_date_flex,
    processar_inicio_situacoes_extras,
    processar_fim_de_situacao_militar,
)


@app.route("/adicionar-militar", methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH', 'ATUALIZACAO CADASTRAL')
def adicionar_militar():
    if not is_super_or_perm("MILITAR_CREATE"):
        abort(403)
    if not has_perm("MILITAR_CREATE"):
        abort(403)

    form_militar = FormMilitar()

    # Os choices precisam ser montados antes de validar o submit, senão o
    # WTForms rejeita qualquer valor enviado nos <select>.
    montar_choices_form_militar(form_militar)

    if form_militar.validate_on_submit():
        militar = criar_militar_em_branco()
        salvar_dados_militar(militar, form_militar)
        try:
            database.session.commit()
            flash("Militar adicionado com sucesso!", "success")
            return redirect(url_for("exibir_militar", militar_id=militar.id))
        except Exception as e:
            database.session.rollback()
            current_app.logger.exception("Erro ao adicionar militar")
            flash(f"Erro ao adicionar militar: {str(e)}", "danger")
    elif request.method == "POST":
        flashar_erros_formulario(form_militar)

    return render_template("adicionar_militar.html", form_militar=form_militar, can_edit=True)


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

    if request.method == "GET":
        # Se alguma situação extra chegou na data de início desde a última
        # visita, ela assume a situação principal antes de montar a tela. E
        # se a situação principal (Agregação/À Disposição/Licença Especial/
        # LTS) já passou da data de término, devolve o militar pra PRONTO
        # automaticamente — sem tocar no registro histórico, que continua
        # intacto no banco.
        processar_inicio_situacoes_extras(militar_id=militar_id)
        processar_fim_de_situacao_militar(militar_id)
        database.session.commit()

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

    elogios = listar_elogios(militar.id)
    situacoes_extras = listar_situacoes_extras(militar.id, limite=8)

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

    # Os choices precisam ser montados tanto no GET quanto no POST: é o que
    # permite o WTForms validar os valores enviados no submit.
    montar_choices_form_militar(form_militar)

    bg_sit2_val = ""
    if request.method == "GET":
        bg_sit2_val = preencher_form_para_exibicao(
            form_militar, militar, obm_funcao_tipo_1, obm_funcao_tipo_2)

    can_edit = has_perm("MILITAR_UPDATE")
    can_delete = has_perm("MILITAR_DELETE")

    if form_militar.validate_on_submit():
        salvar_dados_militar(militar, form_militar)
        try:
            database.session.commit()
            flash("Militar atualizado com sucesso!", "success")
            return redirect(url_for("militares"))
        except Exception as e:
            database.session.rollback()
            current_app.logger.exception("Erro ao atualizar militar")
            flash(f"Erro ao atualizar militar: {str(e)}", "danger")
    elif request.method == "POST":
        flashar_erros_formulario(form_militar)

    auditoria_info = obter_info_auditoria_situacao(militar)

    return render_template(
        "exibir_militar.html",
        form_militar=form_militar,
        militar=militar,
        graduacoes=graduacoes,
        contatos_emergencia=contatos_emergencia,
        conjuge=conjuge,
        elogios=elogios,
        situacoes_extras=situacoes_extras,
        can_edit=can_edit,
        can_delete=can_delete,
        bg_sit2_val=bg_sit2_val if request.method == "GET" else request.form.get(
            "situacao_militar_2", ""),
        auditoria_info=auditoria_info,
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


@app.post("/exibir-militar/<int:militar_id>/adicionar-elogio")
@login_required
@checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH')
def adicionar_elogio(militar_id):
    if not has_perm("MILITAR_UPDATE"):
        abort(403)

    militar = Militar.query.get_or_404(militar_id)

    try:
        criar_elogio(
            militar_id=militar.id,
            assunto=request.form.get("assunto"),
            publicacao=request.form.get("publicacao"),
            observacao=request.form.get("observacao"),
            criado_por_user_id=current_user.id,
        )
        database.session.commit()
    except ValueError as e:
        database.session.rollback()
        flash(str(e), "alert-warning")
        return redirect(url_for('exibir_militar', militar_id=militar_id))
    except Exception as e:
        database.session.rollback()
        current_app.logger.exception("Erro ao adicionar elogio")
        flash(f"Erro ao adicionar elogio: {str(e)}", "alert-danger")
        return redirect(url_for('exibir_militar', militar_id=militar_id))

    flash("Elogio registrado com sucesso!", "alert-success")
    return redirect(url_for('exibir_militar', militar_id=militar_id))


@app.post("/elogios/<int:elogio_id>/remover")
@login_required
@checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH')
def remover_elogio_militar(elogio_id):
    if not has_perm("MILITAR_UPDATE"):
        abort(403)

    elogio = MilitarElogio.query.get_or_404(elogio_id)
    militar_id = elogio.militar_id

    remover_elogio(elogio.id)
    database.session.commit()
    flash("Elogio removido.", "alert-success")
    return redirect(url_for('exibir_militar', militar_id=militar_id))


@app.post("/exibir-militar/<int:militar_id>/adicionar-situacao-extra")
@login_required
@checar_ocupacao('DRH', 'MAPA DA FORÇA', 'SUPER USER', 'DIRETOR DRH')
def adicionar_situacao_extra(militar_id):
    if not has_perm("MILITAR_UPDATE"):
        abort(403)

    militar = Militar.query.get_or_404(militar_id)

    destino_raw = request.form.get("destino_situacao_extra")

    try:
        criar_situacao_extra(
            militar=militar,
            tipo=request.form.get("tipo_situacao_extra"),
            destino_id=int(destino_raw) if destino_raw else None,
            inicio=parse_date_flex(request.form.get("inicio_situacao_extra")),
            fim=parse_date_flex(request.form.get("fim_situacao_extra")),
            publicacao_texto=request.form.get("publicacao_situacao_extra"),
        )
        database.session.commit()
    except ValueError as e:
        database.session.rollback()
        flash(str(e), "alert-warning")
        return redirect(url_for('exibir_militar', militar_id=militar_id))
    except Exception as e:
        database.session.rollback()
        current_app.logger.exception("Erro ao adicionar situação extra")
        flash(f"Erro ao adicionar situação extra: {str(e)}", "alert-danger")
        return redirect(url_for('exibir_militar', militar_id=militar_id))

    flash("Situação extra registrada com sucesso!", "alert-success")
    return redirect(url_for('exibir_militar', militar_id=militar_id))


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
