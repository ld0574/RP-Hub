# RP-Hub Backend（FastAPI）

> 说明：本目录提供 RP-Hub 的后端化存储与向量检索服务。聊天记录、角色、设置等主数据落 PostgreSQL；记忆向量落 Qdrant。

## 1) 本地启动（推荐 Docker）

```bash
cd backend
docker compose up -d --build
```

启动后：
- API: `http://127.0.0.1:8000`
- API 文档: `http://127.0.0.1:8000/docs`
- Qdrant: `http://127.0.0.1:6333/dashboard`

## 2) 本地裸跑（不使用 Docker）

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## 3) 主要 API

- `PUT /api/storage/{key}`：写入任意 JSON（前端主存储）
- `GET /api/storage/{key}`：读取 JSON
- `DELETE /api/storage/{key}`：删除键
- `POST /api/memory/upsert`：写入记忆向量到 Qdrant
- `POST /api/memory/search`：向量检索记忆
- `GET /api/plugins`：列出插件
- `POST /api/plugins`：创建插件
- `POST /api/plugins/{plugin_id}/invoke`：执行插件动作（HTTP / Bluetooth）

## 4) 命名空间隔离

后端通过请求头 `X-RPH-User` 进行用户隔离；前端会自动传当前用户 UUID。

## 5) Bluetooth 插件说明

Bluetooth 执行基于 `bleak`，系统需具备蓝牙能力（常见于本机运行，不建议直接跑在无蓝牙容器中）。

## 6) 常见问题：`permission denied for schema public`

如果看到类似错误：

```text
psycopg2.errors.InsufficientPrivilege: permission denied for schema public
```

说明当前数据库用户没有 `public` schema 的建表权限。可用两种方式处理：

### 方式 A（推荐，本地开发）：重建数据库卷后重启

> 会清空本地 Postgres 数据。

```bash
cd backend
docker compose down -v
docker compose up -d --build
```

`docker-compose.yml` 已挂载 `initdb/01-grants.sql`，首次初始化会自动授予权限。

### 方式 B（保留数据）：手动授予权限

```bash
docker exec -it rphub-postgres psql -U postgres -d rphub -c "GRANT USAGE, CREATE ON SCHEMA public TO rphub; ALTER SCHEMA public OWNER TO rphub;"
```
