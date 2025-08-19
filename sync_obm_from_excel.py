# scripts/sync_obm_from_excel.py
import re
import sys
import math
import argparse
from datetime import datetime
import pandas as pd

# ajuste se seu app factory/module for diferente
from src import app, database as db
from src.models import Militar, MilitarObmFuncao  # ajuste o caminho se necessário


def only_digits(s):
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    s = re.sub(r"\D", "", str(s))
    return s or None


def now_utc():
    return datetime.utcnow()


def load_mapping(xlsx_path, sheet_name=None):
    xls = pd.ExcelFile(xlsx_path)
    sheet = sheet_name or xls.sheet_names[0]
    df = pd.read_excel(xlsx_path, sheet_name=sheet)

    # normaliza nomes de colunas
    df.columns = [str(c).strip() for c in df.columns]

    # checa colunas necessárias
    needed = ["obm_id_1", "obm_id_2"]
    for c in needed:
        if c not in df.columns:
            raise RuntimeError(f"Coluna obrigatória ausente: {c}")

    # tenta identificar CPF e MATRICULA
    cpf_col = "CPF" if "CPF" in df.columns else None
    mat_col = "MATRÍCULA" if "MATRÍCULA" in df.columns else None
    if not cpf_col and not mat_col:
        raise RuntimeError("Nem CPF nem MATRÍCULA foram encontrados no Excel.")

    # constrói lista de dicts
    rows = []
    for _, r in df.iterrows():
        cpf = only_digits(r.get(cpf_col)) if cpf_col else None
        mat = str(r.get(mat_col)).strip() if mat_col and not pd.isna(
            r.get(mat_col)) else None

        obm1 = r.get("obm_id_1")
        obm2 = r.get("obm_id_2")

        # converte obm_ids para int ou None
        def to_int_or_none(x):
            if pd.isna(x):
                return None
            try:
                xi = int(x)
                return xi if xi > 0 else None
            except Exception:
                return None

        obm1 = to_int_or_none(obm1)
        obm2 = to_int_or_none(obm2)

        if cpf or mat:
            rows.append({
                "cpf": cpf,
                "matricula": mat,
                "obm_id_1": obm1,
                "obm_id_2": obm2
            })

    return rows


def find_militar(session, cpf, matricula):
    q = session.query(Militar)
    if cpf:
        m = q.filter(Militar.cpf == cpf).first()
        if m:
            return m
    if matricula:
        return session.query(Militar).filter(Militar.matricula == matricula).first()
    return None


def sync(session, rows, dry_run=False, default_funcao_id=None):
    inserted = 0
    closed = 0
    kept = 0
    moved = 0
    not_found = 0
    processed = 0

    for r in rows:
        processed += 1
        militar = find_militar(session, r["cpf"], r["matricula"])
        if not militar:
            not_found += 1
            continue

        target = []
        if r["obm_id_1"]:
            target.append((r["obm_id_1"], 1))
        if r["obm_id_2"]:
            target.append((r["obm_id_2"], 2))

        # buscar vínculos ativos atuais (tipo 1/2)
        ativos = session.query(MilitarObmFuncao)\
            .filter(
                MilitarObmFuncao.militar_id == militar.id,
                MilitarObmFuncao.data_fim.is_(None),
                MilitarObmFuncao.tipo.in_([1, 2])
        ).all()

        # índice por tipo
        ativos_by_tipo = {a.tipo: a for a in ativos}

        # 1) garantir/atualizar os alvos
        for obm_id, tipo in target:
            atual = ativos_by_tipo.get(tipo)
            if atual and atual.obm_id == obm_id:
                kept += 1
                continue

            # se existe registro ativo do mesmo tipo mas com obm diferente -> fechar e criar novo
            if atual:
                if not dry_run:
                    atual.data_fim = now_utc()
                closed += 1
                moved += 1

            # criar novo vínculo
            if not dry_run:
                novo = MilitarObmFuncao(
                    militar_id=militar.id,
                    obm_id=obm_id,
                    funcao_id=default_funcao_id,  # opcional
                    tipo=tipo,
                    data_criacao=now_utc()
                )
                session.add(novo)
            inserted += 1

        # 2) fechar vínculos ativos (tipo 1/2) que não estão mais na planilha
        target_set = {(obm_id, tipo) for obm_id, tipo in target}
        for a in ativos:
            if (a.obm_id, a.tipo) not in target_set:
                if not dry_run:
                    a.data_fim = now_utc()
                closed += 1

    if not dry_run:
        session.commit()

    return {
        "processed_rows": processed,
        "inserted": inserted,
        "closed": closed,
        "kept": kept,
        "moved": moved,
        "not_found": not_found,
        "dry_run": dry_run
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza militar_obm_funcao a partir de Excel.")
    parser.add_argument("--xlsx", required=True, help="Caminho do Excel")

    parser.add_argument("--sheet", default=None, help="Nome da aba (opcional)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Não grava nada; só simula")
    parser.add_argument("--default-funcao-id", type=int,
                        default=None, help="funcao_id padrão (opcional)")
    args = parser.parse_args()

    with app.app_context():
        rows = load_mapping(args.xlsx, args.sheet)
        with db.session.begin() as _:
            pass  # garante conexão

        # usa uma sessão fora do contexto 'begin' para commit manual
        session = db.session
        report = sync(session, rows, dry_run=args.dry_run,
                      default_funcao_id=args.default_funcao_id)
        print(report)


if __name__ == "__main__":
    sys.exit(main())
