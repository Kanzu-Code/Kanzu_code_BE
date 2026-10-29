
import os
from datetime import timedelta

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL
from flask_jwt_extended import JWTManager


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]

    # JWT configuration
    JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # Database configuration
    SQLALCHEMY_DATABASE_URI = URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("DB_HOST", "db"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {
            "connect_timeout": 5,
        },
    }
