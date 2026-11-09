"""Twende Majuu – crew registration backend (application factory)."""
import logging

from flask import Flask

from .config import get_config, validate_config
from .extensions import cors, db, jwt, migrate


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    validate_config(app.config)

    logging.basicConfig(level=logging.INFO if not app.config["TESTING"] else logging.WARNING)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        max_age=600,
    )

    from . import models  # noqa: F401  (registers models with SQLAlchemy / Alembic)
    from .auth import register_jwt_callbacks
    from .cli import register_cli
    from .errors import register_error_handlers
    from .routes import register_blueprints
    from .services.storage_service import configure_cloudinary

    configure_cloudinary(app)
    register_jwt_callbacks(jwt)
    register_error_handlers(app)
    register_blueprints(app)
    register_cli(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # API responses can contain personal data; never let proxies/browsers cache them.
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    return app
