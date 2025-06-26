from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

# Decorador para verificar a ocupação do usuário


def checar_ocupacao(*ocupacoes_permitidas):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verifica se o usuário tem uma ocupação associada
            if not current_user.user_funcao or current_user.user_funcao.ocupacao not in ocupacoes_permitidas:
                flash('Acesso negado', 'alert-danger')
                return redirect(url_for('acesso_negado'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
