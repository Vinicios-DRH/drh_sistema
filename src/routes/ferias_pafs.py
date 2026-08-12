
from flask_login import login_required
from flask import abort, request, jsonify, make_response
from flask import render_template, request, jsonify, make_response, \
    Response
from flask_login import login_required, current_user
from src import app, database
from src.models import Militar, Obm
from src.decorators.control import checar_ocupacao, obms_permitidas_para_usuario
from datetime import datetime
from sqlalchemy.orm import selectinload
from src.utils.sa_serialize import sa_to_dict
from sqlalchemy.inspection import inspect as sa_inspect
from src.utils.utils import registrar_log_download

from src.services.paf_service import (
    paf_ano_vigente,
    NOMES_MESES,
    calcular_janela_edicao_paf,
    usuario_tem_acesso_obm,
    montar_query_pafs_datatable,
    serializar_linha_paf_datatable,
    listar_militares_sem_paf,
    listar_militares_pafs_para_tabela,
    resolver_ano_referencia_pafs,
    listar_militares_pafs_para_exportacao,
    gerar_planilha_pafs_obm,
    COLUNAS_EXPORTACAO_PAF,
    contar_ferias_por_mes,
    gerar_grafico_ferias_base64,
    alternar_excecao_virada_ano,
    extrair_periodos_ferias,
    validar_periodos_ferias,
    salvar_paf,
    dentro_da_janela_de_edicao_mensal,
    usuario_pode_atualizar_paf,
    usuario_tem_escopo_sobre_militar,
)
from src.authz import is_super_or_perm, can_ferias_bypass_janela


