from sqlalchemy import inspect, text
from sqlmodel import select

from app.db import engine, get_session
from app.models import AlleyConfig, CookLog, Kettle, User, Workshop
from app.security import hash_password

DEFAULT_CAPS = {"东巷": 2, "西巷": 1}


def migrate() -> None:
    """老库补 alley 列并回填巷名；按巷补齐并存上限配置行。"""
    insp = inspect(engine)
    if "kettle" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("kettle")}
        if "alley" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE kettle ADD COLUMN alley VARCHAR NOT NULL DEFAULT ''"))
    with get_session() as session:
        kettles = session.exec(select(Kettle)).all()
        changed = False
        for kettle in kettles:
            if not kettle.alley:
                kettle.alley = "东巷" if kettle.bench % 2 == 0 else "西巷"
                session.add(kettle)
                changed = True
        alleys = sorted({k.alley for k in kettles if k.alley})
        for name in alleys:
            cfg = session.exec(select(AlleyConfig).where(AlleyConfig.alley == name)).first()
            if cfg is None:
                session.add(AlleyConfig(alley=name, cap=DEFAULT_CAPS.get(name, 1), enabled=True))
                changed = True
        if changed:
            session.commit()


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
        if session.exec(select(Workshop)).first():
            session.commit()
            return
        shop = Workshop(name="骨巷熬胶坊", alley="西市骨巷")
        session.add(shop)
        session.flush()
        session.add(AlleyConfig(alley="东巷", cap=2, enabled=True))
        session.add(AlleyConfig(alley="西巷", cap=1, enabled=True))
        layout = [
            ("锅-1", "东巷", Kettle.STATUS_BOILING, 0, 96.0),
            ("锅-2", "东巷", Kettle.STATUS_COLD, 1, None),
            ("锅-3", "东巷", Kettle.STATUS_COLD, 2, None),
            ("锅-4", "东巷", Kettle.STATUS_COLD, 3, None),
            ("锅-5", "东巷", Kettle.STATUS_DRAWN, 4, 102.0),
            ("锅-6", "西巷", Kettle.STATUS_BOILING, 5, 82.0),
            ("锅-7", "西巷", Kettle.STATUS_COLD, 6, None),
            ("锅-8", "西巷", Kettle.STATUS_COLD, 7, None),
            ("锅-9", "西巷", Kettle.STATUS_COLD, 8, None),
            ("锅-10", "西巷", Kettle.STATUS_DRAWN, 9, 94.0),
        ]
        for code, alley, status, bench, peak in layout:
            kettle = Kettle(workshop_id=shop.id, code=code, status=status, bench=bench, alley=alley)
            session.add(kettle)
            session.flush()
            if peak is not None:
                session.add(CookLog(kettle_id=kettle.id, peak_temp_c=peak, operator="worker"))
        session.commit()
