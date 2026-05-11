"""
===============================================================================
Modelos SQLAlchemy de la aplicación.

Define los modelos reales de la BBDD gestionados mediante SQLAlchemy.
Los nombres de columnas se mantienen en español y las trazas quedan
embebidas en la tabla de fotos.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations
from flask_login import UserMixin
from .db import db


class Modelo(db.Model):
    """Modelo de segmentación disponible en el sistema."""

    __tablename__ = "modelo"
    __table_args__ = (
        db.CheckConstraint(
            "estado IN ('activo', 'no_activo')",
            name="ck_modelo_estado",
        ),
        db.CheckConstraint(
            "validacion IN ('pendiente', 'validado')",
            name="ck_modelo_validacion",
        ),
        db.UniqueConstraint(
            "nombre_modelo",
            name="uq_modelo_nombre_modelo",
        ),
    )

    modelo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_modelo = db.Column(db.String(100), nullable=False)
    estado = db.Column(
        db.String(20),
        nullable=False,
        server_default=db.text("'no_activo'"),
    )
    validacion = db.Column(
        db.String(20),
        nullable=False,
        server_default=db.text("'pendiente'"),
    )
    creado_en = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )
    actualizado_en = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    fotos = db.relationship(
        "Foto",
        back_populates="modelo",
        lazy="select",
    )


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
        cascade="all, delete-orphan",
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
            "creado_en",
        ),
    )

    parcela_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.usuario_id"),
        nullable=False,
    )
    tamano_metros = db.Column(db.Float, nullable=False)
    pto_origen_latitud = db.Column(db.Float, nullable=False)
    pto_origen_longitud = db.Column(db.Float, nullable=False)
    pto_fin_latitud = db.Column(db.Float, nullable=False)
    pto_fin_longitud = db.Column(db.Float, nullable=False)
    fuente_id = db.Column(db.Text, nullable=False)
    fuente_nombre = db.Column(db.Text, nullable=False)
    resolucion_solicitada = db.Column(db.Float, nullable=False)
    resolucion_real = db.Column(db.Float, nullable=False)
    ancho_tesela = db.Column(db.Integer, nullable=False)
    alto_tesela = db.Column(db.Integer, nullable=False)
    estado = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("'pending'"),
    )
    nombre_coleccion = db.Column(db.Text, nullable=True)
    creado_en = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    actualizado_en = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.usuario_id", ondelete="CASCADE"),
        nullable=False,
    )

    usuario = db.relationship("Usuario", back_populates="parcelas")

    fotos = db.relationship(
        "Foto",
        back_populates="parcela",
        cascade="all, delete-orphan",
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
            "tesela_id",
            name="uq_foto_parcela_tesela_id",
        ),
        db.Index(
            "idx_foto_parcela",
            "parcela_id",
            "indice_fila",
            "indice_columna",
        ),
    )

    foto_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    parcela_id = db.Column(
        db.Integer,
        db.ForeignKey("parcela.parcela_id", ondelete="CASCADE"),
        nullable=False,
    )
    modelo_id = db.Column(
        db.Integer,
        db.ForeignKey("modelo.modelo_id"),
        nullable=True,
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
    mensaje_error = db.Column(db.Text, nullable=True)
    iniciado_en = db.Column(db.Text, nullable=True)
    finalizado_en = db.Column(db.Text, nullable=True)
    numero_intentos = db.Column(
        db.Integer,
        nullable=False,
        server_default=db.text("0"),
    )
    tesela_id = db.Column(db.Text, nullable=False)
    indice_fila = db.Column(db.Integer, nullable=False)
    indice_columna = db.Column(db.Integer, nullable=False)
    nombre_archivo = db.Column(db.Text, nullable=False)
    ancho = db.Column(db.Integer, nullable=False)
    alto = db.Column(db.Integer, nullable=False)
    limites_3857_json = db.Column(db.Text, nullable=False)
    limites_json = db.Column(db.Text, nullable=False)
    creado_en = db.Column(
        db.Text,
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    parcela_id = db.Column(
        db.Integer,
        db.ForeignKey("parcela.parcela_id", ondelete="CASCADE"),
        nullable=False,
    )

    parcela = db.relationship("Parcela", back_populates="fotos")

    modelo = db.relationship(
        "Modelo",
        back_populates="fotos",
        lazy="select",
    )
