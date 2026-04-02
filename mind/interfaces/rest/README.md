# MIND REST API

这是当前维护中的第一个上层接口适配器，直接依赖
`mind.application.MindService`，而不是直接调用 `mind.Memory`。

## 启动

先在 `mind.toml` 中配置：

```toml
[rest]
host = "127.0.0.1"
port = 8000
cors_allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
```

然后运行：

```bash
python -m mind.interfaces.rest.run
```

如果要显式指定配置文件：

```bash
python -m mind.interfaces.rest.run --toml tests/fixtures/frontend-smoke.toml.example
```

这条路径适合本地前后端联调 smoke，它会使用仓库内维护的 fake/local
配置，而不是依赖 `mind.toml` 的在线 provider。

## Docker Compose

仓库还维护了 compose 化启动路径：

```bash
docker compose up rest
docker compose up web
```

其中：

- `rest` 会自动带起 `postgres`
- `web` 会自动带起 `rest` 和 `postgres`
- 默认 compose 会把工作区根目录 `mind.toml` 挂载到容器内并作为默认配置源
- 如需单独启动 Qdrant：`docker compose --profile qdrant up qdrant`

补充说明：

- compose 默认会读取本地工作区中的 `mind.toml`
- 这里使用的是 bind mount，而不是把 `mind.toml` 打进镜像
- compose 启动 `rest` 时会附带 `--compose-adapt`，对同一份 `mind.toml` 做最小容器适配：
  - `rest.host` 的 loopback 地址会改成 `0.0.0.0`
  - Postgres / pgvector / STL DSN 里的 `localhost` 会改成 `postgres`
- 如果你修改了后端代码，需要重新 build `rest`：

```bash
docker compose up -d --build rest
```

- 如果你只修改了 `mind.toml` 配置，因为 compose 使用的是 bind mount，所以只需要：

```bash
docker compose restart rest
```

- 如果你修改了前端页面，需要重新 build `web`：

```bash
docker compose up -d --build web
```

- 如果你确实需要别的配置文件，请显式调整 compose 挂载或 `MIND_TOML_PATH`，
  而不是依赖仓库内第二套 compose 默认 TOML

## 路由

- `GET /healthz`
- `GET /api/v1/capabilities`
- `GET /api/v1/chat/models`
- `POST /api/v1/chat/completions`
- `POST /api/v1/ingestions`
- `POST /api/v1/memories/search`
- `GET /api/v1/memories`
- `GET /api/v1/memories/{memory_id}`
- `PATCH /api/v1/memories/{memory_id}`
- `DELETE /api/v1/memories/{memory_id}`
- `GET /api/v1/memories/{memory_id}/history`

## Owner Selector

REST 层统一使用 canonical owner selector：

```json
{
  "external_user_id": "alice"
}
```

或：

```json
{
  "anonymous_session_id": "anon-123"
}
```

两者必须二选一。

## Chat Model Profiles

前端可切换的聊天模型来自 `mind.toml` 中单独维护的 `[chat]` 配置，而不是直接暴露
全部 `[llm.*]` provider。这样可以保证：

- 前端只看到允许交互式切换的聊天模型
- STL extraction / decision 阶段仍然保持后端内部策略

示例：

```toml
[chat]
default_profile_id = "fast"

[chat.profiles.fast]
label = "Fast"
provider = "leihuo"
model = "qwen3.5-flash"
temperature = 0.2
timeout = 60.0
```

## 示例

聊天：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "owner": {"external_user_id": "alice"},
    "model_profile_id": "fast",
    "messages": [{"role": "user", "content": "I love black coffee"}]
  }'
```

写入 memory：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingestions \
  -H 'Content-Type: application/json' \
  -d '{
    "owner": {"external_user_id": "alice"},
    "messages": [{"role": "user", "content": "I love black coffee"}]
  }'
```
