"""
===============================================================================
Helpers compartidos para pruebas de autenticación, perfil y administración.

Este módulo centraliza utilidades reutilizadas por los tests de
registro, login, perfil, usuarios administrados y gestión de modelos.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

from io import BytesIO
import pickle
import warnings

from PIL import Image

from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario


class _AdminUploadDummyModel:
    """Objeto mínimo serializable para pruebas de subida de modelos."""

    def forward(self, x):
        """Devuelve una máscara constante para la inferencia simulada."""
        return x.mean(dim=1, keepdim=True)


def _profile_image_bytes() -> BytesIO:
    """Construye una imagen PNG mínima para pruebas de perfil."""
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color=(79, 70, 229)).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _serialized_dummy_model() -> bytes:
    """Devuelve un modelo serializado mínimo para los tests."""
    buffer = BytesIO()
    pickle.dump(_AdminUploadDummyModel(), buffer)
    return buffer.getvalue()


def _serialized_dummy_torchscript_model() -> bytes:
    """Devuelve un TorchScript mínimo embebido para tests."""
    import torch

    class _TorchScriptDummyModel(torch.nn.Module):
        def forward(self, x):
            """Devuelve una máscara constante para la inferencia simulada."""
            return x.mean(dim=1, keepdim=True)

    buffer = BytesIO()
    example = torch.rand(1, 3, 32, 32)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*torch\.jit\..*",
            category=DeprecationWarning,
        )
        traced = torch.jit.trace(_TorchScriptDummyModel(), example)
        torch.jit.save(traced, buffer)

    return buffer.getvalue()


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
