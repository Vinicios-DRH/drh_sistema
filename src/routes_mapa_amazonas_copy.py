from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from sqlalchemy import case, or_
from datetime import date

from src import database
from src.decorators.control import checar_ocupacao
from src.models import (
    Militar,
    Obm,
    MilitarObmFuncao,
    PostoGrad,
    Funcao,
    MilitarContatoEmergencia,
    Quadro,
    Viaturas,
    Curso,
    MilitarCurso,
    EfetivoDiarioOBM,
    Modalidade,
)
from src.querys import obter_estatisticas_militares


PERFIS_MAPA = (
    "DIRETOR DRH",
    "DIRETOR",
    "CHEFE",
    "SUPER USER",
    "DRH",
    "MAPA DA FORÇA",
)

MODALIDADE_PRONTO_ID = 8

FUNCOES_COMANDO = [1, 2, 3, 4, 5, 9, 10, 11, 12, 24]

PESO_FUNCAO = {
    4: 1, 5: 2, 2: 3, 3: 4, 1: 5,
    11: 6, 12: 7, 10: 8, 9: 9, 24: 10
}

PESOS_POSTOS = {
    'CEL': 1, 'TC': 2, 'MAJ': 3, 'CAP': 4,
    '1º TEN': 5, '2º TEN': 6, 'ASP': 7, 'AL OF': 8,
    'ALUNO OFICIAL': 9, 'SUBTENENTE': 10, '1º SGT': 11,
    '2º SGT': 12, '3º SGT': 13, 'AL SGT': 14,
    'CB': 15, 'SD': 16, 'AL SD': 17
}


def fmt_data(data):
    return data.strftime("%d/%m/%Y") if data else None


def nome_operacional(militar, posto=None):
    posto_sigla = posto.sigla if posto else ""
    nome = militar.nome_guerra or militar.nome_completo or "Sem nome"
    return f"{posto_sigla} {nome}".strip()


def registro_diario_mais_recente(registros):
    """
    Proteção caso existam registros duplicados para o mesmo militar/OBM.
    O ideal é ter unique constraint em militar_id + obm_id.
    """
    mapa = {}

    for registro in registros:
        chave = (registro.obm_id, registro.militar_id)

        if chave not in mapa:
            mapa[chave] = registro
            continue

        atual = mapa[chave]
        if registro.atualizado_em and atual.atualizado_em:
            if registro.atualizado_em > atual.atualizado_em:
                mapa[chave] = registro

    return mapa


def montar_situacao_diaria(registro):
    if not registro:
        return {
            "descricao": "Pronto",
            "classe": "pronto",
            "presente_na_obm": True,
            "local_disposicao": None,
            "inicio_periodo": None,
            "fim_periodo": None,
            "comprovante_url": None,
        }

    modalidade_desc = registro.modalidade.descricao if registro.modalidade else None

    if registro.modalidade_id and registro.modalidade_id != MODALIDADE_PRONTO_ID:
        descricao = modalidade_desc or "Afastado/Licença"
        classe = "licenca"
        presente = False
    elif registro.presente_na_obm is False:
        descricao = "Fora da OBM"
        classe = "fora"
        presente = False
    else:
        descricao = modalidade_desc or "Pronto"
        classe = "pronto"
        presente = True

    return {
        "descricao": descricao,
        "classe": classe,
        "presente_na_obm": presente,
        "local_disposicao": registro.local_disposicao,
        "inicio_periodo": fmt_data(registro.inicio_periodo),
        "fim_periodo": fmt_data(registro.fim_periodo),
        "comprovante_url": registro.comprovante_modalidade_url,
    }

mapa_bp = Blueprint('mapa_amazonas_teste', __name__)

