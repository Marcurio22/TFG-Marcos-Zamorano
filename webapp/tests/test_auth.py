from __future__ import annotations
from pathlib import Path
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from trazasytrazadas.db import db
from trazasytrazadas.models import AppSetting, Usuario


def _disable_csrf(app) -> None:
    """Desactiva CSRF para poder enviar formularios en tests."""
    app.config["WTF_CSRF_ENABLED"] = False


def _registration_payload(**overrides) -> dict[str, str]:
    """Construye un payload válido de registro."""
    payload = {
        "nombre_usuario": "Pepe1234",
        "correo_electronico": "pepe1234@gmail.com",
        "telefono": "",
        "contrasena": "Password1!",
        "repetir_contrasena": "Password1!",
    }
    payload.update(overrides)
    return payload


def _login_payload(**overrides) -> dict[str, str]:
    """Construye un payload válido de inicio de sesión."""
    payload = {
        "nombre_usuario": "Pepe1234",
        "contrasena": "Password1!",
    }
    payload.update(overrides)
    return payload


def _create_user(
    app,
    *,
    username: str = "usuario_existente",
    email: str = "existente@example.com",
    password_hash: str = "hashed-password",
    phone: str | None = None,
    role: str = "user",
) -> int:
    """Inserta un usuario persistido y devuelve su identificador."""
    with app.app_context():
        user = Usuario(
            nombre_usuario=username,
            correo_electronico=email,
            telefono=phone,
            contrasena=password_hash,
            rol=role,
        )
        db.session.add(user)
        db.session.commit()
        return int(user.usuario_id)


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


def test_login_page_renders(app, client):
    """La pantalla de login se renderiza correctamente."""
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Inicio de sesi" in html
    assert "Iniciar sesi" in html


def test_login_authenticates_user_and_stores_session(app, client):
    """Un login válido autentica al usuario y guarda la sesión."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Pepe1234",
        email="pepe1234@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    response = client.post(
        "/login",
        data=_login_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Has iniciado sesi" in html

    with client.session_transaction() as session:
        assert session.get("_user_id") == str(user_id)
        assert session.get("_fresh") is True


def test_login_rejects_wrong_password(app, client):
    """No autentica si la contraseña es incorrecta."""
    _disable_csrf(app)
    _create_user(
        app,
        username="Pepe1234",
        email="pepe1234@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    response = client.post(
        "/login",
        data=_login_payload(contrasena="Password2!"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario o contrase" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_rejects_unknown_user(app, client):
    """No autentica si el usuario no existe."""
    _disable_csrf(app)

    response = client.post(
        "/login",
        data=_login_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario o contrase" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_rejects_missing_fields(app, client):
    """El formulario informa los campos obligatorios vacíos."""
    _disable_csrf(app)

    response = client.post(
        "/login",
        data={
            "nombre_usuario": "",
            "contrasena": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Introduce un nombre de usuario." in html
    assert "Introduce una contrase" in html


def test_login_redirects_authenticated_user(app, client):
    """Un usuario autenticado no debe ver la pantalla de login."""
    user_id = _create_user(
        app,
        username="ya_logueado",
        email="logueado@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_login_handles_database_error(app, client, monkeypatch):
    """Se muestra un error genérico si falla la consulta a base de datos."""
    _disable_csrf(app)

    def _raise_db_error(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(db.session, "execute", _raise_db_error)

    response = client.post(
        "/login",
        data=_login_payload(),
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No se ha podido iniciar sesi" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_logout_clears_session_and_redirects_home(app, client):
    """Cerrar sesión limpia la sesión activa y vuelve a portada."""
    user_id = _create_user(
        app,
        username="usuario_logout",
        email="logout@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post("/logout", follow_redirects=True)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Has cerrado sesi" in html

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_logout_requires_authenticated_user(client):
    """Logout exige una sesión autenticada."""
    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_drawer_shows_profile_and_logout_for_authenticated_user(app, client):
    """El drawer muestra perfil y logout para usuarios autenticados."""
    user_id = _create_user(
        app,
        username="usuario_menu",
        email="menu@example.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Perfil" in html
    assert "Cerrar sesión" in html
    assert "Panel del Administrador" not in html


def test_drawer_shows_admin_panel_for_admin_user(app, client):
    """El drawer muestra el bloque admin solo a usuarios administradores."""
    admin_id = _create_user(
        app,
        username="admin_menu",
        email="admin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Panel del Administrador" in html
    assert "Gestión de Usuarios" in html
    assert "Gestión del Modelo" in html


def test_drawer_shows_login_for_anonymous_user(client):
    """El drawer muestra acceso a login cuando no hay sesión."""
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Iniciar sesión" in html
    assert "Perfil" not in html
    assert "Cerrar sesión" not in html


def test_profile_requires_login(client):
    """La página de perfil exige autenticación."""
    response = client.get("/perfil", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_page_renders_current_user_data(app, client):
    """El perfil muestra datos del usuario autenticado."""
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with app.app_context():
        user = db.session.get(Usuario, user_id)
        joined_label = user.fecha_alta.strftime("%d/%m/%Y, %H:%M")

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Nicoup" in html
    assert "nickurio@gmail.com" in html
    assert "No asociado" in html
    assert joined_label in html
    assert "Acceder al visor" in html
    assert "Acceder a la colección" in html


def test_profile_update_persists_changes(app, client):
    """Editar perfil actualiza nombre, correo y teléfono en base de datos."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "NicoupEditado",
            "correo_electronico": "nicoupeditado@gmail.com",
            "telefono": "+34 660 36 46 51",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Perfil actualizado correctamente." in html

    with app.app_context():
        user = db.session.get(Usuario, user_id)
        assert user.nombre_usuario == "NicoupEditado"
        assert user.correo_electronico == "nicoupeditado@gmail.com"
        assert user.telefono == "+34660364651"


