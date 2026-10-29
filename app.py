from flask import Flask, jsonify
from flasgger import Swagger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config.extensions import Config, db, migrate

from models.user import User
from routes.user import employer_auth_bp, admin_auth_bp, apprentice_auth_bp


app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate.init_app(app, db)


app.register_blueprint(employer_auth_bp),
app.register_blueprint(admin_auth_bp), 
app.register_blueprint(apprentice_auth_bp)


swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Kanzu Apprentice Milestone Tracker API",
        "description": (
            "API for apprentice records, milestone reviews "
            "and payment tracking."
        ),
        "version": "1.0.0",
    },
    "tags": [
        {
            "name": "Employer Authentication",
            "description": "Employer account registration.",
        }
    ],
}

swagger = Swagger(
    app,
    config=swagger_config,
    template=swagger_template,
)


@app.get("/")
def index():
    return jsonify(
        message="Kanzu Apprentice Milestone Tracker API",
        documentation="/docs/",
    )


@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database health check failed")

        return jsonify(
            status="unhealthy",
            database="unavailable",
        ), 503

    return jsonify(
        status="healthy",
        database="connected",
    )