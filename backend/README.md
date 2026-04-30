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
- `PUT /api/domain/characters` / `GET /api/domain/characters`：角色规范化表读写
- `PUT /api/domain/chat/{character_id}` / `GET /api/domain/chat/{character_id}`：聊天消息规范化表读写
- `PUT /api/domain/memories/{character_id}` / `GET /api/domain/memories/{character_id}`：记忆规范化表读写
- `PUT /api/domain/presets` / `GET /api/domain/presets`：预设规范化表读写
- `PUT /api/domain/regex` / `GET /api/domain/regex`：正则脚本规范化表读写
- `PUT /api/domain/worldinfo` / `GET /api/domain/worldinfo`：世界书规范化表读写
- `POST /api/memory/upsert`：写入记忆向量到 Qdrant
- `POST /api/memory/search`：向量检索记忆
- `GET /api/plugins`：列出插件
- `POST /api/plugins`：创建插件
- `POST /api/plugins/{plugin_id}/invoke`：执行插件动作（HTTP / Bluetooth）

## 4) 命名空间隔离

后端通过请求头 `X-RPH-User` 进行用户隔离；前端会自动传当前用户 UUID。

## 5) Bluetooth 插件说明

Bluetooth 执行基于 `bleak`，系统需具备蓝牙能力（常见于本机运行，不建议直接跑在无蓝牙容器中）。