@app.route('/ferias_dados', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER', 'DIRETOR DRH', 'DRH')
def ferias_dados():
    draw = request.form.get('draw', type=int)
    start = request.form.get('start', type=int)
    length = request.form.get('length', type=int)
    search_value = request.form.get('search[value]', type=str)
    ano = request.form.get('ano', type=int) or paf_ano_vigente()

    query = montar_query_pafs_datatable(ano, search_value)

    total_records = query.count()
    militares_pafs = query.offset(start).limit(length).all()

    data = [
        serializar_linha_paf_datatable(militar, paf, usuario)
        for militar, paf, usuario in militares_pafs
    ]

    return jsonify({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": total_records,
        "data": data
    })


@app.route('/ferias', methods=['GET'])
@login_required
@checar_ocupacao('SUPER USER', 'DRH')
def exibir_ferias():
    if not is_super_or_perm("NAV_FERIAS_SUPER"):
        abort(403)

    anos_disponiveis = [2025, 2026]
    return render_template(
        'ferias.html',
        ano_atual=datetime.now().year,
        ano_vigente=paf_ano_vigente(),
        anos_disponiveis=anos_disponiveis
    )


@app.route('/pafs/nao_preenchidos')
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER')
def pafs_nao_preenchidos():
    militares_sem_paf = listar_militares_sem_paf()
    return render_template("pafs_nao_preenchidos.html", militares=militares_sem_paf)


@app.route("/debug/militar/<int:militar_id>/full")
@login_required
def debug_militar_full(militar_id):
    # profundidade padrão (pode diminuir se ainda ficar pesado)
    depth = request.args.get("depth", default=4, type=int)

    # monta options de eager load para TODAS as relationships do Militar
    mapper = sa_inspect(Militar)
    rel_options = [
        selectinload(getattr(Militar, rel.key))
        for rel in mapper.relationships
    ]

    militar = (
        database.session.query(Militar)
        .options(*rel_options)
        .get(militar_id)
    )

    if not militar:
        return jsonify({"error": "Militar não encontrado"}), 404

    payload = sa_to_dict(militar, depth=depth, root_class=Militar)

    return jsonify(payload)


@app.route('/ferias-chefe', methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR DRH', 'DIRETOR', 'CHEFE', 'SUPER USER', 'ATUALIZACAO CADASTRAL')
def exibir_ferias_chefe():
    dia_atual = datetime.now().day

    permitidas = obms_permitidas_para_usuario(current_user)
    lista_obms = Obm.query.filter(Obm.id.in_(
        sorted(permitidas))).order_by(Obm.sigla.asc()).all()

    return render_template(
        'ferias_chefe2.html',
        lista_obms=lista_obms,
        ano_atual=datetime.now().year,
        dia_atual=dia_atual,
        ano_vigente=paf_ano_vigente(),
    )


@app.route('/pafs/tabela/<int:obm_id>', methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR DRH', 'DIRETOR', 'CHEFE', 'SUPER USER', 'ATUALIZACAO CADASTRAL')
def carregar_tabela_obm(obm_id):
    if not usuario_tem_acesso_obm(obm_id):
        return "<div class='alert alert-danger'>Sem permissão para esta OBM.</div>", 403

    ano = int(request.args.get("ano") or datetime.now().year)

    obm = Obm.query.get(obm_id)
    if not obm:
        return "<div class='alert alert-danger'>OBM não encontrada</div>", 404

    janela = calcular_janela_edicao_paf(ano)
    militares_pafs = listar_militares_pafs_para_tabela(obm_id, ano)

    return render_template(
        'partial_tabela_obm.html',
        obm=obm,
        militares_pafs=militares_pafs,
        meses=NOMES_MESES,
        current_month=datetime.now().month,
        current_date=datetime.now().date(),
        ano=ano,
        min_iso=janela["min_iso"],
        min_year=janela["min_year"],
        min_month=janela["min_month"],
        bloqueio_mes_atual=janela["bloqueio_mes_atual"],
        is_super=janela["is_super"],
    )


@app.route('/pafs/toggle_excecao', methods=['POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER')
def toggle_excecao():
    militar_id = request.form.get('militar_id', type=int)
    ano = request.form.get('ano', type=int)
    excecao = request.form.get('excecao') == 'true'

    alternar_excecao_virada_ano(militar_id, ano, excecao, current_user.id)
    database.session.commit()

    return jsonify({"status": "success", "message": "Status de exceção atualizado."})


@app.route("/exportar-pafs-obm/<int:obm_id>")
@login_required
@checar_ocupacao('DIRETOR DRH', 'DIRETOR', 'CHEFE', 'SUPER USER', 'ATUALIZACAO CADASTRAL')
def exportar_pafs_obm(obm_id):
    if not usuario_tem_acesso_obm(obm_id):
        return "Sem permissão para exportar esta OBM.", 403

    obm = Obm.query.get_or_404(obm_id)

    ano = resolver_ano_referencia_pafs(request.args.get("ano", type=int))
    if not ano:
        return "Não há PAFs cadastrados para exportação.", 404

    militares_pafs = listar_militares_pafs_para_exportacao(obm_id, ano)
    output = gerar_planilha_pafs_obm(obm, ano, militares_pafs)

    registrar_log_download(
        nome_relatorio=f"Plano Anual de Férias (PAF) - {obm.sigla}",
        colunas_lista=COLUNAS_EXPORTACAO_PAF,
        filtros_dict={
            "ano_referencia": ano,
            "obm_id": obm_id,
            "obm_sigla": obm.sigla
        }
    )

    filename = f"pafs_{obm.sigla}_{ano}.xlsx"
    response = make_response(output.read())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response


@app.route('/grafico-ferias/<int:obm_id>', methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'SUPER USER')
def grafico_ferias(obm_id):
    ferias_por_mes = contar_ferias_por_mes(obm_id)
    image_base64 = gerar_grafico_ferias_base64(ferias_por_mes)
    return Response(response=image_base64, status=200, mimetype='text/plain')


@app.route('/pafs/update', methods=['POST'])
@login_required
def update_paf():
    if not dentro_da_janela_de_edicao_mensal() and not can_ferias_bypass_janela():
        return jsonify({"message": "Alterações só são permitidas de 10 a 20 de cada mês."}), 403

    if not usuario_pode_atualizar_paf():
        return jsonify({"error": "Sem permissão para atualizar PAF."}), 403

    militar_id = int(request.form.get('militar_id') or 0)
    ano = int(request.form.get('ano_referencia') or datetime.now().year)

    if not militar_id:
        return jsonify({"error": "militar_id inválido"}), 400

    if not usuario_tem_escopo_sobre_militar(militar_id):
        return jsonify({"error": "Sem permissão para alterar PAF deste militar."}), 403

    periodos = extrair_periodos_ferias(request.form)

    try:
        validar_periodos_ferias(periodos)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    salvar_paf(
        militar_id=militar_id,
        ano=ano,
        mes_usufruto=request.form.get('mes_usufruto'),
        periodos=periodos,
        usuario_id=current_user.id,
    )
    database.session.commit()

    return jsonify({"message": "Dados salvos com sucesso!"})
