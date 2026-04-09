from flask import Flask, request
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.cselsnczhbsinizmwtcv:drhsistema2025@aws-0-us-west-1.pooler.supabase.com:6543/postgres'
app.config['SECRET_KEY'] = '60cc737479829f9462369024bee383ce'
app.config["UPLOAD_FOLDER"] = "static/boletim_geral"
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_size": 5,
    "max_overflow": 10,       # free: evita estourar conexões
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "pool_timeout": 30,
    "pool_use_lifo": True,   # devolve e pega a conexão mais recente -> mais quente
}

app.config['PAF_ANO_VIGENTE'] = 2026
app.config["PUBLIC_BASE_URL"] = "https://drhsistema-production.up.railway.app"
# --- flags para rodar só uma vez por worker ---
_pool_warmed = False
_pool_warm_lock = threading.Lock()

app.jinja_env.globals.update(enumerate=enumerate)

@app.before_request
def big_brother_log_acesso():
    # 1. Trava de Segurança: Não logar arquivos de imagem, CSS, JS, etc.
    if request.path.startswith('/static') or request.path.startswith('/favicon'):
        return

    try:
        # A MÁGICA AQUI: Importa a model APENAS na hora que a função roda!
        from src.models import LogAcesso 
        
        # 2. Pega o IP real do usuário
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()

        # 3. Pega o ID do usuário (se ele já estiver logado, senão fica None)
        user_id = current_user.id if current_user.is_authenticated else None

        # 4. Pega o User-Agent (limitado a 250 caracteres pro banco não reclamar)
        agent = request.user_agent.string[:250] if request.user_agent.string else "Desconhecido"

        # 5. Salva a fofoca no banco
        novo_log = LogAcesso(
            usuario_id=user_id,
            rota_acessada=request.path,
            metodo=request.method,
            ip_address=ip,
            user_agent=agent
        )
        
        # Como o banco já iniciou a essa altura, o database vai funcionar perfeitamente
        database.session.add(novo_log)
        database.session.commit()
        
    except Exception as e:
        database.session.rollback()
        # Se der erro no log, a gente só "printa" no console, 
        # mas não quebra a navegação do usuário.
        print(f"[ERRO DE AUDITORIA - BIG BROTHER]: {str(e)}")

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
from src.routes_taf import taf_admin_bp
from src.routes_historico import bp_historico
from src.routes_atualizacao_cadastral import bp_atualizacao_cadastral
from src.routes_junta import junta_bp
from src.routes_remove_bg import remove_bg_bp

app.register_blueprint(remove_bg_bp)
app.register_blueprint(junta_bp)
app.register_blueprint(bp_atualizacao_cadastral)
app.register_blueprint(bp_historico)
app.register_blueprint(taf_admin_bp)
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
