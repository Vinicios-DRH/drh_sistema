from flask import Blueprint, render_template, jsonify
from sqlalchemy.orm import aliased
from sqlalchemy import case
from datetime import date
from src import database
from src.models import Militar, Obm, MilitarObmFuncao, PostoGrad, Funcao, MilitarContatoEmergencia
from src.querys import obter_estatisticas_militares

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
def api_dados_mapa():
    # 1. Query principal que você já tem (OBM + Total Efetivo)
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

    # 2. Nova Query para buscar quem está nos cargos de comando em cada OBM
    FUNCOES_COMANDO = [1, 2, 3, 4, 5, 9, 10, 11,
                       12, 24]  # IDs dos cargos de liderança
    comandantes_query = database.session.query(
        MilitarObmFuncao.obm_id,
        Militar.nome_guerra,
        Militar.nome_completo,
        PostoGrad.sigla
    ).join(
        Militar, Militar.id == MilitarObmFuncao.militar_id
    ).outerjoin(
        PostoGrad, PostoGrad.id == Militar.posto_grad_id
    ).filter(
        MilitarObmFuncao.data_fim.is_(None),
        MilitarObmFuncao.funcao_id.in_(FUNCOES_COMANDO)
    ).all()

    # 3. Monta um dicionário para acessar o nome do comandante rapidamente pelo obm_id
    comandantes_dict = {}
    for obm_id, nome_guerra, nome_completo, posto_sigla in comandantes_query:
        if obm_id not in comandantes_dict:  # Pega o primeiro líder encontrado
            nome = nome_guerra if nome_guerra else nome_completo
            posto = posto_sigla if posto_sigla else ""
            comandantes_dict[obm_id] = f"{posto} {nome}".strip()

    resultado = []

    for obm_id, sigla, efetivo in query:
        sigla_upper = sigla.upper()
        cidade_destino = "MANAUS"

        for cidade in COORDENADAS_CIDADES.keys():
            if cidade != "MANAUS" and cidade in sigla_upper:
                cidade_destino = cidade
                break

        import random
        lat_base, lng_base = COORDENADAS_CIDADES[cidade_destino]

        lat = lat_base + \
            random.uniform(-0.015,
                           0.015) if cidade_destino == "MANAUS" else lat_base
        lng = lng_base + \
            random.uniform(-0.015,
                           0.015) if cidade_destino == "MANAUS" else lng_base

        resultado.append({
            "obm_id": obm_id,
            "obm": sigla,
            "efetivo": efetivo,
            "cidade": cidade_destino,
            "lat": lat,
            "lng": lng,
            # Insere o nome do comandante (ou uma mensagem caso a unidade esteja sem)
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
        idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
        
        if sigla not in dados_idade:
            dados_idade[sigla] = []
        dados_idade[sigla].append(idade)

    # 3. Define a ordem hierárquica para o gráfico ficar organizado
    ordem_hierarquica = [
        'CEL', 'TC', 'MAJ', 'CAP', '1 TEN', '2 TEN', 'ASP', 'AL OF', 
        'ALUNO OFICIAL', 'SUBTENENTE', '1 SGT', '2 SGT', '3 SGT', 
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
def api_militares_obm(obm_id):
    ordem_hierarquica = case(
        {
            'CEL': 1, 'TC': 2, 'MAJ': 3, 'CAP': 4,
            '1 TEN': 5, '2 TEN': 6, 'ASP': 7, 'AL OF': 8,
            'ALUNO OFICIAL': 9, 'SUBTENENTE': 10, '1 SGT': 11,
            '2 SGT': 12, '3 SGT': 13, 'AL SGT': 14,
            'CB': 15, 'AL SD': 16, 'SD': 17
        },
        value=database.func.upper(PostoGrad.sigla),
        else_=99
    )

    # Adicionamos MilitarContatoEmergencia na query e nos outerjoins
    query = database.session.query(
        Militar, PostoGrad, MilitarObmFuncao, Funcao, MilitarContatoEmergencia
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id
    ).outerjoin(
        PostoGrad, PostoGrad.id == Militar.posto_grad_id
    ).outerjoin(
        Funcao, Funcao.id == MilitarObmFuncao.funcao_id
    ).outerjoin(
        MilitarContatoEmergencia, MilitarContatoEmergencia.militar_id == Militar.id
    ).filter(
        MilitarObmFuncao.obm_id == obm_id,
        MilitarObmFuncao.data_fim.is_(None),
        Militar.posto_grad_id != 15
    ).order_by(
        ordem_hierarquica,
        Militar.antiguidade.asc()
    ).all()

    resultado_militares = []
    estatisticas_posto = {}
    militares_vistos = set()

    FUNCOES_COMANDO = [1, 2, 3, 4, 5, 9, 10, 11, 12, 24]

    # Mapeamento de prioridade para as funções (menor = aparece mais em cima)
    PESO_FUNCAO = {
        4: 1,   # COMANDANTE GERAL
        5: 2,   # CHEFE DO ESTADO MAIOR
        2: 3,   # DIRETOR
        3: 4,   # COMANDANTE
        1: 5,   # CHEFE
        11: 6,  # CMT PELOTÃO DE GUARDA-VIDAS
        12: 7,  # CMT PELOTÃO FLUVIAL
        10: 8,  # SUB DIRETOR
        9: 9,   # SUBCOMANDANTE
        24: 10  # SUB CHEFE
    }

    for militar, posto, m_funcao, funcao, contato_emergencia in query:
        if militar.id not in militares_vistos:
            militares_vistos.add(militar.id)
            sigla_posto = posto.sigla if posto else "S/P"

            funcao_id = m_funcao.funcao_id if m_funcao else None
            is_comandante = funcao_id in FUNCOES_COMANDO
            nome_funcao = funcao.ocupacao if funcao else ""
            # Pega o peso, se não for comando, joga pro final (99)
            peso = PESO_FUNCAO.get(funcao_id, 99)

            # Extração dos dados de contato com tratamento caso sejam nulos
            celular = militar.celular if militar.celular else "Não informado"
            contato_nome = contato_emergencia.nome if contato_emergencia else "Nenhum cadastrado"
            contato_tel = contato_emergencia.telefone if contato_emergencia else "---"

            resultado_militares.append({
                "nome": militar.nome_guerra if militar.nome_guerra else militar.nome_completo,
                "posto": sigla_posto,
                "is_comandante": is_comandante,
                "funcao": nome_funcao,
                "celular": celular,
                "contato_emergencia_nome": contato_nome,
                "contato_emergencia_tel": contato_tel,
                "peso_funcao": peso
            })

            estatisticas_posto[sigla_posto] = estatisticas_posto.get(
                sigla_posto, 0) + 1

    # Ordena garantindo: 1º É comando?, 2º Qual o peso da Função?, 3º Rank do Banco (Estável)
    # O .sort() do Python é estável, então o resto da tropa vai manter a ordem hierárquica do BD certinha.
    resultado_militares.sort(key=lambda x: (
        not x["is_comandante"], x["peso_funcao"]))

    return jsonify({
        "militares": resultado_militares,
        "stats": estatisticas_posto
    })
