"""
Pruebas básicas de la application factory de Flask.

Este módulo verifica que create_app() construye la aplicación con la
configuración esperada y que respeta los ajustes de sesión definidos para el
proyecto.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

from datetime import timedelta

from trazasytrazadas import create_app
from trazasytrazadas.db import db


def _dispose_app(app):
    """Cierra sesiones y conexiones abiertas por una app creada a mano."""
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_config():
    """Comprueba el comportamiento de TESTING por defecto y en tests."""
    app = create_app()
    app_test = create_app({"TESTING": True})

    try:
        assert not app.testing
        assert app_test.testing
    finally:
        _dispose_app(app_test)
        _dispose_app(app)


def test_session_lifetime_is_24_hours():
    """Verifica la configuración de duración y refresco de sesión."""
    app = create_app({"TESTING": True})

    try:
        assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=24)
        assert app.config["SESSION_REFRESH_EACH_REQUEST"] is False
    finally:
        _dispose_app(app)
