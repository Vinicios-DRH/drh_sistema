from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from supabase import create_client  # ← importa aqui
from dotenv import load_dotenv
import os, pathlib

# Carrega variáveis do .env
load_dotenv()

# Dados do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)

# Banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.cselsnczhbsinizmwtcv:drhsistema2025@aws-0-us-west-1.pooler.supabase.com:5432/postgres'
app.config['SECRET_KEY'] = '60cc737479829f9462369024bee383ce'
app.config["UPLOAD_FOLDER"] = "static/boletim_geral"
app.jinja_env.globals.update(enumerate=enumerate)

# Inicializa extensões
database = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'alert-info'


@app.template_filter("br_currency")
def br_currency(value):
    try:
        value = float(value)
        return f"R$ {value:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    except:
        return value

# if pathlib.Path(".env").exists():
#     from dotenv import load_dotenv
#     load_dotenv() 

# Importa rotas depois
from src import routes
from src.routes_acumulo import bp_acumulo
app.register_blueprint(bp_acumulo)
# Torna o supabase acessível de fora
app.supabase = supabase