COORDENADAS_CIDADES = {
    "MANAUS": [-3.1190, -60.0217],
    "LÁBREA": [-7.2597, -64.7983],
    "MANICORÉ": [-5.8090, -61.3004],
    "NOVO ARIPUANÃ": [-5.1206, -60.3797],
    "TAPAUÁ": [-5.6247, -63.1816],
    "ITACOATIARA": [-3.1432, -58.4442],
    "MANACAPURU": [-3.2996, -60.6206],
    "PARINTINS": [-2.6282, -56.7358],
    "PRESIDENTE FIGUEIREDO": [-2.0526, -60.0263],
    "RIO PRETO DA EVA": [-2.6989, -59.7001],
    "IRANDUBA": [-3.2842, -60.1861],
    "AUTAZES": [-3.5794, -59.1305],
    "NOVO AIRÃO": [-2.6218, -60.9438],
    "ITAPIRANGA": [-2.7492, -58.0227],
    "MAUÉS": [-3.3836, -57.7188],
    "MANAQUIRI": [-3.4258, -60.4586],
    "TABATINGA": [-4.2285, -69.9388],
    "TEFÉ": [-3.3526, -64.7106],
    "COARI": [-4.0848, -63.1416],
    "ATALAIA DO NORTE": [-4.3725, -70.1919],
    "ENVIRA": [-7.3013, -70.2185],
    "JUTAÍ": [-2.7458, -66.7672],
    "BARCELOS": [-0.9730, -62.9224],
    "HUMAITÁ": [-7.5061, -63.0208],
    "APUÍ": [-7.1941, -59.8960],
    "BORBA": [-4.3878, -59.5939]
}


@mapa_bp.route('/mapa-efetivo-teste')
@login_required
# @checar_ocupacao(*PERFIS_MAPA)
def renderizar_mapa():
    return render_template('mapa_amazonas_copy.html')


@mapa_bp.route('/api/estatisticas-gerais-teste')
def api_estatisticas_gerais():
    """Retorna os dados globais para o rodapé do Dashboard."""
    # 1. Pega os dados já validados de querys.py
    stats = obter_estatisticas_militares()

    # 2. Calcula a média de idade de todos os ativos via Python (livre de erros de dialeto SQL)
    idades_db = database.session.query(Militar.data_nascimento).filter(
        Militar.inativo.is_(False),
        Militar.posto_grad_id != 15,
        Militar.data_nascimento.isnot(None)
    ).all()

    hoje = date.today()
    soma_idades = 0
    total_validos = 0

    for registro in idades_db:
        nascimento = registro[0]
        if nascimento:
            # Calcula a idade exata
            idade = hoje.year - nascimento.year - \
                ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
            soma_idades += idade
            total_validos += 1

    media_idade = round(soma_idades / total_validos,
                        1) if total_validos > 0 else 0

    return jsonify({
        "total": stats.get("efetivo_total_sem_civis", 0),
        "media_idade": media_idade,
        "combatentes": stats.get("militares_combatentes", 0),
        "saude": stats.get("militares_saude", 0)
    })


