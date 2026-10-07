from sqlalchemy import inspect, text
from sqlmodel import select

from app.db import engine, get_session
from app.models import AlleyConfig, CookLog, Kettle, User, Workshop
from app.security import hash_password

WEST_ALLEY = "西巷"
EAST_ALLEY = "东巷"
ALLEYS = [WEST_ALLEY, EAST_ALLEY]


def migrate_schema() -> None:
    """给旧库补 kettles.alley 列（create_all 不会改已存在的表）。"""
    inspector = inspect(engine)
    if "kettle" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("kettle")}
    if "alley" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE kettle ADD COLUMN alley VARCHAR DEFAULT '西巷'"))
            # 旧布局锅-1..3 在西巷，锅-4..6 在东巷
            conn.execute(text("UPDATE kettle SET alley = '东巷' WHERE bench >= 3"))


def _ensure_alley_configs(session) -> None:
    defaults = {WEST_ALLEY: 2, EAST_ALLEY: 2}
    existing = {c.alley: c for c in session.exec(select(AlleyConfig)).all()}
    for alley, cap in defaults.items():
        if alley not in existing:
            session.add(AlleyConfig(alley=alley, cap=cap, enabled=True))


def seed_demo() -> None:
    with get_session() as session:
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if admin is None:
            session.add(User(username="admin", password_hash=hash_password("123456"), role="admin"))
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"
        worker = session.exec(select(User).where(User.username == "worker")).first()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"
        _ensure_alley_configs(session)
        if session.exec(select(Workshop)).first():
            session.commit()
            return
        shop = Workshop(name="骨巷熬胶坊", alley="西市骨巷")
        session.add(shop)
        session.flush()
        layout = [
            # 锅-1..3 西巷，锅-4..6 东巷
            ("锅-1", Kettle.STATUS_BOILING, 0, 96.0, WEST_ALLEY),
            ("锅-2", Kettle.STATUS_COLD, 1, None, WEST_ALLEY),
            ("锅-3", Kettle.STATUS_DRAWN, 2, 102.0, WEST_ALLEY),
            ("锅-4", Kettle.STATUS_BOILING, 3, 82.0, EAST_ALLEY),
            ("锅-5", Kettle.STATUS_COLD, 4, None, EAST_ALLEY),
            ("锅-6", Kettle.STATUS_DRAWN, 5, 94.0, EAST_ALLEY),
        ]
        for code, status, bench, peak, alley in layout:
            kettle = Kettle(workshop_id=shop.id, code=code, status=status, bench=bench, alley=alley)
            session.add(kettle)
            session.flush()
            if peak is not None:
                session.add(CookLog(kettle_id=kettle.id, peak_temp_c=peak, operator="worker"))
        session.commit()
