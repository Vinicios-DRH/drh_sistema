from flask import Blueprint, render_template, jsonify
from sqlalchemy.orm import aliased
from src import database  # Ajuste a importação do banco conforme seu projeto
from src.models import Militar, Obm, MilitarObmFuncao, PostoGrad

mapa_bp = Blueprint('mapa_amazonas', __name__)

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


@mapa_bp.route('/mapa-efetivo')
def renderizar_mapa():
    return render_template('mapa_amazonas.html')


@mapa_bp.route('/api/mapa-dados')
def api_dados_mapa():
    # Incluímos o Obm.id na pesquisa
    query = database.session.query(
        Obm.id,
        Obm.sigla,
        database.func.count(Militar.id).label('total_efetivo')
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.obm_id == Obm.id
    ).join(
        Militar, Militar.id == MilitarObmFuncao.militar_id
    ).filter(
        Militar.posto_grad_id != 15,
        MilitarObmFuncao.data_fim.is_(None)
    ).group_by(Obm.id, Obm.sigla).all()

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
            "lng": lng
        })

    return jsonify(resultado)


@mapa_bp.route('/api/militares-obm/<int:obm_id>')
def api_militares_obm(obm_id):
    """Nova rota para listar os militares de uma OBM específica."""
    query = database.session.query(
        Militar, PostoGrad
    ).join(
        MilitarObmFuncao, MilitarObmFuncao.militar_id == Militar.id
    ).join(
        PostoGrad, PostoGrad.id == Militar.posto_grad_id
    ).filter(
        MilitarObmFuncao.obm_id == obm_id,
        MilitarObmFuncao.data_fim.is_(None),
        Militar.posto_grad_id != 15
    ).order_by(PostoGrad.id).all()  # Ordena por patente (dependendo de como os IDs estão no seu banco)

    resultado = []
    for militar, posto in query:
        resultado.append({
            "nome": militar.nome_guerra if militar.nome_guerra else militar.nome_completo,
            "posto": posto.sigla
        })

    return jsonify(resultado)
