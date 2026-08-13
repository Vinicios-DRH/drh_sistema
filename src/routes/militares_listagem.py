
from flask import current_app
from flask_login import login_required
from flask import request, jsonify, current_app
from flask import render_template, request, jsonify
from flask_login import login_required
from src import app, database
from src.forms import (FormFiltroMilitar)
from src.models import (Militar, Modalidade)
from src.decorators.control import checar_ocupacao
from datetime import datetime, date
from sqlalchemy.orm import joinedload

from src.routes.helpers import build_tabela_militares_query
from src.services.militares_listagem_service import (
    PER_PAGE,
    montar_choices_filtro_militar,
    extrair_filtros_militares,
    construir_query_militares,
    serializar_militar_linha,
)
from src.services.lts_service import listar_militares_lts
from src.services.militar_situacao_service import processar_fim_de_lts
from src.services.situacoes_militares_service import (
    listar_militares_agregados,
    listar_militares_a_disposicao,
    listar_licencas_especiais,
)
from src.decorators.business_logic import (
    processar_militares_agregados,
    processar_militares_a_disposicao,
    processar_militares_le,
)


@app.route("/militares", methods=["GET"])
@login_required
@checar_ocupacao(
    "DIRETOR",
    "CHEFE",
    "MAPA DA FORÇA",
    "DRH",
    "SUPER USER",
    "DIRETOR DRH",
    "ATUALIZACAO CADASTRAL",
)
def militares():
    form_filtro = FormFiltroMilitar()
    montar_choices_filtro_militar(form_filtro)

    filtros = extrair_filtros_militares(request.args)

    query = construir_query_militares(filtros)
    query = query.order_by(Militar.nome_completo.asc())

    militares_paginados = query.paginate(
        page=filtros.page, per_page=PER_PAGE, error_out=False
    )

    militares_linhas = [
        serializar_militar_linha(militar) for militar in militares_paginados.items
    ]

    total = militares_paginados.total

    return render_template(
        "militares.html",
        militares=militares_linhas,
        form_militar=form_filtro,
        page=filtros.page,
        has_next=militares_paginados.has_next,
        has_prev=militares_paginados.has_prev,
        next_page=militares_paginados.next_num,
        prev_page=militares_paginados.prev_num,
        pages=militares_paginados.pages,
        total=total,
        start=((filtros.page - 1) * PER_PAGE) + 1 if total else 0,
        end=min(filtros.page * PER_PAGE, total),
        has_novo_militar=("adicionar_militar" in current_app.view_functions),
    )


@app.route("/militares-inativos", methods=['GET'])
@login_required
def militares_inativos():
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '', type=str)

        query = Militar.query.options(
            joinedload(Militar.posto_grad),
            joinedload(Militar.quadro),
            joinedload(Militar.especialidade),
            joinedload(Militar.localidade),
            joinedload(Militar.modalidade),
            joinedload(Militar.obm_funcoes)
        ).filter(Militar.modalidade.has(Modalidade.descricao.in_(['RESERVA', 'INATIVO'])))

        if search:
            query = query.filter(Militar.nome_completo.ilike(f"%{search}%"))

        militares_inativos = query.order_by(
            Militar.nome_completo.asc()).paginate(page=page, per_page=100)

        return render_template(
            'militares_inativos.html',
            militares=militares_inativos.items,
            page=page,
            has_next=militares_inativos.has_next,
            has_prev=militares_inativos.has_prev,
            next_page=militares_inativos.next_num,
            prev_page=militares_inativos.prev_num
        )

    except Exception as e:
        app.logger.error(f"Erro ao processar a requisição: {str(e)}")
        return jsonify({'error': 'Ocorreu um erro ao processar a requisição.', 'details': str(e)}), 500


