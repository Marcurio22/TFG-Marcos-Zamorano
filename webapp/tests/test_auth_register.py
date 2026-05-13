"""
===============================================================================
Pruebas de registro de usuarios.

Este módulo verifica el alta de usuarios y las validaciones asociadas a nombre
de usuario, correo electrónico, teléfono y contraseña.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario
from tests.auth_helpers import (
    _create_user,
    _disable_csrf,
    _registration_payload,
)


def test_register_page_renders(app, client):
    """La pantalla de registro se renderiza correctamente."""
    response = client.get("/registro")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Registrarse" in html
    assert "Correo electr" in html


def test_register_creates_user_and_hashes_password(app, client):
    """El registro correcto crea usuario y guarda la contraseña hasheada."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario registrado correctamente." in html
    assert "Iniciar sesi" in html

    with app.app_context():
        user = db.session.execute(
            db.select(Usuario).filter_by(nombre_usuario="Pepe1234")
        ).scalar_one()

        assert user.correo_electronico == "pepe1234@gmail.com"
        assert user.telefono is None
        assert user.rol == "user"
        assert user.contrasena != "Password1!"
        assert check_password_hash(user.contrasena, "Password1!")


def test_register_persists_optional_phone_when_present(app, client):
    """El teléfono se guarda cuando el usuario lo informa."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(telefono="+34600112233"),
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        user = db.session.execute(
            db.select(Usuario).filter_by(nombre_usuario="Pepe1234")
        ).scalar_one()
        assert user.telefono == "+34600112233"


def test_register_rejects_duplicate_username(app, client):
    """No se puede registrar un nombre de usuario ya existente."""
    _disable_csrf(app)
    _create_user(app, username="Pepe1234", email="otro@example.com")

    response = client.post(
        "/registro",
        data=_registration_payload(correo_electronico="nuevo@example.com"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Ya existe un usuario con ese nombre." in html

    with app.app_context():
        count = db.session.execute(
            db.select(db.func.count(Usuario.usuario_id)).where(
                Usuario.nombre_usuario == "Pepe1234"
            )
        ).scalar_one()
        assert count == 1


def test_register_rejects_duplicate_email(app, client):
    """No se puede registrar un correo ya existente."""
    _disable_csrf(app)
    _create_user(app, username="OtroUsuario", email="pepe1234@gmail.com")

    response = client.post(
        "/registro",
        data=_registration_payload(nombre_usuario="NuevoUsuario"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Ya existe un usuario con ese correo electr" in html


def test_register_rejects_invalid_email(app, client):
    """Se valida que el correo tenga formato correcto."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(correo_electronico="correo-invalido"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Introduce un correo electr" in html


def test_register_rejects_invalid_phone(app, client):
    """Se valida el formato permitido del teléfono opcional."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(telefono="telefono@@@"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "solo puede contener" in html


def test_register_rejects_password_mismatch(app, client):
    """Se informa error cuando las contraseñas no coinciden."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(repetir_contrasena="OtraPassword1!"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Las contraseñas no coinciden." in html


def test_register_rejects_password_without_uppercase(app, client):
    """La contraseña debe incluir una mayúscula."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(
            contrasena="password1!",
            repetir_contrasena="password1!",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "al menos una mayúscula" in response.get_data(as_text=True)


def test_register_rejects_password_without_number(app, client):
    """La contraseña debe incluir un número."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(
            contrasena="Password!",
            repetir_contrasena="Password!",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "al menos un número" in response.get_data(as_text=True)


def test_register_rejects_password_without_special_char(app, client):
    """La contraseña debe incluir un carácter especial."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(
            contrasena="Password1",
            repetir_contrasena="Password1",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "al menos un carácter especial" in response.get_data(as_text=True)


def test_register_rejects_too_short_password(app, client):
    """La contraseña debe superar la longitud mínima."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(
            contrasena="Pass1!",
            repetir_contrasena="Pass1!",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "más de 8 caracteres" in response.get_data(as_text=True)


def test_register_redirects_authenticated_user(app, client):
    """Un usuario ya autenticado no debe ver la pantalla de registro."""
    user_id = _create_user(
        app,
        username="ya_logueado",
        email="logueado@example.com",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/registro", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_register_handles_integrity_error(app, client, monkeypatch):
    """Se muestra un error genérico si el commit falla en base de datos."""
    _disable_csrf(app)

    def _raise_integrity_error():
        raise IntegrityError("statement", "params", Exception("boom"))

    monkeypatch.setattr(db.session, "commit", _raise_integrity_error)

    response = client.post(
        "/registro",
        data=_registration_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No se ha podido completar el registro" in html

    with app.app_context():
        user = db.session.execute(
            db.select(Usuario).filter_by(nombre_usuario="Pepe1234")
        ).scalar_one_or_none()
        assert user is None


def test_register_normalizes_phone_with_default_prefix(app, client):
    """Si no se indica prefijo, se usa +34 por defecto."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(telefono="903 38 93 23"),
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        user = db.session.execute(
            db.select(Usuario).filter_by(nombre_usuario="Pepe1234")
        ).scalar_one()
        assert user.telefono == "+34903389323"


def test_register_rejects_invalid_country_prefix(app, client):
    """El prefijo internacional debe ser + y dos dígitos juntos."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(telefono="+3 4 903389323"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "dos dígitos juntos" in html


def test_register_rejects_too_short_phone(app, client):
    """El registro rechaza teléfonos demasiado cortos."""
    _disable_csrf(app)

    response = client.post(
        "/registro",
        data=_registration_payload(telefono="+34909"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "al menos 7 dígitos" in response.get_data(as_text=True)