@mapa_bp.route('/api/mapa-dados-teste')
@login_required
# @checar_ocupacao(*PERFIS_MAPA)
def api_dados_mapa():
    base_efetivo = (
        database.session.query(
            Obm.id.label("obm_id"),
            Obm.sigla.label("obm_sigla"),
            Militar.id.label("militar_id")
        )
        .join(MilitarObmFuncao, MilitarObmFuncao.obm_id == Obm.id)
        .join(Militar, Militar.id == MilitarObmFuncao.militar_id)
        .filter(
            Militar.inativo.is_(False),
            Militar.posto_grad_id != 15,
            MilitarObmFuncao.data_fim.is_(None),
            or_(
                MilitarObmFuncao.funcao_id.is_(None),
                MilitarObmFuncao.funcao_id != 26
            )
        )
        .all()
    )

    obms_dict = {}
    militares_por_obm = {}

    for linha in base_efetivo:
        obms_dict[linha.obm_id] = linha.obm_sigla
        militares_por_obm.setdefault(linha.obm_id, set()).add(linha.militar_id)

    obm_ids = list(obms_dict.keys())

    registros_diarios = []
    if obm_ids:
        registros_diarios = (
            EfetivoDiarioOBM.query
            .filter(EfetivoDiarioOBM.obm_id.in_(obm_ids))
            .all()
        )

    mapa_diario = registro_diario_mais_recente(registros_diarios)

    resumo_por_obm = {}

    for obm_id, militares_ids in militares_por_obm.items():
        resumo = {
            "total": len(militares_ids),
            "prontos": 0,
            "em_licenca": 0,
            "fora_obm": 0,
            "dirigindo_hoje": 0,
        }

        for militar_id in militares_ids:
            diario = mapa_diario.get((obm_id, militar_id))

            if diario and diario.viatura_diaria_id:
                resumo["dirigindo_hoje"] += 1

            if diario and diario.modalidade_id and diario.modalidade_id != MODALIDADE_PRONTO_ID:
                resumo["em_licenca"] += 1
            elif diario and diario.presente_na_obm is False:
                resumo["fora_obm"] += 1
            else:
                resumo["prontos"] += 1

        resumo_por_obm[obm_id] = resumo

    comandantes_query = (
        database.session.query(
            MilitarObmFuncao.obm_id,
            Militar.nome_guerra,
            Militar.nome_completo,
            PostoGrad.sigla,
            MilitarObmFuncao.funcao_id
        )
        .join(Militar, Militar.id == MilitarObmFuncao.militar_id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .filter(
            Militar.inativo.is_(False),
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.funcao_id.in_(FUNCOES_COMANDO)
        )
        .all()
    )

    comandantes_dict = {}
    melhor_peso_obm = {}

    for obm_id, nome_guerra, nome_completo, posto_sigla, funcao_id in comandantes_query:
        nome = nome_guerra or nome_completo or "Não informado"
        posto = posto_sigla or ""
        peso_atual = PESO_FUNCAO.get(funcao_id, 99)

        if obm_id not in comandantes_dict or peso_atual < melhor_peso_obm.get(obm_id, 99):
            comandantes_dict[obm_id] = f"{posto} {nome}".strip()
            melhor_peso_obm[obm_id] = peso_atual

    resultado = []

    for obm_id, sigla in obms_dict.items():
        sigla_upper = sigla.upper()
        cidade_destino = "MANAUS"

        for cidade in COORDENADAS_CIDADES.keys():
            if cidade != "MANAUS" and cidade in sigla_upper:
                cidade_destino = cidade
                break

        import random
        lat_base, lng_base = COORDENADAS_CIDADES[cidade_destino]

        lat = lat_base + random.uniform(-0.015, 0.015) if cidade_destino == "MANAUS" else lat_base
        lng = lng_base + random.uniform(-0.015, 0.015) if cidade_destino == "MANAUS" else lng_base

        resumo = resumo_por_obm.get(obm_id, {
            "total": 0,
            "prontos": 0,
            "em_licenca": 0,
            "fora_obm": 0,
            "dirigindo_hoje": 0,
        })

        resultado.append({
            "obm_id": obm_id,
            "obm": sigla,
            "efetivo": resumo["total"],
            "prontos": resumo["prontos"],
            "em_licenca": resumo["em_licenca"],
            "fora_obm": resumo["fora_obm"],
            "dirigindo_hoje": resumo["dirigindo_hoje"],
            "cidade": cidade_destino,
            "lat": lat,
            "lng": lng,
            "comandante": comandantes_dict.get(obm_id, "Não atribuído")
        })

    return jsonify(resultado)


@mapa_bp.route('/api/media-idade-posto')
def api_media_idade_posto():
    # 1. Busca militares ativos, excluindo posto 15 (se for a regra) e com data de nascimento válida
    query = database.session.query(
        PostoGrad.sigla,
        Militar.data_nascimento
    ).join(
        PostoGrad, PostoGrad.id == Militar.posto_grad_id
    ).filter(
        Militar.inativo.is_(False),
        Militar.posto_grad_id != 15,
        Militar.data_nascimento.isnot(None)
    ).all()

    hoje = date.today()
    dados_idade = {}

    # 2. Agrupa as idades calculadas por sigla do posto
    for sigla, nascimento in query:
        idade = hoje.year - nascimento.year - \
            ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))

        if sigla not in dados_idade:
            dados_idade[sigla] = []
        dados_idade[sigla].append(idade)

    # 3. Define a ordem hierárquica para o gráfico ficar organizado
    ordem_hierarquica = [
        'CEL', 'TC', 'MAJ', 'CAP', '1º TEN', '2º TEN', 'ASP', 'AL OF',
        'ALUNO OFICIAL', 'SUBTENENTE', '1º SGT', '2º SGT', '3º SGT',
        'AL SGT', 'CB', 'AL SD', 'SD'
    ]

    resultado = []

    # 4. Monta o resultado respeitando a ordem
    for sigla in ordem_hierarquica:
        if sigla in dados_idade and len(dados_idade[sigla]) > 0:
            media = sum(dados_idade[sigla]) / len(dados_idade[sigla])
            resultado.append({
                "posto": sigla,
                "media": round(media, 1)
            })

    # Caso exista algum posto fora da lista, adiciona no final
    for sigla, idades in dados_idade.items():
        if sigla not in ordem_hierarquica and len(idades) > 0:
            media = sum(idades) / len(idades)
            resultado.append({
                "posto": sigla,
                "media": round(media, 1)
            })

    return jsonify(resultado)


