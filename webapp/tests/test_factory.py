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


def test_config():
    """Comprueba el comportamiento de TESTING por defecto y en tests."""
    app = create_app()
    assert not app.testing

    app_test = create_app({"TESTING": True})
    assert app_test.testing


def test_session_lifetime_is_24_hours():
    """Verifica la configuración de duración y refresco de sesión."""
    app = create_app({"TESTING": True})

    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=24)
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is False
