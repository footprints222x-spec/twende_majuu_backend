from .admin import admin_bp
from .applicant import applicant_bp
from .auth import auth_bp
from .meta import meta_bp


def register_blueprints(app):
    app.register_blueprint(meta_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(applicant_bp, url_prefix="/api/applicant")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
