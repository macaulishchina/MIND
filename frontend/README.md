# MIND Frontend Workbench

内部体验 / 调试工作台，只通过 REST API 与 MIND 交互。

主页是 chat-first：

- 像标准 LLM 对话窗口一样发送和接收消息
- 通过后端返回的 curated chat profiles 选择聊天模型
- 用 `Submit Memory` 把本次会话里“尚未提交过”的新 turn 写入 MIND
- 在右侧 `Memory Explorer` 查看、修改、删除和追踪 memory history

## 开发

```bash
npm install
npm run dev
```

## 验证

```bash
npm run test
npm run build
```

默认读取：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

建议同时启动后端：

```bash
python -m mind.interfaces.rest.run
```

## Live Smoke

如果要跑安全的前后端联调 smoke，建议使用仓库内维护的 fake/local 配置：

```bash
python -m mind.interfaces.rest.run --toml tests/fixtures/frontend-smoke.toml.example
VITE_API_BASE_URL=http://127.0.0.1:18000 npm run dev
```

这条路径会连接运行中的真实 REST adapter，但不会触发 live 模型调用。

## Docker Compose

如果只想快速起完整体验栈：

```bash
docker compose up web
```

它会自动带起：

- `postgres`
- `rest`
- `web`

默认访问：

- Web: `http://127.0.0.1:8080`
- REST: `http://127.0.0.1:8000`

compose 默认会让运行中的 `rest` 读取工作区根目录的 `mind.toml`。

注意：

- compose 下前端看到的 chat model 来自运行中的 `rest` 服务，而不是前端自己本地读取 TOML
- 默认 `rest` 读的是工作区里的 `mind.toml`
- compose 会自动把 `mind.toml` 中面向本机开发的 loopback 值做容器内适配，
  例如 `localhost` 数据库主机改成 `postgres`，`rest.host` 改成 `0.0.0.0`
- 如果你改了前端页面，需要执行：

```bash
docker compose up -d --build web
```

- 如果你改了 Python 后端或 REST 行为，需要执行：

```bash
docker compose up -d --build rest
```

- 如果你只改了 `mind.toml` 里的聊天模型或其他配置，执行：

```bash
docker compose restart rest
```

- 如果前后端都改了，直接执行：

```bash
docker compose up -d --build rest web
```

- 如果你的 `mind.toml` 还不存在，先执行：

```bash
cp mind.toml.example mind.toml
```

工作台固定包含两个区域：

- `Chat Workspace`：known / anonymous owner、chat model 切换、对话、增量 memory submit
- `Memory Explorer`：list、detail、update、delete、history
