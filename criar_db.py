from src import app, database as db
from src.models import User, FuncaoUser, UserPermissao

with app.app_context():
    CODES = ["MILITAR_READ", "MILITAR_CREATE", "MILITAR_UPDATE", "MILITAR_DELETE",
             "FERIAS_READ", "FERIAS_CREATE", "FERIAS_UPDATE", "FERIAS_DELETE"]

    drh_users = (db.session.query(User)
                .join(FuncaoUser, User.funcao_user_id == FuncaoUser.id)
                .filter(FuncaoUser.ocupacao == "DRH")  # ajuste campo/valor
                .all())

    for u in drh_users:
        for code in CODES:
            row = (db.session.query(UserPermissao)
                .filter_by(user_id=u.id, codigo=code)
                .first())
            if row is None:
                db.session.add(UserPermissao(
                    user_id=u.id, codigo=code, ativo=True))

    db.session.commit()
    print("OK")
