# src/utils/sa_serialize.py

from datetime import date, datetime, time
from sqlalchemy.inspection import inspect as sa_inspect

def sa_to_dict(obj, visited=None, depth=4, root_class=None):
    """
    Converte uma instância SQLAlchemy em dict, incluindo relacionamentos.

    - depth: profundidade de relacionamento (4 já costuma ser suficiente)
    - root_class: classe raiz (Militar) para evitar ficar voltando pra ela
    """
    if obj is None:
        return None

    if visited is None:
        visited = set()

    if root_class is None:
        root_class = obj.__class__

    mapper = sa_inspect(obj.__class__)

    # identidade única pra evitar loop
    pk = tuple(getattr(obj, col.key) for col in mapper.primary_key)
    identity = (obj.__class__, pk)
    if identity in visited:
        return f"<ciclo {obj.__class__.__name__} {pk}>"

    visited.add(identity)

    data = {}

    # 1) Colunas
    for col in mapper.columns:
        valor = getattr(obj, col.key)

        if isinstance(valor, (date, datetime, time)):
            data[col.key] = valor.isoformat() if valor else None
        else:
            data[col.key] = valor

    # 2) Relacionamentos
    if depth <= 0:
        return data

    for rel in mapper.relationships:
        # não voltar pra root_class (ex.: Declaracao -> Militar -> ...)
        if rel.mapper.class_ is root_class and obj.__class__ is not root_class:
            continue

        valor_rel = getattr(obj, rel.key)

        if valor_rel is None:
            data[rel.key] = None
        elif rel.uselist:
            data[rel.key] = [
                sa_to_dict(
                    child,
                    visited=visited,
                    depth=depth - 1,
                    root_class=root_class
                )
                for child in valor_rel
            ]
        else:
            data[rel.key] = sa_to_dict(
                valor_rel,
                visited=visited,
                depth=depth - 1,
                root_class=root_class
            )

    return data
