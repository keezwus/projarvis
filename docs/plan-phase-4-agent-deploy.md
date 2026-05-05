# 轮 4：Agent + 部署 — agent_loop.py + Dockerfile + docker-compose.yml

## 背景

轮 3 完成了 HTTP 服务 + 日历同步。用户现在可以 `curl POST /what-if` 出排程，`POST /commit` 推日历。但这需要手动调 API。本轮实现自然语言入口——Agent 层（Claude API tool-use loop）+ 容器化部署。

## 本轮任务

### `app/agent_loop.py`

无阻塞 I/O 的会话式 tool-use 引擎。暴露 3 个纯函数，不 import app 模块，通过 HTTP（`requests`）与 server 通信。

#### 架构

```
send_user_message(session_id, user_text) → {session_id, status, tools_to_approve, response_text}
approve_pending_tools(session_id, approved) → 同上
clear_session(session_id) → None
```

返回结构：
```python
{
    "session_id": str,
    "status": "awaiting_tools" | "completed",
    "tools_to_approve": [{"id": str, "name": str, "input": dict}] | None,
    "response_text": str | None,
}
```

#### `send_user_message(session_id: str | None, user_text: str) → dict`

1. 若 session_id 为空 → 新建 session，init messages
2. 若 session_id 已存在 → 从 SESSION_DB 取出
3. user_text 追加到 messages，调用 Claude API
4. 解析响应：
   - `end_turn` → 返回 status: "completed" + 文本
   - `tool_use` → 所有 tool_use block 打包，存入 pending_tools，返回 status: "awaiting_tools" + 工具列表

#### `approve_pending_tools(session_id: str, approved: bool) → dict`

1. 取出 pending_tools
2. approved=True → 逐条执行 HTTP 调用 → 构造 tool_result
3. approved=False → 构造 tool_result(content="用户未批准此操作")
4. tool_results 追加到 messages
5. 立刻再次调用 Claude API 继续生成
6. 返回结果（同 send_user_message）

#### HITL 批准粒度

每次 Claude API response 里的所有 tool_use block 打成一包，整批申请用户批准。用户一次 y/N 决定全部执行或全部拒绝。

#### 7 个 Tool

| Tool | HTTP | 参数 |
|---|---|---|
| `get_plan` | `GET /api/v1/plan` | 无 |
| `add_tasks` | `POST /api/v1/tasks/add` | `tasks: [{title, duration_minutes, priority?, metadata?}]` |
| `modify_task` | `POST /api/v1/tasks/{task_id}/modify` | `task_id`, `title?`, `duration_minutes?`, `priority?`, `metadata?` |
| `delete_tasks` | `DELETE /api/v1/tasks` | `task_ids: [string, ...]` |
| `block_time` | `POST /api/v1/block-time` | `blocks: [{date, start, end}, ...]` |
| `set_constraints` | `POST /api/v1/constraints` | `constraints: [{type, params}], mode?` |
| `what_if` | `POST /api/v1/what-if` | 无 |

`commit` 不是 Claude tool。Claude 的职责是生成计划、展示影响（what_if 结果），用户在 App 看到后自己调 `POST /api/v1/commit`。

#### 环境变量

- `PROJARVIS_API_URL` — server 地址，默认 `http://localhost:8000`
- `ANTHROPIC_API_KEY` — Claude API key（必须）

### `app/agent_system_prompt.md`

SYSTEM_PROMPT 独立文件，包含架构说明、5 条规则、8 个插件参考文档、INFEASIBLE 应对指南。中文。agent_loop.py 启动时读取。

### API 批量化改造（`app/models.py` + `app/server.py`）

新增模型：`BlockTimeItem(date, start, end)`、`DeleteTasksRequest(task_ids: list[str])`

`BlockTimeRequest` 改为 `blocks: list[BlockTimeItem]`。

端点变更：
- `DELETE /api/v1/tasks/{task_id}` → `DELETE /api/v1/tasks`（批量删除）
- `POST /api/v1/block-time` → 循环处理 blocks 数组，返回 `{status: "ok", blocked: N}`

### `Dockerfile`

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 git && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY pyproject.toml ./
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; print('\n'.join(deps))" > /tmp/deps.txt && \
    pip install --no-cache-dir -r /tmp/deps.txt

COPY app/ ./app/
COPY projarvis/ ./projarvis/
RUN pip install --no-cache-dir --no-deps . && mkdir -p /app/config/state

ENV TZ=Asia/Shanghai
EXPOSE 8000
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

原计划文档中 `pip install -e .` 在 COPY 源码之前执行会失败，已修正为先装依赖、再 COPY 源码、再 install 包。

### `docker-compose.yml`

```yaml
version: "3.8"
services:
  baikal:
    image: ckulka/baikal:nginx
    restart: unless-stopped
    ports: ["127.0.0.1:8080:80"]
    volumes:
      - baikal_config:/var/www/baikal/config
      - baikal_data:/var/www/baikal/Specific

  projarvis:
    build: .
    restart: unless-stopped
    ports: ["127.0.0.1:8000:8000"]
    volumes:
      - ./config:/app/config
    environment:
      - PROJARVIS_CALDAV_URL=http://baikal:80/dav.php/calendars/user/default/
      - PROJARVIS_CALDAV_USERNAME=user
      - PROJARVIS_CALDAV_PASSWORD=changeme
    depends_on:
      - baikal

volumes:
  baikal_config:
  baikal_data:
```

### `.dockerignore`

排除 state、cache、测试、文档等构建无关文件。

### 更新 `pyproject.toml`

`[project.dependencies]` 追加：
```toml
"anthropic>=0.30",
"requests>=2.28",
```

## 依赖

- 轮 3：`app.server`（HTTP API 必须在运行）
- 新增依赖：`anthropic`（Claude API SDK）、`requests`（agent HTTP 调用）

## 重要细节

- agent_loop 是纯函数模块，无阻塞 I/O。不 import app。通过 HTTP 与 server 通信
- 会话状态存储在 SESSION_DB 字典，未来可换 SQLite/Redis
- 用户批准机制：每次 Claude API response 中的所有 tool_use block 整批挂起，由调用方（手机 App / 未来 HTTP 端点）决定批准或拒绝
- model 用 `claude-sonnet-4-6`。后续可按需切 Opus
- 环境变量 `ANTHROPIC_API_KEY` 需要设置

## 不做什么

- 不做 CLI 交互（`if __name__ == "__main__"` 块），agent_loop.py 仅暴露纯函数
- 不做 agent HTTP 端点（`POST /api/v1/agent/message`, `POST /api/v1/agent/approve`），留到手机对接轮次
- 不做 Telegram/WebSocket/iOS Shortcut 集成
- 不写测试文件

## 验证

```bash
# 1. Build & start
docker compose up -d

# 2. Batch API smoke
curl -X POST http://localhost:8000/api/v1/block-time -H 'Content-Type: application/json' \
  -d '{"blocks": [{"date": "2026-05-06", "start": "14:00", "end": "18:00"}]}'

curl -X DELETE http://localhost:8000/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"task_ids": ["nonexistent"]}'  # → 404

# 3. Agent 函数验证
export ANTHROPIC_API_KEY=sk-ant-...
python -c "
from app.agent_loop import send_user_message
res = send_user_message(None, '帮我加一个明天上午写代码的任务')
print(res)
"
```
