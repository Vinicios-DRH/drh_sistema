import re

import requests
from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer

CBMAM_EMAIL_GATEWAY_URL = "https://www.cbm.am.gov.br/drh/servidor/apiEnviarEmail"


def build_public_reset_url(token: str) -> str:
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base_url}/resetar-senha/{token}"


def send_email(to: str, name: str, subject: str, html_message: str, timeout: int = 30) -> dict:
    params = {
        "to": to,
        "name": name or "",
        "subject": subject,
        "message": html_message,
    }

    response = requests.get(
        CBMAM_EMAIL_GATEWAY_URL,
        params=params,
        timeout=timeout
    )
    response.raise_for_status()
    return response.json()


def _get_reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_password_reset_token(user_id: int, area: str) -> str:
    serializer = _get_reset_serializer()
    return serializer.dumps(
        {"user_id": user_id, "area": area},
        salt="reset-senha-cbmam"
    )


def verify_password_reset_token(token: str, max_age: int = 1800) -> dict | None:
    serializer = _get_reset_serializer()
    try:
        data = serializer.loads(
            token,
            salt="reset-senha-cbmam",
            max_age=max_age
        )
        return data
    except Exception:
        return None


def send_reset_password_email(user, area: str) -> dict:
    token = generate_password_reset_token(user.id, area)
    reset_url = build_public_reset_url(token)

    area_label = "área administrativa" if area == "admin" else "área militar"
    subject = "CBMAM | DP - Redefinição de Senha"

    html = f"""
    <div style="font-family:Arial,sans-serif;background:#f4f6f8;padding:20px">
    <div style="max-width:540px;margin:auto;background:#fff;border:1px solid #d0d7de">
        
        <div style="background:#0f4fbf;color:#fff;padding:16px;text-align:center">
        <b>Corpo de Bombeiros Militar do Amazonas</b><br>
        Diretoria de Pessoal
        </div>

        <div style="padding:22px;color:#1f2937">

        <p>Prezado(a) <b>{user.nome or 'usuário(a)'}</b>,</p>

        <p>
        Foi registrada uma solicitação de redefinição de senha para acesso à
        <b>{area_label}</b>.
        </p>

        <p style="text-align:center;margin:24px 0">
            <a href="{reset_url}"
            style="background:#dc2626;color:#fff;text-decoration:none;
            padding:12px 20px;border-radius:6px;font-weight:bold">
            REDEFINIR SENHA
            </a>
        </p>

        <p><b>Validade do link:</b> 30 minutos.</p>

        <p style="font-size:12px;color:#555">
        Caso o botão não funcione, utilize o link abaixo:
        </p>

        <p style="font-size:12px;color:#0f4fbf;word-break:break-all">
        {reset_url}
        </p>

        <p style="font-size:13px;color:#555">
        Se você não solicitou esta alteração, ignore este e-mail.
        </p>

        </div>

        <div style="background:#f3f4f6;padding:12px;text-align:center;font-size:12px;color:#6b7280">
        Sistema BM-6 / CBMAM • Mensagem automática
        </div>

    </div>
    </div>
    """
    # minifica o HTML para caber melhor na URL
    html = re.sub(r">\s+<", "><", html)
    html = re.sub(r"\s{2,}", " ", html).strip()

    return send_email(
        to=user.email,
        name=user.nome or "",
        subject=subject,
        html_message=html
    )
