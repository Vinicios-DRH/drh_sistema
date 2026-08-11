from flask import Blueprint, render_template, request, send_file, jsonify
from rembg import remove
from PIL import Image
from io import BytesIO
import os

remove_bg_bp = Blueprint("remove_bg", __name__, url_prefix="/imagens")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_FILE_SIZE_MB = 15


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def upscale_to_uhd_if_needed(img: Image.Image) -> Image.Image:
    """
    Se a imagem for menor que UHD (3840x2160), faz upscale proporcional.
    Mantém proporção sem cortar.
    """
    target_w, target_h = 3840, 2160
    w, h = img.size

    if w >= target_w or h >= target_h:
        return img

    ratio = min(target_w / w, target_h / h)
    new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
    return img.resize(new_size, Image.LANCZOS)


def crop_transparent_borders(img: Image.Image) -> Image.Image:
    """
    Recorta automaticamente as bordas transparentes com base no canal alpha.
    Versão compatível com Pillow sem usar alpha_only=True.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        return img.crop(bbox)
    return img


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """
    Converte cor hexadecimal (#RRGGBB) em RGB.
    """
    hex_color = (hex_color or "#FFFFFF").strip().lstrip("#")

    if len(hex_color) != 6:
        return (255, 255, 255)

    try:
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def apply_background(img: Image.Image, tipo_fundo: str, cor_fundo: str) -> Image.Image:
    """
    Aplica fundo branco ou sólido sobre uma imagem RGBA.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    if tipo_fundo == "transparent":
        return img

    if tipo_fundo == "white":
        bg_color = (255, 255, 255, 255)
    elif tipo_fundo == "solid":
        r, g, b = hex_to_rgb(cor_fundo)
        bg_color = (r, g, b, 255)
    else:
        return img

    background = Image.new("RGBA", img.size, bg_color)
    return Image.alpha_composite(background, img)


@remove_bg_bp.route("/remover-fundo", methods=["GET"])
def remover_fundo():
    return render_template("remover_fundo.html")


@remove_bg_bp.route("/remover-fundo/processar", methods=["POST"])
def processar_remocao_fundo():
    arquivo = request.files.get("imagem")

    modo_saida = request.form.get(
        "modo_saida", "original").lower()          # original | uhd
    formato_saida = request.form.get(
        "formato_saida", "png").lower()         # png | jpg
    # transparent | white | solid
    tipo_fundo = request.form.get("tipo_fundo", "transparent").lower()
    cor_fundo = request.form.get("cor_fundo", "#0b2e4f")

    recortar = request.form.get("recortar", "true").lower() == "true"
    compactar = request.form.get("compactar", "false").lower() == "true"

    try:
        compress_level = int(request.form.get("compress_level", 6))
    except ValueError:
        compress_level = 6

    compress_level = max(0, min(9, compress_level))

    if not arquivo or arquivo.filename == "":
        return jsonify({"erro": "Selecione uma imagem."}), 400

    if not allowed_file(arquivo.filename):
        return jsonify({"erro": "Formato inválido. Envie PNG, JPG, JPEG ou WEBP."}), 400

    arquivo.seek(0, os.SEEK_END)
    file_size = arquivo.tell()
    arquivo.seek(0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return jsonify({"erro": f"A imagem excede o limite de {MAX_FILE_SIZE_MB} MB."}), 400

    if formato_saida not in {"png", "jpg"}:
        formato_saida = "png"

    if tipo_fundo not in {"transparent", "white", "solid"}:
        tipo_fundo = "transparent"

    # JPG não suporta transparência
    if formato_saida == "jpg" and tipo_fundo == "transparent":
        tipo_fundo = "white"

    try:
        input_bytes = arquivo.read()

        # remove fundo
        output_bytes = remove(input_bytes)

        # abre como RGBA
        img = Image.open(BytesIO(output_bytes)).convert("RGBA")

        # recorta bordas transparentes
        if recortar:
            img = crop_transparent_borders(img)

        # upscale opcional
        if modo_saida == "uhd":
            img = upscale_to_uhd_if_needed(img)

        # aplica fundo final
        img = apply_background(img, tipo_fundo, cor_fundo)

        nome_base = os.path.splitext(arquivo.filename)[0]
        suffix = "_sem_fundo_uhd" if modo_saida == "uhd" else "_sem_fundo"

        saida = BytesIO()

        if formato_saida == "jpg":
            nome_download = f"{nome_base}{suffix}.jpg"
            img_rgb = img.convert("RGB")

            save_kwargs = {
                "format": "JPEG",
                "optimize": True,
                "quality": 82 if compactar else 92
            }

            img_rgb.save(saida, **save_kwargs)
            mimetype = "image/jpeg"

        else:
            nome_download = f"{nome_base}{suffix}.png"

            save_kwargs = {
                "format": "PNG",
                "optimize": True,
                "compress_level": compress_level if compactar else 1
            }

            img.save(saida, **save_kwargs)
            mimetype = "image/png"

        saida.seek(0)

        return send_file(
            saida,
            mimetype=mimetype,
            as_attachment=False,
            download_name=nome_download
        )

    except Exception as e:
        return jsonify({"erro": f"Erro ao processar imagem: {str(e)}"}), 500