@mapa_bp.route('/api-teste/militares-obm/<int:obm_id>')
@login_required
# @checar_ocupacao(*PERFIS_MAPA)
def api_militares_obm(obm_id):
    ordem_hierarquica = case(
        PESOS_POSTOS,
        value=database.func.upper(PostoGrad.sigla),
        else_=99
    )

    query = (
        database.session.query(
            Militar,
            PostoGrad,
            MilitarObmFuncao,
            Funcao,
            MilitarContatoEmergencia,
            Quadro
        )
        .join(MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id)
        .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)
        .outerjoin(Funcao, Funcao.id == MilitarObmFuncao.funcao_id)
        .outerjoin(MilitarContatoEmergencia, MilitarContatoEmergencia.militar_id == Militar.id)
        .outerjoin(Quadro, Quadro.id == Militar.quadro_id)
        .filter(
            MilitarObmFuncao.obm_id == obm_id,
            MilitarObmFuncao.data_fim.is_(None),
            Militar.inativo.is_(False),
            Militar.posto_grad_id != 15,
            or_(
                MilitarObmFuncao.funcao_id.is_(None),
                MilitarObmFuncao.funcao_id != 26
            )
        )
        .order_by(
            ordem_hierarquica,
            Militar.rg.asc()
        )
        .all()
    )

    militar_ids = [m.id for m, _, _, _, _, _ in query]

    cursos_por_militar = {}
    if militar_ids:
        cursos_db = (
            database.session.query(MilitarCurso.militar_id, Curso.nome)
            .join(Curso, Curso.id == MilitarCurso.curso_id)
            .filter(MilitarCurso.militar_id.in_(militar_ids))
            .order_by(Curso.nome.asc())
            .all()
        )

        for militar_id, curso_nome in cursos_db:
            cursos_por_militar.setdefault(militar_id, []).append(curso_nome)

    registros_diarios = []
    if militar_ids:
        registros_diarios = (
            EfetivoDiarioOBM.query
            .filter(
                EfetivoDiarioOBM.obm_id == obm_id,
                EfetivoDiarioOBM.militar_id.in_(militar_ids)
            )
            .all()
        )

    mapa_diario = registro_diario_mais_recente(registros_diarios)

    resultado_militares = []
    militares_vistos = set()
    motoristas_diarios_por_viatura = {}

    for militar, posto, m_funcao, funcao, contato_emergencia, quadro in query:
        if militar.id in militares_vistos:
            continue

        militares_vistos.add(militar.id)

        sigla_posto = posto.sigla if posto else "S/P"
        sigla_quadro = quadro.quadro if quadro else ""
        rg_militar = militar.rg or "S/RG"

        funcao_id = m_funcao.funcao_id if m_funcao else None
        is_comandante = funcao_id in FUNCOES_COMANDO
        nome_funcao = funcao.ocupacao if funcao else ""
        peso = PESO_FUNCAO.get(funcao_id, 99)

        rg_num = 999999999
        if militar.rg:
            numeros_rg = ''.join(filter(str.isdigit, militar.rg))
            if numeros_rg:
                rg_num = int(numeros_rg)

        celular = militar.celular or "Não informado"
        contato_nome = contato_emergencia.nome if contato_emergencia else "Nenhum cadastrado"
        contato_tel = contato_emergencia.telefone if contato_emergencia else "---"

        diario = mapa_diario.get((obm_id, militar.id))
        situacao = montar_situacao_diaria(diario)

        viatura_diaria = None
        if diario and diario.viatura_diaria:
            viatura = diario.viatura_diaria
            viatura_diaria = {
                "id": viatura.id,
                "prefixo": viatura.prefixo or "S/ Prefixo",
                "marca_modelo": viatura.marca_modelo or "Modelo não informado",
                "placa": viatura.placa or "---",
            }

            motoristas_diarios_por_viatura.setdefault(viatura.id, []).append(
                nome_operacional(militar, posto)
            )

        resultado_militares.append({
            "id": militar.id,
            "nome": militar.nome_guerra or militar.nome_completo,
            "posto": sigla_posto,
            "quadro": sigla_quadro,
            "rg": rg_militar,
            "is_comandante": is_comandante,
            "funcao": nome_funcao,
            "celular": celular,
            "contato_emergencia_nome": contato_nome,
            "contato_emergencia_tel": contato_tel,
            "cursos": cursos_por_militar.get(militar.id, []),

            "situacao": situacao["descricao"],
            "situacao_classe": situacao["classe"],
            "presente_na_obm": situacao["presente_na_obm"],
            "local_disposicao": situacao["local_disposicao"],
            "inicio_periodo": situacao["inicio_periodo"],
            "fim_periodo": situacao["fim_periodo"],
            "comprovante_modalidade_url": situacao["comprovante_url"],
            "viatura_diaria": viatura_diaria,

            "peso_funcao": peso,
            "posto_ordem": PESOS_POSTOS.get(sigla_posto.upper(), 99),
            "rg_num": rg_num
        })

    resultado_militares.sort(key=lambda x: (
        not x["is_comandante"],
        x["peso_funcao"],
        x["posto_ordem"],
        x["rg_num"]
    ))

    viaturas_query = (
        Viaturas.query
        .filter(Viaturas.obm_id == obm_id)
        .order_by(Viaturas.prefixo.asc())
        .all()
    )

    resultado_viaturas = []

    for viatura in viaturas_query:
        resultado_viaturas.append({
            "id": viatura.id,
            "prefixo": viatura.prefixo or "S/ Prefixo",
            "marca_modelo": viatura.marca_modelo or "Modelo não inf.",
            "placa": viatura.placa or "---",
            "motoristas": sorted(motoristas_diarios_por_viatura.get(viatura.id, []))
        })

    return jsonify({
        "militares": resultado_militares,
        "viaturas": resultado_viaturas
    })

