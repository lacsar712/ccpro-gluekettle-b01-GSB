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
from app.domain import (
    RuleError,
    assert_can_enter_boiling,
    assert_can_set_status,
    latest_peak,
)
from app.models import AlleyConfig, CookLog, Kettle, User, Workshop
from app.security import make_token, parse_token, verify_password
from app.seed import migrate_schema, seed_demo


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


def boiling_count(session, alley: str) -> int:
    return session.exec(
        select(func.count())
        .select_from(Kettle)
        .where(Kettle.alley == alley, Kettle.status == Kettle.STATUS_BOILING)
    ).one()


def alley_json(session, cfg: AlleyConfig) -> dict:
    return {
        "alley": cfg.alley,
        "cap": cfg.cap,
        "enabled": cfg.enabled,
        "occupied": boiling_count(session, cfg.alley),
    }


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


async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "GlueKettle"})


async def login(request: Request):
    body = await request.json()
    with get_session() as session:
        user = session.exec(select(User).where(User.username == body.get("username", ""))).first()
        if user is None or not verify_password(body.get("password", ""), user.password_hash):
            return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)
        return JSONResponse(
            {
                "access_token": make_token(user.username),
                "user": {"username": user.username, "role": user.role},
            }
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
        cfgs = session.exec(select(AlleyConfig).order_by(AlleyConfig.id)).all()
        loaded = sorted(kettles, key=lambda k: (k.alley, k.bench))
        return JSONResponse(
            {
                "workshop": shop.name,
                "alley": shop.alley,
                "kettles": [kettle_json(k) for k in loaded],
                "alleys": [alley_json(session, c) for c in cfgs],
            }
        )


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
        # 登峰值不读巷上限
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
            # 无效状态、出胶温度门槛在此校验，均不读巷上限
            assert_can_set_status(kettle, new_status)
            if kettle.status == Kettle.STATUS_COLD and new_status == Kettle.STATUS_BOILING:
                # 先锁该巷配置行：同巷并发入煮在此串行，邻巷各锁各行互不影响
                cfg = session.exec(
                    select(AlleyConfig)
                    .where(AlleyConfig.alley == kettle.alley)
                    .with_for_update()
                ).first()
                # 锁后再读该锅当前状态与该巷真实占用（Read Committed 下能看到前一笔已提交的结果）
                current_status = session.exec(
                    select(Kettle.status).where(Kettle.id == kettle.id)
                ).first()
                if current_status == Kettle.STATUS_COLD:
                    occupied = boiling_count(session, kettle.alley)
                    if cfg is not None:
                        assert_can_enter_boiling(
                            kettle,
                            alley_name=cfg.alley,
                            enabled=cfg.enabled,
                            cap=cfg.cap,
                            boiling_count=occupied,
                        )
        except RuleError as exc:
            session.rollback()
            return JSONResponse({"detail": str(exc)}, status_code=400)
        kettle.status = new_status
        session.add(kettle)
        session.commit()
        kettle = load_kettle(session, kettle_id)
        return JSONResponse(kettle_json(kettle))


async def alleys(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    with get_session() as session:
        cfgs = session.exec(select(AlleyConfig).order_by(AlleyConfig.id)).all()
        return JSONResponse([alley_json(session, c) for c in cfgs])


async def update_alley(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    if user.role != "admin":
        return JSONResponse({"detail": "仅管理员可修改巷口配置"}, status_code=403)
    alley_name = request.path_params["alley"]
    body = await request.json()
    with get_session() as session:
        cfg = session.exec(
            select(AlleyConfig).where(AlleyConfig.alley == alley_name).with_for_update()
        ).first()
        if cfg is None:
            return JSONResponse({"detail": "巷口不存在"}, status_code=404)
        if "cap" in body:
            raw = body["cap"]
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
                return JSONResponse({"detail": "并存上限必须是正整数"}, status_code=400)
            cfg.cap = raw
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                return JSONResponse({"detail": "启用开关必须是布尔值"}, status_code=400)
            cfg.enabled = body["enabled"]
        session.add(cfg)
        session.commit()
        cfg = session.exec(select(AlleyConfig).where(AlleyConfig.id == cfg.id)).first()
        return JSONResponse(alley_json(session, cfg))


def init() -> None:
    SQLModel.metadata.create_all(engine)
    migrate_schema()
    seed_demo()


init()

app = Starlette(
    routes=[
        Route("/api/health", health),
        Route("/api/auth/login", login, methods=["POST"]),
        Route("/api/auth/me", me),
        Route("/api/board", board),
        Route("/api/alleys", alleys),
        Route("/api/alleys/{alley:str}", update_alley, methods=["PATCH"]),
        Route("/api/kettles/{kettle_id:int}/cooks", add_cook, methods=["POST"]),
        Route("/api/kettles/{kettle_id:int}/status", set_status, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)
