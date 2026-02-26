from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user
from supabase import create_client  # ← importa aqui
from dotenv import load_dotenv
import os, pathlib
from sqlalchemy import event, text
import time, logging
from sqlalchemy.pool import Pool
import threading

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
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_size": 5,
    "max_overflow": 0,       # free: evita estourar conexões
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "pool_use_lifo": True,   # devolve e pega a conexão mais recente -> mais quente
}

app.config['PAF_ANO_VIGENTE'] = 2026

# --- flags para rodar só uma vez por worker ---
_pool_warmed = False
_pool_warm_lock = threading.Lock()

app.jinja_env.globals.update(enumerate=enumerate)

# Inicializa extensões
database = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'alert-info'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sqlalchemy_timing")

with app.app_context():
    engine = database.engine

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total_ms = (time.perf_counter() - getattr(context, "_query_start_time", time.perf_counter()))*1000
        logger.info(f"[DB] {total_ms:.1f} ms | rows={cursor.rowcount} | {statement[:120]} ...")

    
    @event.listens_for(database.engine, "connect")
    def set_tz_manaus(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("SET TIME ZONE 'America/Manaus'")
        cur.close()

@event.listens_for(Pool, "checkout")
def on_checkout(dbapi_con, con_record, con_proxy):
    con_record.info["checkout_t0"] = time.perf_counter()

@event.listens_for(Pool, "checkin")
def on_checkin(dbapi_con, con_record):
    t0 = con_record.info.pop("checkout_t0", None)
    if t0:
        alive_ms = (time.perf_counter() - t0)*1000
        logger.info(f"[POOL] conexão ficou viva por {alive_ms:.0f} ms")


def _prime_pool_once():
    global _pool_warmed
    if _pool_warmed:
        return
    with _pool_warm_lock:
        if _pool_warmed:
            return
        # estamos em app/request context aqui
        eng = database.engine          # <-- troquei aqui (ou: database.get_engine())
        pool_size = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('pool_size', 5)
        conns = []
        try:
            for _ in range(pool_size):
                c = eng.connect()
                c.execute(text("SELECT 1")).fetchone()
                conns.append(c)
        finally:
            for c in conns:
                c.close()
        _pool_warmed = True

@app.before_request   # existe no Flask 3.x
def _warm_pool_if_needed():
    _prime_pool_once()


@app.template_filter("br_currency")
def br_currency(value):
    try:
        value = float(value)
        return f"R$ {value:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    except:
        return value


@app.context_processor
def inject_nav():
    try:
        if getattr(current_user, "is_authenticated", False):
            # ✅ import lazy (evita circular)
            from src.nav import build_nav
            return {"nav_items": build_nav()}
    except Exception:
        pass
    return {"nav_items": []}

# if pathlib.Path(".env").exists():
#     from dotenv import load_dotenv
#     load_dotenv() 


# Importa rotas depois
from src import routes
from src.routes_acumulo import bp_acumulo
from src.routes_paf import bp_paf
from src.bp_paf_auto import bp_paf_auto
from src.routes_dependentes import bp_dep
from src.route_ferias import bp_ferias
from src.admin_permissoes import bp_admin_permissoes
from src.admin_obm_gestao import bp_admin_obm_gestao
from src.api_taf import bp_api_taf
app.register_blueprint(bp_api_taf)
app.register_blueprint(bp_acumulo)
app.register_blueprint(bp_paf)
app.register_blueprint(bp_ferias)
app.register_blueprint(bp_paf_auto)
app.register_blueprint(bp_dep)
app.register_blueprint(bp_admin_permissoes)
app.register_blueprint(bp_admin_obm_gestao)

# Torna o supabase acessível de fora
app.supabase = supabase
