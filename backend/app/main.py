from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import SQLModel, select

from app.db import engine, get_session
from app.domain import RuleError, assert_alley_has_room, assert_can_set_status, latest_peak
from app.models import AlleyConfig, CookLog, Kettle, User, Workshop
from app.security import make_token, parse_token, verify_password
from app.seed import migrate, seed_demo


async def current_user(request: Request) -> User | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    username = parse_token(header.split(" ", 1)[1])
    if not username:
        return None
    with get_session() as session:
        return session.exec(select(User).where(User.username == username)).first()


def load_kettle(session, kettle_id: int) -> Kettle | None:
    return session.exec(
        select(Kettle).where(Kettle.id == kettle_id).options(selectinload(Kettle.cooks))
    ).first()


def kettle_json(kettle: Kettle) -> dict:
    return {
        "id": kettle.id,
        "code": kettle.code,
        "status": kettle.status,
        "bench": kettle.bench,
        "alley": kettle.alley,
        "latestPeakC": latest_peak(kettle),
        "cookCount": len(kettle.cooks or []),
    }


def alley_rows(session) -> list[dict]:
    """按巷给出上限、开关与当前占用；占用实时数真实熬煮中锅数。"""
    configs = session.exec(select(AlleyConfig).order_by(AlleyConfig.alley)).all()
    counts = dict(
        session.exec(
            select(Kettle.alley, func.count())
            .where(Kettle.status == Kettle.STATUS_BOILING)
            .group_by(Kettle.alley)
        ).all()
    )
    return [
        {"alley": c.alley, "cap": c.cap, "enabled": c.enabled, "used": int(counts.get(c.alley, 0))}
        for c in configs
    ]


async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "GlueKettle"})


async def login(request: Request):
    body = await request.json()
    with get_session() as session:
        user = session.exec(select(User).where(User.username == body.get("username", ""))).first()
        if user is None or not verify_password(body.get("password", ""), user.password_hash):
            return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)
        return JSONResponse(
            {"access_token": make_token(user.username), "user": {"username": user.username, "role": user.role}}
        )


async def me(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    return JSONResponse({"username": user.username, "role": user.role})


async def board(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    with get_session() as session:
        shop = session.exec(select(Workshop)).first()
        if shop is None:
            return JSONResponse({"detail": "尚无熬胶坊"}, status_code=404)
        kettles = session.exec(
            select(Kettle)
            .where(Kettle.workshop_id == shop.id)
            .options(selectinload(Kettle.cooks))
        ).all()
        loaded = sorted(kettles, key=lambda k: k.bench)
        return JSONResponse(
            {"workshop": shop.name, "alley": shop.alley, "kettles": [kettle_json(k) for k in loaded]}
        )


async def list_alleys(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    with get_session() as session:
        return JSONResponse({"alleys": alley_rows(session)})


async def update_alley(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    if user.role != "admin":
        return JSONResponse({"detail": "仅管理员可改巷口并存"}, status_code=403)
    alley = request.path_params["alley"]
    body = await request.json()
    with get_session() as session:
        config = session.exec(select(AlleyConfig).where(AlleyConfig.alley == alley)).first()
        if config is None:
            return JSONResponse({"detail": "巷不存在"}, status_code=404)
        if "cap" in body:
            cap = body["cap"]
            if isinstance(cap, bool) or not isinstance(cap, (int, float)) or int(cap) != cap or int(cap) < 1:
                return JSONResponse({"detail": "上限必须是正整数"}, status_code=400)
            config.cap = int(cap)
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                return JSONResponse({"detail": "开关必须是布尔值"}, status_code=400)
            config.enabled = body["enabled"]
        session.add(config)
        session.commit()
        return JSONResponse({"alleys": alley_rows(session)})


async def add_cook(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    kettle_id = int(request.path_params["kettle_id"])
    body = await request.json()
    try:
        peak = float(body.get("peakTempC"))
    except (TypeError, ValueError):
        return JSONResponse({"detail": "峰值温度必须是数字"}, status_code=400)
    with get_session() as session:
        kettle = load_kettle(session, kettle_id)
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        session.add(CookLog(kettle_id=kettle.id, peak_temp_c=peak, operator=user.username))
        session.commit()
        kettle = load_kettle(session, kettle_id)
        return JSONResponse(kettle_json(kettle))


async def set_status(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    kettle_id = int(request.path_params["kettle_id"])
    body = await request.json()
    new_status = body.get("status", "")
    with get_session() as session:
        kettle = load_kettle(session, kettle_id)
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        try:
            assert_can_set_status(kettle, new_status)
            if new_status == Kettle.STATUS_BOILING and kettle.status != Kettle.STATUS_BOILING:
                # 锁住该巷配置行，核对与落库同事务，两人同抢也只能一个过一个挡
                config = session.exec(
                    select(AlleyConfig).where(AlleyConfig.alley == kettle.alley).with_for_update()
                ).first()
                if config is not None and config.enabled:
                    used = session.exec(
                        select(func.count(Kettle.id)).where(
                            Kettle.alley == kettle.alley,
                            Kettle.status == Kettle.STATUS_BOILING,
                        )
                    ).one()
                    assert_alley_has_room(kettle.alley, config.cap, used)
        except RuleError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        kettle.status = new_status
        session.add(kettle)
        session.commit()
        kettle = load_kettle(session, kettle_id)
        return JSONResponse(kettle_json(kettle))


def init() -> None:
    SQLModel.metadata.create_all(engine)
    migrate()
    seed_demo()


init()

app = Starlette(
    routes=[
        Route("/api/health", health),
        Route("/api/auth/login", login, methods=["POST"]),
        Route("/api/auth/me", me),
        Route("/api/board", board),
        Route("/api/alleys", list_alleys),
        Route("/api/alleys/{alley}", update_alley, methods=["PUT"]),
        Route("/api/kettles/{kettle_id:int}/cooks", add_cook, methods=["POST"]),
        Route("/api/kettles/{kettle_id:int}/status", set_status, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)
