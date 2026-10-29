import os

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL


db = SQLAlchemy()
migrate = Migrate()


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_DATABASE_URI = URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("DB_HOST", "db"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "connect_args": {"connect_timeout": 5}}
