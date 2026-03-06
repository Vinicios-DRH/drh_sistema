# src/decorators/password_utils.py
import secrets
import string


def generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    # senha forte sem caracteres “confusos” é opcional, mas isso aqui já é ok.
    return "".join(secrets.choice(alphabet) for _ in range(length))
