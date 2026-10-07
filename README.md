# GlueKettle-01 · 骨巷熬胶坊

一排熬锅作业台。登录后是横向锅位，点锅登记煮胶峰值并改状态。前端是原生 JS，没有 React/Vue/Svelte。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Starlette 路由表（不是 FastAPI Depends） |
| 结构 | SQLModel 实体 + `domain.py` 门槛 |
| 数据 | SQLModel / SQLAlchemy · psycopg2 · PostgreSQL 15 |
| 前端 | 原生 ES Module · Vite 仅打包 |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4790
- API：http://localhost:8790
- PostgreSQL：localhost:6190

## 演示账号

`admin` / `123456`，`worker` / `123456`

## 业务规则

锅不可标「已出胶」，除非最近一次煮胶峰值 **≥ 90℃**。规则在 `backend/app/domain.py`。

每巷（东巷 / 西巷）各有一份「巷口并存」配置：熬煮中并存上限（正整数）+ 启用开关。开关开着且该巷已顶格时，再把该巷冷锅拨成「熬煮中」会被中文挡住；邻巷数字互不影响。登记峰值、标已出胶不读巷上限。

- 顶栏可切「锅位作业台」与「巷口并存」两页。
- 「巷口并存」专页按巷展示上限、开关、当前占用（实时等于该巷真实熬煮中锅数）；管理员可改，操作工只读。
- 接口：`GET /api/alleys` 看各巷占用；`PUT /api/alleys/{alley}` 改上限/开关（仅管理员）。
- 拨锅核对与落库在同一事务并锁住该巷配置行，两人同时抢拨也只能一人一挡。

## 快速启动

```bash
cd GlueKettle/GlueKettle-01
docker compose up --build
```
