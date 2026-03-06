import requests
from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer

CBMAM_EMAIL_GATEWAY_URL = "https://www.cbm.am.gov.br/drh/servidor/apiEnviarEmail"


def send_email(to: str, name: str, subject: str, html_message: str, timeout: int = 30) -> dict:
    params = {
        "to": to,
        "name": name or "",
        "subject": subject,
        "message": html_message,
    }

    response = requests.get(CBMAM_EMAIL_GATEWAY_URL,
                            params=params, timeout=timeout)
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
    reset_url = url_for("resetar_senha_publica", token=token, _external=True)

    area_label = "área administrativa" if area == "admin" else "área militar"

    subject = "CBMAM | DP - Redefinição de Senha"

    html = f"""
    <div style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, Helvetica, sans-serif; color:#1f2937;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f6f8; padding:32px 0;">
            <tr>
                <td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0"
                        style="max-width:680px; background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 8px 30px rgba(0,0,0,0.08);">

                        <tr>
                            <td style="background:linear-gradient(135deg, #0b3d91, #0f4fbf); padding:28px 32px; text-align:center;">
                                <div style="font-size:13px; letter-spacing:1px; color:#dbeafe; font-weight:bold;">
                                    CORPO DE BOMBEIROS MILITAR DO AMAZONAS
                                </div>
                                <div style="font-size:22px; color:#ffffff; font-weight:700; margin-top:8px;">
                                    Diretoria de Pessoal
                                </div>
                                <div style="font-size:14px; color:#dbeafe; margin-top:6px;">
                                    Redefinição de senha de acesso
                                </div>
                            </td>
                        </tr>

                        <tr>
                            <td style="padding:36px 32px;">
                                <p style="margin:0 0 18px 0; font-size:16px; line-height:1.6;">
                                    Prezado(a) <strong>{user.nome or 'usuário(a)'}</strong>,
                                </p>

                                <p style="margin:0 0 16px 0; font-size:15px; line-height:1.7; color:#374151;">
                                    Informamos que foi registrada uma solicitação de redefinição de senha para acesso à <strong>{area_label}</strong>
                                    do sistema da Diretoria de Pessoal do CBMAM.
                                </p>

                                <p style="margin:0 0 24px 0; font-size:15px; line-height:1.7; color:#374151;">
                                    Para cadastrar uma nova senha, clique no botão abaixo:
                                </p>

                                <div style="text-align:center; margin:30px 0;">
                                    <a href="{reset_url}"
                                        style="background:#dc2626; color:#ffffff; text-decoration:none; padding:14px 28px;
                                            border-radius:8px; display:inline-block; font-size:15px; font-weight:700;
                                            letter-spacing:.3px; box-shadow:0 6px 18px rgba(220,38,38,.25);">
                                        REDEFINIR MINHA SENHA
                                    </a>
                                </div>

                                <div style="margin:28px 0 0 0; padding:18px; background:#f9fafb; border-left:4px solid #0f4fbf; border-radius:8px;">
                                    <p style="margin:0 0 10px 0; font-size:14px; font-weight:700; color:#111827;">
                                        Importante:
                                    </p>
                                    <p style="margin:0 0 8px 0; font-size:14px; line-height:1.6; color:#4b5563;">
                                        Este link possui validade de <strong>30 minutos</strong>.
                                    </p>
                                    <p style="margin:0; font-size:14px; line-height:1.6; color:#4b5563;">
                                        Caso o botão acima não funcione, copie e cole o endereço abaixo em seu navegador:
                                    </p>
                                    <p style="margin:12px 0 0 0; font-size:13px; line-height:1.6; word-break:break-all; color:#0f4fbf;">
                                        {reset_url}
                                    </p>
                                </div>

                                <p style="margin:28px 0 0 0; font-size:14px; line-height:1.7; color:#4b5563;">
                                    Se você não realizou esta solicitação, desconsidere esta mensagem. Sua senha atual permanecerá válida
                                    até que uma nova seja cadastrada por meio do link acima.
                                </p>

                                <p style="margin:32px 0 0 0; font-size:15px; line-height:1.7; color:#374151;">
                                    Atenciosamente,<br>
                                    <strong>Diretoria de Pessoal</strong><br>
                                    Corpo de Bombeiros Militar do Amazonas
                                </p>
                            </td>
                        </tr>

                        <tr>
                            <td style="background:#f3f4f6; padding:18px 24px; text-align:center; font-size:12px; color:#6b7280; line-height:1.6;">
                                Esta é uma mensagem automática do sistema BM-6/CBMAM.<br>
                                Por favor, não responda este e-mail.
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
    </div>
    """

    return send_email(
        to=user.email,
        name=user.nome or "",
        subject=subject,
        html_message=html
    )
