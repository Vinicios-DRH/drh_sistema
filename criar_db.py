from flask import send_file
from sqlalchemy import extract, func
from io import BytesIO
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from src import database
from src.models import Militar

# Adicione os imports da sua aplicação (database, Militar)
# from src import database
# from models import Militar

