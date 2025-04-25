from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from supabase import create_client  # ← importa aqui

# Dados do Supabase
SUPABASE_URL = "https://cselsnczhbsinizmwtcv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNzZWxzbmN6aGJzaW5pem13dGN2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzYxMzIzNTQsImV4cCI6MjA1MTcwODM1NH0.SrdZIC5o03q5V5SK_RpzvoqqXrK6X37Dw9cObeLSjL8"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)  # ← cliente global

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


# Importa rotas depois
from src import routes
# Torna o supabase acessível de fora
app.supabase = supabase
