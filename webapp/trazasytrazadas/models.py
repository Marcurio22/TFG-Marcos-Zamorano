"""
===============================================================================
Modelos SQLAlchemy de la aplicación.

Define los modelos reales de la BBDD sin cambiar todavía
el código de acceso manual existente. Sirven como base para migrar después
collection_store.py a Flask-SQLAlchemy.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations
from flask_login import UserMixin
from .db import db


class AppSetting(db.Model):
    """Configuración simple persistida de la aplicación."""
    __tablename__ = "app_setting"

    key = db.Column(db.Text, primary_key=True)
    value = db.Column(db.Text, nullable=False)


class Usuario(UserMixin, db.Model):
    """Modelo de usuario persistido en SQLite."""
    __tablename__ = "usuario"
    __table_args__ = (
        db.CheckConstraint(
            "rol IN ('system', 'admin', 'user')",
            name="ck_usuario_rol",
        ),
    )

    usuario_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_usuario = db.Column(db.String(50), nullable=False, unique=True)
    contrasena = db.Column(db.String(255), nullable=False)
    correo_electronico = db.Column(db.String(50), nullable=False, unique=True)
    telefono = db.Column(db.String(20), nullable=True)
    ruta_imagen_perfil = db.Column(db.Text, nullable=True)
    rol = db.Column(db.String(20), nullable=False)
    fecha_alta = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    parcelas = db.relationship(
        "Parcela",
        back_populates="usuario",
        lazy="select",
    )

    def get_id(self) -> str:
        """Devuelve el identificador serializable del usuario."""
        return str(self.usuario_id)


class Parcela(db.Model):
    """Modelo de zona persistida en la colección."""
    __tablename__ = "parcela"
    __table_args__ = (
        db.CheckConstraint(
            "estado IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_parcela_estado",
        ),
        db.Index(
            "idx_parcela_usuario_fecha",
            "usuario_id",
            "created_at",
        ),
    )

    parcela_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.usuario_id"),
        nullable=False,
    )
    tamano_metros = db.Column(db.Float, nullable=False)
    pto_origen_lat = db.Column(db.Float, nullable=False)
    pto_origen_lng = db.Column(db.Float, nullable=False)
    pto_fin_lat = db.Column(db.Float, nullable=False)
    pto_fin_lng = db.Column(db.Float, nullable=False)
    fecha = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("(DATE('now'))"),
    )
    bbox_json = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Text, nullable=False)
    source_label = db.Column(db.Text, nullable=False)
    requested_resolution = db.Column(db.Float, nullable=False)
    actual_resolution = db.Column(db.Float, nullable=False)
    tile_width = db.Column(db.Integer, nullable=False)
    tile_height = db.Column(db.Integer, nullable=False)
    estado = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("'pending'"),
    )
    nombre_coleccion = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    usuario = db.relationship(
        "Usuario",
        back_populates="parcelas",
        lazy="select",
    )
    fotos = db.relationship(
        "Foto",
        back_populates="parcela",
        cascade="all, delete-orphan",
        lazy="select",
    )


class Foto(db.Model):
    """Modelo de tesela asociada a una parcela."""
    __tablename__ = "foto"
    __table_args__ = (
        db.CheckConstraint(
            "trazas IN (0, 1)",
            name="ck_foto_trazas",
        ),
        db.CheckConstraint(
            "estado IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_foto_estado",
        ),
        db.UniqueConstraint(
            "parcela_id",
            "tile_id",
            name="uq_foto_parcela_tile_id",
        ),
        db.Index(
            "idx_foto_parcela",
            "parcela_id",
            "row_index",
            "col_index",
        ),
    )

    foto_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    parcela_id = db.Column(
        db.Integer,
        db.ForeignKey("parcela.parcela_id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha_foto = db.Column(db.Text, nullable=False)
    resolucion_valor = db.Column(db.Float, nullable=False)
    resolucion_unidad = db.Column(db.Text, nullable=False)
    longitud = db.Column(db.Float, nullable=False)
    latitud = db.Column(db.Float, nullable=False)
    ruta_foto = db.Column(db.Text, nullable=False)
    ruta_trazas = db.Column(db.Text, nullable=True)
    trazas = db.Column(
        db.Integer,
        nullable=False,
        server_default=db.text("0"),
    )
    estado = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("'pending'"),
    )
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.Text, nullable=True)
    finished_at = db.Column(db.Text, nullable=True)
    attempt_count = db.Column(
        db.Integer,
        nullable=False,
        server_default=db.text("0"),
    )
    tile_id = db.Column(db.Text, nullable=False)
    row_index = db.Column(db.Integer, nullable=False)
    col_index = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.Text, nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    bbox3857_json = db.Column(db.Text, nullable=False)
    bounds_json = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    parcela = db.relationship(
        "Parcela",
        back_populates="fotos",
        lazy="select",
    )
