from trazasytrazadas import create_app
from trazasytrazadas.db import db
from trazasytrazadas.models import Usuario

app = create_app()

with app.app_context():
    user = db.session.execute(
        db.select(Usuario).where(Usuario.nombre_usuario == "Vindi22")
    ).scalar_one_or_none()

    if user is None:
        print("No existe ningún usuario con nombre Vindi22.")
    else:
        user.rol = "admin"
        db.session.commit()
        print("Usuario Vindi22 actualizado a administrador.")
