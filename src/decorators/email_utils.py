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
    <div style="font:14px Arial,sans-serif;background:#f4f6f8;padding:20px">
      <div style="max-width:560px;margin:auto;background:#fff;border:1px solid #dbe2ea">
        <div style="background:#0f4fbf;color:#fff;padding:16px;text-align:center;font-weight:700">
          CBMAM | Diretoria de Pessoal
        </div>
        <div style="padding:22px;color:#1f2937">
          <p>Prezado(a), <b>{user.nome or 'usuário(a)'}</b>.</p>
          <p>Recebemos uma solicitação para redefinição de senha da <b>{area_label}</b>.</p>
          <p style="text-align:center;margin:22px 0">
            <a href="{reset_url}" style="background:#dc2626;color:#fff;text-decoration:none;padding:12px 18px;border-radius:6px;font-weight:700;display:inline-block">
              REDEFINIR SENHA
            </a>
          </p>
          <p><b>Validade:</b> 30 minutos.</p>
          <p style="font-size:12px;word-break:break-all;color:#0f4fbf">{reset_url}</p>
          <p>Se não foi você, ignore esta mensagem.</p>
        </div>
        <div style="background:#f3f4f6;padding:12px;text-align:center;font-size:12px;color:#6b7280">
          Mensagem automática do sistema BM-6/CBMAM.
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
