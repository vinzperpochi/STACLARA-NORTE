import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import Role, User


def test_official_can_view_blotter_map():
    app = create_app("testing")

    with app.app_context():
        db.create_all()

        official_role = db.session.scalar(db.select(Role).where(Role.name == "Barangay Official"))
        if official_role is None:
            official_role = Role(name="Barangay Official", description="Official access")
            db.session.add(official_role)

        user = db.session.scalar(db.select(User).where(User.username == "official_test"))
        if user is None:
            user = User(username="official_test", email="official_test@example.com", status="active", is_active=True)
            user.set_password("Official@123456")
            user.roles.append(official_role)
            db.session.add(user)
            db.session.commit()

        with app.test_client() as client:
            login_resp = client.post(
                "/auth/login",
                data={"role": "staff", "identifier": "official_test", "password": "Official@123456"},
                follow_redirects=False,
            )
            assert login_resp.status_code == 302

            resp = client.get("/official/blotter-map")
            assert resp.status_code == 200