# ====================================================================
# NOVAS ROTAS PARA O PAINEL DE ESPECIALIDADES
# ====================================================================

@mapa_bp.route('/api-teste/cursos')
def api_cursos_lista():
    """Retorna todos os cursos para preencher o Select de busca"""
    cursos = database.session.query(
        Curso.id, Curso.nome).order_by(Curso.nome.asc()).all()
    return jsonify([{"id": c.id, "nome": c.nome} for c in cursos])


@mapa_bp.route('/api-teste/militares-por-especialidade/<int:curso_id>')
def api_pesquisa_especialidade(curso_id):
    """Busca todos os militares ativos que possuem um curso específico e onde estão lotados"""
    query = database.session.query(
        Militar.nome_guerra, Militar.nome_completo, PostoGrad.sigla,
        Obm.sigla.label('obm_sigla'), Obm.id.label('obm_id'),
        database.func.upper(Obm.sigla)
    ).join(
        MilitarCurso, MilitarCurso.militar_id == Militar.id
    ).join(
        PostoGrad, PostoGrad.id == Militar.posto_grad_id
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id
    ).join(
        Obm, Obm.id == MilitarObmFuncao.obm_id
    ).filter(
        MilitarCurso.curso_id == curso_id,
        Militar.inativo.is_(False),
        MilitarObmFuncao.data_fim.is_(None)
    ).order_by(PostoGrad.id.asc()).all()

    resultados = []
    for nome_guerra, nome_completo, posto, obm_sigla, obm_id, obm_upper in query:
        cidade_destino = "MANAUS"
        for cidade in COORDENADAS_CIDADES.keys():
            if cidade != "MANAUS" and cidade in obm_upper:
                cidade_destino = cidade
                break

        nome = nome_guerra if nome_guerra else nome_completo
        resultados.append({
            "nome_completo": f"{posto} {nome}",
            "obm": obm_sigla,
            "obm_id": obm_id,
            "cidade": cidade_destino
        })

    return jsonify(resultados)