def test_profile_update_rejects_duplicate_username(app, client):
    """No permite reutilizar un nombre de usuario ya existente."""
    _disable_csrf(app)
    owner_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _create_user(
        app,
        username="UsuarioExistente",
        email="otro@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "UsuarioExistente",
            "correo_electronico": "nickurio@gmail.com",
            "telefono": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ya existe un usuario con ese nombre." in response.get_data(
        as_text=True)


def test_profile_update_rejects_duplicate_email(app, client):
    """No permite reutilizar un correo ya existente."""
    _disable_csrf(app)
    owner_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )
    _create_user(
        app,
        username="OtroUsuario",
        email="existente@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "Nicoup",
            "correo_electronico": "existente@gmail.com",
            "telefono": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ya existe un usuario con ese correo electr" in response.get_data(
        as_text=True)


def test_profile_update_rejects_invalid_phone(app, client):
    """No permite guardar teléfonos con formato inválido."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "Nicoup",
            "correo_electronico": "nickurio@gmail.com",
            "telefono": "telefono@@@",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "solo puede contener" in response.get_data(as_text=True)


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


def test_profile_page_formats_phone_for_display(app, client):
    """El perfil muestra el teléfono con formato legible estable."""
    user_id = _create_user(
        app,
        username="Pepe1234",
        email="pepe1234@gmail.com",
        password_hash=generate_password_hash("Password1!"),
        phone="+34903389323",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "(+34) 903 38 93 23" in html


def test_login_page_renders_guest_access_button(client):
    """La pantalla de login ofrece acceso a la parte básica como visitante."""
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Continuar como visitante" in html


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


def test_profile_update_rejects_too_short_phone(app, client):
    """El perfil rechaza teléfonos demasiado cortos."""
    _disable_csrf(app)
    user_id = _create_user(
        app,
        username="Nicoup",
        email="nickurio@gmail.com",
        password_hash=generate_password_hash("Password1!"),
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/perfil/editar",
        data={
            "nombre_usuario": "Nicoup",
            "correo_electronico": "nickurio@gmail.com",
            "telefono": "+34909",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "al menos 7 dígitos" in response.get_data(as_text=True)


def test_profile_page_shows_admin_badge_for_admin(app, client):
    """El perfil muestra la etiqueta de administrador solo para admins."""
    admin_id = _create_user(
        app,
        username="AdminUser",
        email="adminuser@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        user = db.session.get(Usuario, admin_id)
        joined_label = user.fecha_alta.strftime("%d/%m/%Y, %H:%M")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Administrador" in html
    assert joined_label in html


def test_anonymous_user_cannot_access_visor(client):
    """Un usuario anónimo no puede acceder al visor."""
    response = client.get("/visor", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_user_cannot_access_collection(client):
    """Un usuario anónimo no puede acceder a la colección."""
    response = client.get("/coleccion", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_user_cannot_access_profile(client):
    """Un usuario anónimo no puede acceder al perfil."""
    response = client.get("/perfil", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_panel_redirects_anonymous_user_to_login(client):
    """El panel admin redirige a login si el usuario es anónimo."""
    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_panel_forbids_regular_user(app, client):
    """Un usuario normal no puede entrar en Flask-Admin."""
    user_id = _create_user(
        app,
        username="usuario_normal",
        email="normal@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 403


def test_admin_panel_redirects_admin_to_user_management(app, client):
    """El root admin redirige a la gestión de usuarios."""
    admin_id = _create_user(
        app,
        username="superadmin",
        email="superadmin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert "/admin/usuarios" in response.headers["Location"]


def test_profile_page_shows_admin_links_for_admin(app, client):
    """El perfil del administrador muestra accesos de gestión."""
    admin_id = _create_user(
        app,
        username="AdminUser",
        email="adminuser@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/perfil")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Administrador" in html
    assert "Gestión de Usuarios" in html
    assert "Gestión del Modelo" in html


def test_admin_user_management_page_renders_summary_and_rows(app, client):
    """La gestión de usuarios muestra cards resumen y el listado."""
    admin_id = _create_user(
        app,
        username="superadmin",
        email="superadmin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    _create_user(
        app,
        username="UsuarioPanel",
        email="panel@example.com",
        password_hash=generate_password_hash("Password1!"),
        phone="+34903389323",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/usuarios/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Gestión de Usuarios" in html
    assert "Total de usuarios" in html
    assert "Administradores" in html
    assert "Usuarios regulares" in html
    assert "UsuarioPanel" in html


def test_admin_user_detail_hides_password_and_formats_phone(app, client):
    """El detalle admin no muestra contraseña y formatea el teléfono."""
    admin_id = _create_user(
        app,
        username="superadmin",
        email="superadmin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    managed_user_id = _create_user(
        app,
        username="UsuarioDetalle",
        email="detalle@example.com",
        password_hash=generate_password_hash("Password1!"),
        phone="+34903389323",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    with app.app_context():
        stored_hash = db.session.get(Usuario, managed_user_id).contrasena

    response = client.get(f"/admin/usuarios/{managed_user_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "UsuarioDetalle" in html
    assert "(+34) 903 38 93 23" in html
    assert "Contraseña" not in html
    assert stored_hash not in html


def test_admin_can_edit_user_from_management(app, client):
    """El administrador puede editar un usuario desde la gestión."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="superadmin",
        email="superadmin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    managed_user_id = _create_user(
        app,
        username="UsuarioEditar",
        email="editar@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        f"/admin/usuarios/{managed_user_id}/editar",
        data={
            "nombre_usuario": "UsuarioEditado",
            "correo_electronico": "editado@example.com",
            "telefono": "+34 900 30 02 00",
            "rol": "admin",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario actualizado correctamente." in html

    with app.app_context():
        user = db.session.get(Usuario, managed_user_id)
        assert user.nombre_usuario == "UsuarioEditado"
        assert user.correo_electronico == "editado@example.com"
        assert user.telefono == "+34900300200"
        assert user.rol == "admin"


def test_admin_can_delete_user_without_parcels(app, client):
    """El administrador puede eliminar un usuario sin parcelas asociadas."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="superadmin",
        email="superadmin@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    managed_user_id = _create_user(
        app,
        username="UsuarioEliminar",
        email="eliminar@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        f"/admin/usuarios/{managed_user_id}/eliminar",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Usuario eliminado correctamente." in html

    with app.app_context():
        user = db.session.get(Usuario, managed_user_id)
        assert user is None


def test_admin_cannot_delete_another_admin(app, client):
    """Un admin no puede eliminar a otro admin."""
    _disable_csrf(app)

    acting_admin_id = _create_user(
        app,
        username="admin_actor",
        email="admin_actor@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    target_admin_id = _create_user(
        app,
        username="admin_target",
        email="admin_target@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(acting_admin_id)
        session["_fresh"] = True

    response = client.post(
        f"/admin/usuarios/{target_admin_id}/eliminar",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No se puede eliminar otro usuario administrador." in html

    with app.app_context():
        assert db.session.get(Usuario, target_admin_id) is not None


def test_admin_cannot_delete_self_from_admin_view(app, client):
    """Un admin no puede eliminar su propia cuenta desde admin."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_self",
        email="admin_self@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        f"/admin/usuarios/{admin_id}/eliminar",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No puedes eliminar el usuario con el "
    "que has iniciado sesión." in html

    with app.app_context():
        assert db.session.get(Usuario, admin_id) is not None


def test_admin_cannot_remove_admin_role_from_admin_user(app, client):
    """Un admin no puede retirar el rol admin a otro admin."""
    _disable_csrf(app)

    acting_admin_id = _create_user(
        app,
        username="admin_actor",
        email="admin_actor@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    target_admin_id = _create_user(
        app,
        username="admin_target",
        email="admin_target@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(acting_admin_id)
        session["_fresh"] = True

    response = client.post(
        f"/admin/usuarios/{target_admin_id}/editar",
        data={
            "nombre_usuario": "admin_target",
            "correo_electronico": "admin_target@example.com",
            "telefono": "",
            "rol": "user",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No se puede retirar el rol de "
    "administrador desde esta vista." in html

    with app.app_context():
        user = db.session.get(Usuario, target_admin_id)
        assert user is not None
        assert user.rol == "admin"


def test_admin_folds_page_lists_from_fold_zero(app, client):
    """La gestión de folds lista folds reales empezando en fold.0."""
    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = app.config["SEG_MODELS_DIR"]
        Path(models_dir, "fold.0").write_text("a", encoding="utf-8")
        Path(models_dir, "fold.1").write_text("b", encoding="utf-8")
        Path(models_dir, "fold.9").write_text("c", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/folds/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "fold.0" in html
    assert "fold.1" in html
    assert "fold.9" in html
    assert "fold.10" not in html


def test_admin_folds_page_marks_fold_zero_as_default_active(app, client):
    """Si no hay setting persistido, fold.0 actúa como activo por defecto."""
    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("a", encoding="utf-8")
        (models_dir / "fold.1").write_text("b", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/folds/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Activo: fold.0" in html


def test_admin_can_activate_fold_and_persists_in_db(app, client):
    """El administrador puede activar un fold y se persiste en SQLite."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.0").write_text("a", encoding="utf-8")
        (models_dir / "fold.1").write_text("b", encoding="utf-8")

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/activar",
        data={"fold_name": "fold.1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Modelo activo actualizado correctamente." in response.get_data(
        as_text=True
    )

    with app.app_context():
        setting = db.session.get(AppSetting, "active_fold_name")
        assert setting is not None
        assert setting.value == "fold.1"


def test_admin_can_rename_active_fold_and_updates_db_setting(app, client):
    """Renombrar el fold activo actualiza también la referencia persistida."""
    _disable_csrf(app)

    admin_id = _create_user(
        app,
        username="admin_folds",
        email="admin_folds@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "fold.3").write_text("x", encoding="utf-8")
        db.session.add(AppSetting(key="active_fold_name", value="fold.3"))
        db.session.commit()

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/admin/folds/renombrar",
        data={
            "current_name": "fold.3",
            "new_name": "fold.7",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Fold renombrado correctamente." in html

    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        assert (models_dir / "fold.7").exists()
        assert not (models_dir / "fold.3").exists()

        setting = db.session.get(AppSetting, "active_fold_name")
        assert setting is not None
        assert setting.value == "fold.7"
