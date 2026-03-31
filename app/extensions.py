from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler
from flask_mail import Mail

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
limiter = Limiter(key_func=get_remote_address)
scheduler = APScheduler()
mail = Mail()