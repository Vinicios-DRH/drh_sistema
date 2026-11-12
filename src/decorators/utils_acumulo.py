# utils_acumulo.py
import os
import time
import uuid
import mimetypes
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
import boto3
import botocore.auth
import botocore.utils
from botocore.config import Config
from io import BytesIO
from uuid import uuid4
import requests
from werkzeug.utils import secure_filename

# --------- Ajuste automático de Clock Skew para SigV4 (Backblaze B2) ---------
_b2_clock_offset = timedelta(0)
_b2_clock_synced_at = 0.0


def _patched_get_current_datetime(remove_tzinfo=True):
    dt = datetime.now(timezone.utc) + _b2_clock_offset
    if remove_tzinfo:
        dt = dt.replace(tzinfo=None)
    return dt


botocore.auth.get_current_datetime = _patched_get_current_datetime
botocore.utils.get_current_datetime = _patched_get_current_datetime


def _sync_b2_clock(endpoint: str):
    """Sincroniza o offset de relógio com o endpoint S3/B2 para evitar falhas
    de assinatura SigV4 ('Timestamp is in the future') se o relógio do SO desalinhar."""
    global _b2_clock_offset, _b2_clock_synced_at
    now_mono = time.monotonic()
    if _b2_clock_synced_at and (now_mono - _b2_clock_synced_at) < 300:
        return
    try:
        resp = requests.head(endpoint, timeout=5)
        date_hdr = resp.headers.get("Date")
        if date_hdr:
            server_dt = parsedate_to_datetime(date_hdr)
            if server_dt.tzinfo is None:
                server_dt = server_dt.replace(tzinfo=timezone.utc)
            else:
                server_dt = server_dt.astimezone(timezone.utc)
            local_dt = datetime.now(timezone.utc)
            diff = server_dt - local_dt
            _b2_clock_offset = diff if abs(diff.total_seconds()) > 60 else timedelta(0)
            _b2_clock_synced_at = now_mono
    except Exception:
        pass


# --------- Credenciais / Config ---------


def _secret_key():
    # tenta pegar do Flask (o mesmo SECRET_KEY do app)
    try:
        k = current_app.config.get("SECRET_KEY")
        if k:
            return k
    except RuntimeError:
        pass
    # fallback: variável de ambiente
    k = os.getenv("SECRET_KEY")
    if not k:
        raise RuntimeError(
            "SECRET_KEY não definido (Flask config ou variável de ambiente).")
    return k


def _required_env(name: str) -> str:
    v = os.getenv(name)
    if not v or not v.strip():
        raise RuntimeError(f"Variável de ambiente {name} ausente.")
    return v.strip()


def b2_client():
    endpoint = _required_env("B2_ENDPOINT")
    key_id = _required_env("B2_KEY_ID")
    app_key = _required_env("B2_APP_KEY")
    region = os.getenv("B2_REGION", "").strip(
    ) or endpoint.split("//")[1].split(".")[1]

    _sync_b2_clock(endpoint)

    cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
        region_name=region,
        config=cfg,
    )


def _signer():
    return URLSafeTimedSerializer(_secret_key(), salt="acumulo-cargos")

# --------- Tokens de convite ---------


def make_invite_token(militar_id: int, ano: int):
    return _signer().dumps({"militar_id": militar_id, "ano": ano})


def load_invite_token(token: str, max_age_hours=14*24):
    return _signer().loads(token, max_age=max_age_hours * 3600)

# --------- Upload / Download Backblaze ---------


def b2_bucket_name() -> str:
    return _required_env("B2_BUCKET_NAME")


def b2_upload_fileobj(file_storage, key_prefix="acumulo"):
    """
    Sobe o arquivo para o bucket privado e retorna apenas a object_key
    (guarde essa key no banco).
    """
    s3 = b2_client()
    ctype = file_storage.mimetype or mimetypes.guess_type(
        file_storage.filename)[0] or "application/octet-stream"
    ext = os.path.splitext(file_storage.filename or "")[1].lower() or ".bin"
    object_key = f"{key_prefix}/{uuid.uuid4().hex}{ext}"

    s3.upload_fileobj(
        Fileobj=file_storage.stream,
        Bucket=b2_bucket_name(),
        Key=object_key,
        ExtraArgs={"ContentType": ctype}  # SSE-B2 default se ligado no bucket
    )
    return object_key


def b2_presigned_get(object_key: str, expires_seconds=3600, download_name: str | None = None):
    """
    Gera URL temporária (bucket privado).
    Se 'download_name' for passado, força Content-Disposition para baixar com esse nome.
    """
    s3 = b2_client()
    params = {"Bucket": b2_bucket_name(), "Key": object_key}
    if download_name:
        nome_seguro = secure_filename(download_name) or "documento"
        params["ResponseContentDisposition"] = (
            f'attachment; filename="{nome_seguro}"'
        )
    return s3.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_seconds)

# --------- Helpers opcionais ---------


def build_prefix(ano: int, militar_id: int) -> str:
    """Use assim: key_prefix=build_prefix(ano, militar_id)"""
    return f"acumulo/{ano}/{militar_id}"


def build_prefix_dependente(ano: int, militar_id: int, protocolo: str) -> str:
    """
    Ex: acumulo/2025/123/dependentes/PROTOCOLO-XYZ
    """
    return f"acumulo/{ano}/{militar_id}/dependentes/{protocolo}"


def b2_check():
    s3 = b2_client()
    print("endpoint:", os.getenv("B2_ENDPOINT"))
    print("bucket:", b2_bucket_name())
    s3.head_bucket(Bucket=b2_bucket_name())


def b2_put_test():
    s3 = b2_client()
    key = f"acumulo/test-{uuid4().hex}.txt"
    s3.put_object(
        Bucket=b2_bucket_name(),
        Key=key,
        Body=BytesIO(b"ok"),
        ContentType="text/plain",
    )
    print("OK:", key)


# utils_acumulo.py
def b2_delete_all_versions(key: str):
    s3 = b2_client()
    resp = s3.list_object_versions(Bucket=b2_bucket_name(), Prefix=key)
    to_delete = []
    for v in resp.get("Versions", []) + resp.get("DeleteMarkers", []):
        if v.get("Key") == key:
            to_delete.append({"Key": key, "VersionId": v["VersionId"]})
    if to_delete:
        s3.delete_objects(Bucket=b2_bucket_name(), Delete={"Objects": to_delete})
