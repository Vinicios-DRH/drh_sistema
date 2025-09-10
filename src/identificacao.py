import re
from sqlalchemy import func, cast, String
from src.models import Militar, FichaAlunos, MilitarObmFuncao

from datetime import datetime
from src import database as db

# Mantém seu normalizador de matrícula
def normaliza_matricula(valor: str) -> str:
    if not valor:
        return ""
    return re.sub(r'[^0-9A-Z]', '', valor.strip().upper())

def _query_por_cpf(model_cls, cpf_num: str, coluna_cpf):
    """Busca genérica por CPF, ignorando máscara/pontos/traços no BD."""
    return (model_cls.query
            .filter(func.regexp_replace(cast(coluna_cpf, String), r'[^0-9]', '', 'g') == cpf_num)
            .first())

def buscar_pessoa_por_cpf(cpf_formatado: str):
    """
    Tenta achar CPF em Militar OU FichaAlunos.
    Retorna dict: { 'tipo': 'militar'|'aluno', 'obj': <instância> } ou None.
    """
    if not cpf_formatado:
        return None

    # Só dígitos do CPF formatado
    cpf_num = re.sub(r'\D', '', cpf_formatado)

    # 1) Militar
    mil = _query_por_cpf(Militar, cpf_num, Militar.cpf)
    if mil:
        return {'tipo': 'militar', 'obj': mil}

    # 2) Aluno
    alu = _query_por_cpf(FichaAlunos, cpf_num, FichaAlunos.cpf)
    if alu:
        return {'tipo': 'aluno', 'obj': alu}

    return None

def get_aluno_por_user(user):
    """Busca FichaAlunos pelo CPF do User (ignorando máscara)."""
    cpf = getattr(user, "cpf", None) or ""
    cpf_num = re.sub(r"\D", "", cpf)
    if not cpf_num:
        return None
    return (
        FichaAlunos.query
        .filter(func.regexp_replace(cast(FichaAlunos.cpf, String), r'[^0-9]', '', 'g') == cpf_num)
        .first()
    )


def ensure_militar_from_aluno(aluno, user=None, obm_padrao=26, funcao_padrao=27):
    """
    Garante que exista um Militar espelhando o aluno.
    - Procura por CPF, depois por matrícula.
    - Se não existir, cria com campos mínimos + P/G, Quadro e Situação.
    - Garante um MOF ativo (tipo 1) com obm/funcao padrão.
    Retorna o objeto Militar.
    """
    # 1) tenta achar por CPF
    m = None
    if getattr(aluno, "cpf", None):
        m = Militar.query.filter_by(cpf=aluno.cpf).first()

    # 2) tenta por matrícula, se ainda não achou
    if not m and getattr(aluno, "matricula", None):
        m = Militar.query.filter_by(matricula=aluno.matricula).first()

    if not m:
        # 3) cria militar mínimo + campos requeridos pelos fluxos
        m = Militar(
            nome_completo=(aluno.nome_completo or "").strip(),
            cpf=(aluno.cpf or "").strip(),
            matricula=(aluno.matricula or "").strip(),
            # mínimos para seus formulários/consultas:
            posto_grad_id=17,
            quadro_id=1,
            situacao_id=9,          # "ALUNO" (ou o que 9 representa)
            pronto="SIM",           # opcional; ajuste se preferir None
            inativo=False,
            data_criacao=datetime.utcnow(),
        )
        if user and hasattr(Militar, "usuario_id"):
            m.usuario_id = getattr(user, "id", None)

        db.session.add(m)
        db.session.flush()  # garante m.id

    # 4) garante MOF ativo (tipo=1) para OBM/funcao padrão
    mof_ativo = (
        MilitarObmFuncao.query
        .filter(
            MilitarObmFuncao.militar_id == m.id,
            MilitarObmFuncao.data_fim.is_(None),
            MilitarObmFuncao.tipo == 1
        )
        .first()
    )

    if not mof_ativo:
        mof_ativo = MilitarObmFuncao(
            militar_id=m.id,
            obm_id=obm_padrao,     # 26
            funcao_id=funcao_padrao,  # 27
            tipo=1,
            data_criacao=datetime.utcnow(),
            data_fim=None,
        )
        db.session.add(mof_ativo)
    else:
        # se já existe, mas com OBM/Função diferentes, atualiza para o padrão
        changed = False
        if mof_ativo.obm_id != obm_padrao:
            mof_ativo.obm_id = obm_padrao
            changed = True
        if mof_ativo.funcao_id != funcao_padrao:
            mof_ativo.funcao_id = funcao_padrao
            changed = True
        if changed:
            db.session.add(mof_ativo)

    # 5) commit único
    db.session.commit()
    return m
