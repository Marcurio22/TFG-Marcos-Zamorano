"""
===============================================================================
Pruebas de administración de usuarios.

Este módulo verifica el listado, detalle, edición, borrado y exportación de
usuarios desde el panel de administración.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from trazasytrazadas.db import db
from trazasytrazadas.models import Foto, Parcela, Usuario
from tests.auth_helpers import _create_user, _disable_csrf


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
    assert "Exportar CSV" in html
    assert "Exportar PDF" in html


def test_admin_can_export_users_csv(app, client):
    """El administrador puede exportar todos los usuarios a CSV."""
    admin_id = _create_user(
        app,
        username="admin_export_csv",
        email="admin_export_csv@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    managed_hash = generate_password_hash("Password1!")
    _create_user(
        app,
        username="UsuarioCsv",
        email="csv@example.com",
        password_hash=managed_hash,
        phone="+34903389323",
        role="user",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/usuarios/exportar/csv")

    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert "usuarios.csv" in response.headers["Content-Disposition"]

    csv_text = response.get_data(as_text=True).lstrip("\ufeff")
    assert "ID,Usuario,Correo electrónico,Teléfono,Rol,Fecha de registro" in (
        csv_text
    )
    assert "UsuarioCsv" in csv_text
    assert "csv@example.com" in csv_text
    assert "(+34) 903 38 93 23" in csv_text
    assert managed_hash not in csv_text


def test_admin_can_export_users_pdf(app, client):
    """El administrador puede exportar todos los usuarios a PDF."""
    admin_id = _create_user(
        app,
        username="admin_export_pdf",
        email="admin_export_pdf@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="admin",
    )
    _create_user(
        app,
        username="UsuarioPdf",
        email="pdf@example.com",
        password_hash=generate_password_hash("Password1!"),
        phone="+34903389323",
        role="user",
    )

    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.get("/admin/usuarios/exportar/pdf")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "usuarios.pdf" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF")


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


def test_admin_can_delete_user_with_parcels_by_cascade(app, client):
    """Eliminar un usuario borra también sus parcelas y fotos."""
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
        username="UsuarioConParcelas",
        email="parcelas@example.com",
        password_hash=generate_password_hash("Password1!"),
        role="user",
    )

    with app.app_context():
        parcel = Parcela(
            usuario_id=managed_user_id,
            tamano_metros=100.0,
            pto_origen_latitud=40.0,
            pto_origen_longitud=-4.0,
            pto_fin_latitud=40.1,
            pto_fin_longitud=-3.8,
            fuente_id="pnoa2023",
            fuente_nombre="PNOA 2023",
            resolucion_solicitada=0.25,
            resolucion_real=0.25,
            ancho_tesela=1024,
            alto_tesela=640,
            estado="pending",
            nombre_coleccion="Zona del usuario",
        )
        db.session.add(parcel)
        db.session.flush()

        photo = Foto(
            parcela_id=int(parcel.parcela_id),
            modelo_id=None,
            fecha_foto="2026-01-01",
            resolucion_valor=0.25,
            resolucion_unidad="m/px",
            longitud=-4.0,
            latitud=40.0,
            ruta_foto="parcelas/test/tile.jpg",
            ruta_trazas=None,
            trazas=0,
            estado="pending",
            mensaje_error=None,
            iniciado_en=None,
            finalizado_en=None,
            numero_intentos=0,
            tesela_id="r01_c01",
            indice_fila=1,
            indice_columna=1,
            nombre_archivo="tile.jpg",
            ancho=1024,
            alto=640,
            limites_3857_json="{}",
            limites_json="{}",
        )
        db.session.add(photo)
        db.session.commit()

        parcel_id = int(parcel.parcela_id)
        photo_id = int(photo.foto_id)

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
    assert "parcelas asociadas" in html

    with app.app_context():
        assert db.session.get(Usuario, managed_user_id) is None
        assert db.session.get(Parcela, parcel_id) is None
        assert db.session.get(Foto, photo_id) is None


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
