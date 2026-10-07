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

### 巷口并存上限

- 每巷（东巷 / 西巷）可配置「熬煮中」并存上限（正整数）与启用开关，存在 `alley_config` 表。
- 开关开启且该巷已达上限时，把**冷锅**拨成「熬煮中」会被后端中文挡住（如「西巷熬煮中已达上限（2 口），不能再入煮」）；东巷、西巷各锁各巷、计数互不影响。
- 登记煮胶峰值、标「已出胶」均不读巷上限；关闭开关后即使占用已超上限也可继续入煮。
- 并发安全：入煮事务先 `SELECT ... FOR UPDATE` 锁该巷配置行再计数，顶格时两口冷锅几乎同时抢入煮，两笔都会落空，不会超限入库。
- 顶栏可进入「锅位作业台」与「巷口并存」独立专页；专页按巷展示上限、启用与否、当前占用（= 该巷真实熬煮中锅数）。管理员可改，操作工只读（`PATCH /api/alleys/{巷}` 仅 admin）。


## 快速启动

```bash
cd GlueKettle/GlueKettle-01
docker compose up --build
```