@app.route("/tabela-militares", methods=["GET", "POST"])
@login_required
@checar_ocupacao(
    "DIRETOR",
    "CHEFE",
    "MAPA DA FORÇA",
    "SUPER USER",
    "DRH",
    "DIRETOR DRH",
    "ATUALIZACAO CADASTRAL",
)
def tabela_militares():
    today = date.today()

    try:
        page = request.args.get("page", 1, type=int)
        per_page = 50

        # Esta consulta já contém TODOS os filtros recebidos.
        query = build_tabela_militares_query()

        total_militares = (
            Militar.query
            .filter(Militar.inativo.is_(False))
            .count()
        )

        militares_filtrados = query.all()

        agregados_count = sum(
            1
            for militar in militares_filtrados
            if (militar.situacao or "").strip().upper() == "AGREGADO"
        )

        adisposicao_count = sum(
            1
            for militar in militares_filtrados
            if militar.modalidade_id == 2
        )

        militares_paginados = (
            query
            .order_by(Militar.nome_completo.asc())
            .paginate(
                page=page,
                per_page=per_page,
                error_out=False,
            )
        )

        militares_filtrados_data = []

        for militar in militares_paginados.items:
            obm_funcoes_ativas = sorted(
                [
                    vinculo
                    for vinculo in militar.obm_funcoes
                    if vinculo.data_fim is None
                ],
                # data_criacao é DateTime; use datetime.min, não date.min.
                key=lambda vinculo: vinculo.data_criacao or datetime.min,
                reverse=True,
            )

            obms = [
                vinculo.obm.sigla
                if vinculo.obm
                else "OBM não encontrada"
                for vinculo in obm_funcoes_ativas
            ]

            funcoes = [
                vinculo.funcao.ocupacao
                if vinculo.funcao
                else "Função não encontrada"
                for vinculo in obm_funcoes_ativas
            ]

            destino_txt = (
                militar.destino.local
                if militar.destino and militar.destino.local
                else "N/A"
            )

            inclusao_fmt = (
                militar.inclusao.strftime("%d/%m/%Y")
                if militar.inclusao
                else "N/A"
            )

            situacao_exibe = (militar.situacao or "").strip().upper()

            if not situacao_exibe:
                situacao_exibe = "N/A"

            # Modalidade permanece uma informação separada da situação.
            modalidade_exibe = (
                militar.modalidade.descricao
                if militar.modalidade and militar.modalidade.descricao
                else "N/A"
            )

            sexo_raw = (militar.sexo or "").strip().lower()
            sexo_exibe = (
                "Masculino"
                if sexo_raw.startswith("m")
                else "Feminino"
                if sexo_raw.startswith("f")
                else (militar.sexo or "N/A")
            )

            militares_filtrados_data.append({
                "id": militar.id,
                "nome_completo": militar.nome_completo or "N/A",
                "nome_guerra": militar.nome_guerra or "N/A",
                "sexo": sexo_exibe,
                "raca": militar.raca or "N/A",
                "cpf": militar.cpf or "N/A",
                "rg": militar.rg or "N/A",
                "matricula": militar.matricula or "N/A",
                "posto_grad": (
                    militar.posto_grad.sigla
                    if militar.posto_grad
                    else "N/A"
                ),
                "quadro": (
                    militar.quadro.quadro
                    if militar.quadro
                    else "N/A"
                ),
                "especialidade": (
                    militar.especialidade.ocupacao
                    if militar.especialidade
                    else "N/A"
                ),
                "localidade": (
                    militar.localidade.sigla
                    if militar.localidade
                    else "N/A"
                ),
                "situacao": situacao_exibe,
                "modalidade": modalidade_exibe,
                "destino": destino_txt,
                "inclusao": inclusao_fmt,
                "obms": obms,
                "funcoes": funcoes,
                "data_nascimento": (
                    militar.data_nascimento.strftime("%d/%m/%Y")
                    if militar.data_nascimento
                    else "N/A"
                ),
                "graduacao": militar.graduacao or "N/A",
                "grau_instrucao": militar.grau_instrucao or "N/A",
                "pos_graduacao": militar.pos_graduacao or "N/A",
                "mestrado": militar.mestrado or "N/A",
                "doutorado": militar.doutorado or "N/A",
            })

        return render_template(
            "relacao_militares.html",
            militares=militares_filtrados_data,
            total_militares=total_militares,
            militares_filtrados_count=militares_paginados.total,
            agregados_count=agregados_count,
            adisposicao_count=adisposicao_count,
            page=page,
            total_pages=militares_paginados.pages,
            has_next=militares_paginados.has_next,
            has_prev=militares_paginados.has_prev,
            per_page=per_page,
        )

    except Exception as exc:
        app.logger.exception("Erro ao processar /tabela-militares")
        return jsonify({
            "error": "Ocorreu um erro ao processar a requisição.",
            "details": str(exc),
        }), 500


@app.route("/militares-a-disposicao")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def militares_a_disposicao():
    # Recalcula o status a partir de hoje antes de listar, pra tela nunca
    # mostrar dado desatualizado.
    processar_militares_a_disposicao()

    militares = listar_militares_a_disposicao()
    return render_template('militares_a_disposicao.html', militares=militares)


@app.route("/militares-agregados")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def militares_agregados():
    processar_militares_agregados()

    militares = listar_militares_agregados()
    return render_template('militares_agregados.html', militares=militares)


@app.route("/licenca-especial")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def licenca_especial():
    processar_militares_le()

    militares_le = listar_licencas_especiais()
    return render_template('licenca_especial.html', militares_le=militares_le)


@app.route("/licenca-para-tratamento-de-saude")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH', 'SUPER USER', 'DIRETOR DRH')
def lts():
    # Recalcula o status de todas as LTS a partir de hoje (e devolve pra
    # PRONTO quem já terminou a licença) antes de listar, pra tela nunca
    # mostrar dado desatualizado.
    processar_fim_de_lts()
    database.session.commit()

    militares_lts = listar_militares_lts()

    return render_template('licenca_para_tratamento_de_saude.html', militares_lts=militares_lts)