# Manaus
# Rota para renderizar a página HTML exclusiva de Manaus
@mapa_bp.route('/mapa-efetivo-manaus')
def renderizar_mapa_manaus():
    return render_template('mapa_manaus.html')

# API que retorna os dados do mapa filtrados apenas para a Capital


@mapa_bp.route('/api/mapa-dados-manaus')
def api_dados_mapa_manaus():
    # 1. Query principal (Igual a original)
    query = database.session.query(
        Obm.id,
        Obm.sigla,
        database.func.count(database.func.distinct(
            Militar.id)).label('total_efetivo')
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.obm_id == Obm.id
    ).join(
        Militar, Militar.id == MilitarObmFuncao.militar_id
    ).filter(
        Militar.posto_grad_id != 15,
        MilitarObmFuncao.data_fim.is_(None)
    ).group_by(Obm.id, Obm.sigla).all()

    # 2. Query dos comandantes (Igual a original)
    FUNCOES_COMANDO = [1, 2, 3, 4, 5, 9, 10, 11, 12, 24]
    comandantes_query = database.session.query(
        MilitarObmFuncao.obm_id, Militar.nome_guerra, Militar.nome_completo,
        PostoGrad.sigla, MilitarObmFuncao.funcao_id
    ).join(Militar, Militar.id == MilitarObmFuncao.militar_id)\
     .outerjoin(PostoGrad, PostoGrad.id == Militar.posto_grad_id)\
     .filter(MilitarObmFuncao.data_fim.is_(None), MilitarObmFuncao.funcao_id.in_(FUNCOES_COMANDO)).all()

    PESO_FUNCAO = {4: 1, 5: 2, 2: 3, 3: 4,
                   1: 5, 11: 6, 12: 7, 10: 8, 9: 9, 24: 10}

    comandantes_dict = {}
    melhor_peso_obm = {}

    for obm_id, nome_guerra, nome_completo, posto_sigla, funcao_id in comandantes_query:
        nome = nome_guerra if nome_guerra else nome_completo
        posto = posto_sigla if posto_sigla else ""
        peso_atual = PESO_FUNCAO.get(funcao_id, 99)

        if obm_id not in comandantes_dict or peso_atual < melhor_peso_obm.get(obm_id, 99):
            comandantes_dict[obm_id] = f"{posto} {nome}".strip()
            melhor_peso_obm[obm_id] = peso_atual

    resultado = []

    # 3. Montagem do JSON (COM FILTRO PARA MANAUS)
    for obm_id, sigla, efetivo in query:
        sigla_upper = sigla.upper()
        cidade_destino = "MANAUS"

        for cidade in COORDENADAS_CIDADES.keys():
            if cidade != "MANAUS" and cidade in sigla_upper:
                cidade_destino = cidade
                break

        # A MÁGICA ACONTECE AQUI: Só adiciona na lista se a cidade for MANAUS
        if cidade_destino == "MANAUS":
            import random
            lat_base, lng_base = COORDENADAS_CIDADES["MANAUS"]

            # Espalha os pins um pouco mais, já que o zoom vai ser maior na capital
            lat = lat_base + random.uniform(-0.025, 0.025)
            lng = lng_base + random.uniform(-0.025, 0.025)

            resultado.append({
                "obm_id": obm_id,
                "obm": sigla,
                "efetivo": efetivo,
                "cidade": cidade_destino,
                "lat": lat,
                "lng": lng,
                "comandante": comandantes_dict.get(obm_id, "Não atribuído")
            })

    return jsonify(resultado)


