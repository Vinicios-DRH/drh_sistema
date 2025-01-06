from src import routes
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
import sqlalchemy

app = Flask(__name__)

# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/sistema'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///drh-sistema.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:drhsistema2025@db.cselsnczhbsinizmwtcv.supabase.co:5432/postgres'

app.config['SECRET_KEY'] = '60cc737479829f9462369024bee383ce'
app.config["UPLOAD_FOLDER"] = "static/boletim_geral"
app.jinja_env.globals.update(enumerate=enumerate)

database = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'alert-info'
