import re
import json
import time
import requests

obms_sql = """
('1', '1 BI'), ('2', 'ABMAM'), ('3', 'AJAI'), ('4', 'AJUDANCIA GERAL'), ('5', 'BBE'),
('6', 'BBE/PELOTÃO FLUVIAL'), ('7', 'BIFMA'), ('8', 'BM1-SJD'), ('9', 'BM-2'),
('10', 'BM-3'), ('11', 'BM-4'), ('13', 'BM-5'), ('14', 'BM-6'), ('15', 'CBC'),
('16', 'CBI'), ('17', 'CBI/1 CIBM/1 PDBM/RIO PRETO DA EVA'),
('18', 'CBI/1 CIBM/2 PDBM/HUMAITÁ'), ('19', 'CBI/1 CIBM/3 PDBM PRESIDENTE FIGUEIREDO'),
('20', 'CBI/1 CIBM/ITACOATIARA'), ('21', 'CBI/1 PIBM/TEFÉ'),
('22', 'CBI/2 CIBM/MANACAPURU'), ('23', 'CBI/2 CIBM/2 PDBM/NOVO AIRÃO'),
('24', 'CBI/2 PIBM/TABATINGA'), ('25', 'CBI/3 CIBM/PARINTINS'),
('26', 'CFAP'), ('27', 'CIA CG'), ('28', 'CMBM'), ('29', 'COBOM'),
('30', 'CONTROLADORIA'), ('31', 'CORREGEDORIA/CBMAM'), ('32', 'CSM'),
('33', 'DAT'), ('34', 'DF'), ('35', 'DFEP'), ('36', 'DL'), ('37', 'DRH'),
('38', 'DS'), ('39', 'EMG'), ('40', 'FCECON'), ('41', 'FUNESBOM'),
('42', 'GAB CMT GERAL'), ('43', 'GAB SUBCMT-GERAL'), ('44', 'GRAPH'),
('45', 'GSE'), ('46', 'JOIS'), ('47', 'OUVIDORIA'), ('48', 'PGGM'),
('49', 'PMAM'), ('50', 'PROVIDA'), ('51', 'SCI'), ('52', 'SJD'),
('53', 'SUBCOMADEC'), ('54', 'CBI/1 PDBM/IRANDUBA'), ('55', 'A DEFINIR')
"""

# Coordenadas padrão de Manaus
manaus_lat, manaus_lon = -3.1, -60.02

def buscar_coordenadas(cidade):
    try:
        url = f"https://nominatim.openstreetmap.org/search?city={cidade}&state=Amazonas&country=Brazil&format=json"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = response.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except:
        pass
    return manaus_lat, manaus_lon

obms = re.findall(r"\('(\d+)', '([^']+)'\)", obms_sql)
resultado = []

for obm_id, nome in obms:
    if "CBI" in nome and "/" in nome:
        cidade = nome.split("/")[-1].split()[0].title()
        lat, lon = buscar_coordenadas(cidade)
    else:
        cidade = "Manaus"
        lat, lon = manaus_lat, manaus_lon

    resultado.append({
        "id": int(obm_id),
        "nome": nome,
        "cidade": cidade,
        "latitude": lat,
        "longitude": lon
    })

    time.sleep(1)

# Salva o JSON final
with open("obm_coords.json", "w", encoding="utf-8") as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)

print("✅ Arquivo obm_coords.json gerado com sucesso!")