@mapa_bp.route('/api/estatisticas-gerais-manaus')
def api_estatisticas_gerais_manaus():
    """Retorna os dados globais APENAS para Manaus."""
    # Busca militares ativos, suas OBMs e seus quadros
    query = database.session.query(
        Militar.id,
        Militar.data_nascimento,
        Quadro.quadro,
        Obm.sigla
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id
    ).join(
        Obm, Obm.id == MilitarObmFuncao.obm_id
    ).outerjoin(
        Quadro, Quadro.id == Militar.quadro_id
    ).filter(
        Militar.inativo.is_(False),
        Militar.posto_grad_id != 15,
        MilitarObmFuncao.data_fim.is_(None)
    ).all()

    hoje = date.today()
    total = 0
    combatentes = 0
    saude = 0
    soma_idades = 0
    total_idades = 0
    vistos = set()

    for m_id, nascimento, quadro_nome, obm_sigla in query:
        # Evita contar o mesmo militar duas vezes caso ele tenha duas funções na mesma OBM
        if m_id in vistos:
            continue

        sigla_upper = obm_sigla.upper() if obm_sigla else ""
        is_manaus = True

        # Lógica de filtro: se tiver nome de município do interior na OBM, não é Manaus
        for cidade in COORDENADAS_CIDADES.keys():
            if cidade != "MANAUS" and cidade in sigla_upper:
                is_manaus = False
                break

        if is_manaus:
            vistos.add(m_id)
            total += 1

            # Verifica se é do Quadro de Saúde (ajuste a string se o banco for diferente)
            q_str = quadro_nome.upper() if quadro_nome else ""
            if "SAÚDE" in q_str or "SAUDE" in q_str or "MÉDICO" in q_str:
                saude += 1
            else:
                combatentes += 1

            # Calcula a idade exata
            if nascimento:
                idade = hoje.year - nascimento.year - \
                    ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
                soma_idades += idade
                total_idades += 1

    media_idade = round(soma_idades / total_idades,
                        1) if total_idades > 0 else 0

    return jsonify({
        "total": total,
        "media_idade": media_idade,
        "combatentes": combatentes,
        "saude": saude
    })


@mapa_bp.route('/api/media-idade-posto-manaus')
def api_media_idade_posto_manaus():
    """Retorna a média de idades por posto APENAS para Manaus."""
    query = database.session.query(
        PostoGrad.sigla,
        Militar.data_nascimento,
        Obm.sigla.label('obm_sigla')
    ).join(
        PostoGrad, PostoGrad.id == Militar.posto_grad_id
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id
    ).join(
        Obm, Obm.id == MilitarObmFuncao.obm_id
    ).filter(
        Militar.inativo.is_(False),
        Militar.posto_grad_id != 15,
        Militar.data_nascimento.isnot(None),
        MilitarObmFuncao.data_fim.is_(None)
    ).all()

    hoje = date.today()
    dados_idade = {}

    for posto_sigla, nascimento, obm_sigla in query:
        sigla_upper = obm_sigla.upper() if obm_sigla else ""
        is_manaus = True

        for cidade in COORDENADAS_CIDADES.keys():
            if cidade != "MANAUS" and cidade in sigla_upper:
                is_manaus = False
                break

        if is_manaus:
            idade = hoje.year - nascimento.year - \
                ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
            if posto_sigla not in dados_idade:
                dados_idade[posto_sigla] = []
            dados_idade[posto_sigla].append(idade)

    ordem_hierarquica = [
        'CEL', 'TC', 'MAJ', 'CAP', '1º TEN', '2º TEN', 'ASP', 'AL OF',
        'ALUNO OFICIAL', 'SUBTENENTE', '1º SGT', '2º SGT', '3º SGT',
        'AL SGT', 'CB', 'AL SD', 'SD'
    ]

    resultado = []

    # Respeita a ordem hierárquica no gráfico
    for sigla in ordem_hierarquica:
        if sigla in dados_idade and len(dados_idade[sigla]) > 0:
            media = sum(dados_idade[sigla]) / len(dados_idade[sigla])
            resultado.append({"posto": sigla, "media": round(media, 1)})

    # Adiciona eventuais postos que não estejam na lista
    for sigla, idades in dados_idade.items():
        if sigla not in ordem_hierarquica and len(idades) > 0:
            media = sum(idades) / len(idades)
            resultado.append({"posto": sigla, "media": round(media, 1)})

    return jsonify(resultado)
