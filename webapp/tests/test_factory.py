"""
===============================================================================
 Archivo: test_factory.py
 Autor: Marcos Zamorano Lasso
 Since: 19/11/2025
 Descripción:
     Tests básicos para comprobar que la application factory de Flask
     (`create_app`) se crea correctamente y respeta la configuración de tests.
===============================================================================
"""

from trazasytrazadas import create_app


def test_config():
    """
    Verifica que:
        - Por defecto, la app NO está en modo testing.
        - Si pasamos {"TESTING": True}, la app se crea en modo testing.
    """
    app = create_app()
    assert not app.testing  # Valor por defecto

    app_test = create_app({"TESTING": True})
    assert app_test.testing  # Debe respetar la configuración proporcionada
