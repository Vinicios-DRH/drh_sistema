
from flask import current_app
from flask_login import login_required
from flask import request, current_app
import os
from flask import render_template, redirect, url_for, request, flash, session, send_file
from flask_login import login_required, current_user
from src import app
from src.models import (ImportacaoMilitarHistorico, Obm)
from src.authz import require_perm
from src.services.importar_militares import (
    ler_planilha,
    colunas_reconhecidas,
    importar_dataframe,
    salvar_historico_importacao,
)
from src.services.importacao_militares_wizard import (
    payload_para_dataframe,
    montar_contexto_confirmacao,
    salvar_resultado_na_sessao,
    obter_resultado_da_sessao,
    parse_json_seguro,
)


@app.route("/militares/importar", methods=["GET"])
@login_required
@require_perm("NAV_MIL_ATIVOS_IMPORT")
def tela_importar_militares():
    obms = Obm.query.order_by(Obm.sigla).all()
    return render_template(
        "militares/importar_upload.html",
        obms=obms
    )


@app.route("/militares/importar/modelo", methods=["GET"])
@login_required
@require_perm("NAV_MIL_ATIVOS_IMPORT")
def download_modelo_importacao():
    caminho_arquivo = os.path.join(
        current_app.root_path, 'static/downloads', 'modelo_planilha_importacao.xlsx')

    return send_file(
        caminho_arquivo,
        as_attachment=True,
        download_name="modelo_planilha_importacao.xlsx"
    )


@app.route("/militares/importar/analisar", methods=["POST"])
@login_required
def analisar_importacao_militares():
    arquivo = request.files.get("arquivo")
    modo = request.form.get("modo", "misto")

    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo Excel ou CSV.", "danger")
        return redirect(url_for("tela_importar_militares"))

    try:
        nome_arquivo = arquivo.filename
        df = ler_planilha(arquivo)

        if df.empty:
            flash("A planilha está vazia.", "warning")
            return redirect(url_for("tela_importar_militares"))

        colunas_ok = colunas_reconhecidas(df)
        if not colunas_ok:
            flash("Nenhuma coluna reconhecida para importação.", "warning")
            return redirect(url_for("tela_importar_militares"))

        # A OBM é escolhida à parte (checkbox "aplicar a todos"), então não
        # entra pré-selecionada entre os campos a importar.
        campos_preselecionados = [c for c in colunas_ok if c != "obm"]

        contexto = montar_contexto_confirmacao(
            df, campos_preselecionados, modo, nome_arquivo)

        return render_template("militares/importar_confirmacao.html", **contexto)

    except Exception as e:
        flash(f"Erro ao analisar planilha: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))


@app.route("/militares/importar/reanalisar", methods=["POST"])
@login_required
def reanalisar_importacao_militares():
    payload_b64 = request.form.get("payload_b64")
    campos_selecionados = request.form.getlist("campos")
    nome_arquivo = request.form.get("nome_arquivo", "arquivo_importado")
    modo = request.form.get("modo", "misto")

    if not campos_selecionados:
        flash("Selecione pelo menos um campo para reanalisar.", "warning")
        return redirect(url_for("tela_importar_militares"))

    try:
        df = payload_para_dataframe(payload_b64)
        contexto = montar_contexto_confirmacao(
            df, campos_selecionados, modo, nome_arquivo, payload_b64=payload_b64)

        return render_template("militares/importar_confirmacao.html", **contexto)

    except Exception as e:
        flash(f"Erro ao reanalisar planilha: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))


@app.route("/militares/importar/confirmar", methods=["POST"])
@login_required
def confirmar_importacao_militares():
    payload_b64 = request.form.get("payload_b64")
    campos_selecionados = request.form.getlist("campos")
    modo = request.form.get("modo", "misto")
    regra_atualizacao = request.form.get("regra_atualizacao", "complementar")
    aplicar_obm = request.form.get("aplicar_obm")
    obm_id = request.form.get("obm_id")
    nome_arquivo = request.form.get("nome_arquivo", "arquivo_importado")

    if not campos_selecionados:
        flash("Selecione pelo menos um campo para importar.", "warning")
        return redirect(url_for("tela_importar_militares"))

    try:
        df = payload_para_dataframe(payload_b64)
    except ValueError as e:
        current_app.logger.exception(
            "Erro ao reconstruir DataFrame da importação.")
        flash(str(e), "danger")
        return redirect(url_for("tela_importar_militares"))

    obm_id_final = None
    if aplicar_obm == "1" and obm_id:
        try:
            obm_id_final = int(obm_id)
        except ValueError:
            flash("OBM inválida selecionada.", "danger")
            return redirect(url_for("tela_importar_militares"))

    try:
        relatorio = importar_dataframe(
            df=df,
            campos_selecionados=campos_selecionados,
            modo=modo,
            regra_atualizacao=regra_atualizacao,
            obm_id=obm_id_final,
            usuario_id=current_user.id,
        )
    except Exception as e:
        current_app.logger.exception(
            "Erro durante a importação dos militares.")
        flash(f"Erro ao importar planilha: {str(e)}", "danger")
        return redirect(url_for("tela_importar_militares"))

    try:
        salvar_historico_importacao(
            usuario_id=current_user.id,
            nome_arquivo=nome_arquivo,
            modo=modo,
            campos_selecionados=campos_selecionados,
            relatorio=relatorio,
            total_linhas=len(df),
            obm_id=obm_id_final,
        )
    except Exception as e:
        current_app.logger.exception("Erro ao salvar histórico da importação.")
        flash(
            f"Importação concluída, mas falhou ao salvar o histórico: {str(e)}", "warning")

    salvar_resultado_na_sessao(
        session, relatorio, nome_arquivo, modo, campos_selecionados)

    flash(
        f"Importação concluída. Inseridos: {relatorio['inseridos']} | "
        f"Atualizados: {relatorio['atualizados']} | "
        f"Ignorados: {relatorio['ignorados']}",
        "success"
    )

    return redirect(url_for("resultado_importacao_militares"))


@app.route("/militares/importar/historico", methods=["GET"])
@login_required
def historico_importacao_militares():
    historicos = (
        ImportacaoMilitarHistorico.query
        .order_by(ImportacaoMilitarHistorico.criado_em.desc())
        .limit(100)
        .all()
    )

    return render_template(
        "militares/importar_historico.html",
        historicos=historicos
    )


@app.route("/militares/importar/historico/<int:historico_id>", methods=["GET"])
@login_required
def detalhe_historico_importacao_militares(historico_id):
    historico = ImportacaoMilitarHistorico.query.get_or_404(historico_id)

    return render_template(
        "militares/importar_historico_detalhe.html",
        historico=historico,
        campos=parse_json_seguro(historico.campos_json),
        relatorio=parse_json_seguro(historico.relatorio_json),
    )


@app.route("/militares/importar/resultado", methods=["GET"])
@login_required
def resultado_importacao_militares():
    resultado = obter_resultado_da_sessao(session)

    if not resultado["relatorio"]:
        flash("Nenhum resultado de importação disponível.", "warning")
        return redirect(url_for("tela_importar_militares"))

    return render_template("militares/importar_resultado.html", **resultado)
