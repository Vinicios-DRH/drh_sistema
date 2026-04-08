from flask import render_template, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, case, distinct
from sqlalchemy.orm import joinedload

# ajuste os imports conforme teu projeto
from src import app, database
from src.models import (
     Militar, MilitarObmFuncao, Obm, PostoGrad, Quadro,
     LicencaEspecial, LicencaParaTratamentoDeSaude
)
