from flask import Flask, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config.extensions import Config, db, migrate

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
migrate.init_app(app, db)


@app.get("/")
def index():
    return jsonify(message="Kanzu Apprentice Milestone Tracker API")


@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database health check failed")
        return jsonify(status="unhealthy", database="unavailable"), 503
    return jsonify(status="healthy", database="connected")
