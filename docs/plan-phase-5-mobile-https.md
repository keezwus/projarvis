# 轮 5：Agent 端点 + HTTPS + 初始化

## 背景

轮 4 完成了 agent_loop 纯函数引擎和 Docker 部署。但：
- agent_loop 的 `send_user_message` / `approve_pending_tools` 没有 HTTP 入口，手机无法调用
- 服务器跑在 HTTP 明文，移动端无法直连
- 没有初始化流程，首次启动需要手动 curl 引导

本轮做三件事：Agent HTTP 端点 → Caddy HTTPS 反向代理 → 系统初始化。

---

## 1. Agent HTTP 端点

在 `app/server.py` 新增 2 个端点，薄封装 agent_loop 的两个函数。

### `POST /api/v1/agent/message`

```python
@app.post("/api/v1/agent/message")
def agent_message(body: AgentMessageRequest):
    from .agent_loop import send_user_message
    return send_user_message(body.session_id, body.user_text)
```

入参：`{session_id: str | None, user_text: str}`

### `POST /api/v1/agent/approve`

```python
@app.post("/api/v1/agent/approve")
def agent_approve(body: AgentApproveRequest):
    from .agent_loop import approve_pending_tools
    return approve_pending_tools(body.session_id, body.approved)
```

入参：`{session_id: str, approved: bool}`

### `DELETE /api/v1/agent/session/{session_id}`

```python
@app.delete("/api/v1/agent/session/{session_id}")
def agent_clear_session(session_id: str):
    from .agent_loop import clear_session
    clear_session(session_id)
    return {"status": "ok"}
```

### `app/models.py` 追加

```python
class AgentMessageRequest(BaseModel):
    session_id: str | None = None
    user_text: str

class AgentApproveRequest(BaseModel):
    session_id: str
    approved: bool
```

---

## 2. Caddy HTTPS 反向代理

### `Caddyfile`

```
your-domain.com {
    reverse_proxy projarvis:8000
}
```

替换 `your-domain.com` 为实际域名。

### `docker-compose.yml` 追加

```yaml
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports: ["443:443", "80:80"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on:
      - projarvis

volumes:
  # ... 原有 ...
  caddy_data:
```

Caddy 自动向 Let's Encrypt 申请证书、自动续期，无需手动管理。80 端口用于 HTTP→HTTPS 重定向和 ACME challenge。

---

## 3. 系统初始化

### 初始化脚本 `scripts/init.sh`

```bash
#!/bin/bash
set -e

# 1. 创建 config 目录和默认配置（如不存在）
if [ ! -f config/app_config.toml ]; then
    echo "创建默认配置..."
    cat > config/app_config.toml <<'TOML'
[horizon]
weeks = 4

[availability]
monday    = [["09:00", "12:00"], ["14:00", "18:00"]]
tuesday   = [["09:00", "12:00"], ["14:00", "18:00"]]
wednesday = [["09:00", "12:00"], ["14:00", "18:00"]]
thursday  = [["09:00", "12:00"], ["14:00", "18:00"]]
friday    = [["09:00", "12:00"], ["14:00", "17:00"]]
saturday  = []
sunday    = []

[caldav]
url = "http://baikal:80/dav.php/calendars/user/default/"
username = "user"
password = "changeme"
calendar_name = "projarvis"

[engine]
max_time_seconds = 30.0
random_seed = 42
TOML
fi

# 2. 确保 state 目录存在（server 启动时会 init git repo）
mkdir -p config/state

# 3. 启动服务
docker compose up -d

# 4. 等待服务就绪
echo "等待 projarvis 启动..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/api/v1/plan > /dev/null 2>&1; then
        echo "projarvis 已就绪"
        break
    fi
    sleep 2
done

# 5. 引导 Baikal 初始化（如需要）
echo "Baikal 管理界面: http://<server-ip>:8080"
echo "首次使用需在 Baikal 中创建用户和日历"
echo "CalDAV URL: https://<server-ip>/dav.php/calendars/<user>/<calendar>/"
```

### `docker-compose.yml` 追加 baikal 初始化引导

Baikal 容器首次启动后需要手动通过 Web UI 初始化（创建 admin 用户、创建 calendar）。这是 Baikal 本身的限制，不做自动化。

compose 里 baikal 的 ports 保持 `127.0.0.1:8080:80`，不对外暴露，因为 CalDAV 同步是 server 直连 baikal 内网地址，用户只需通过 Caddy 的 443 访问 projarvis。

---

## 文件变更清单

| 文件 | 动作 |
|---|---|
| `app/server.py` | 新增 3 个 agent HTTP 端点 |
| `app/models.py` | 新增 `AgentMessageRequest`, `AgentApproveRequest` |
| `app/__init__.py` | 导出新模型 |
| `Caddyfile` | **Create** — 反向代理配置 |
| `docker-compose.yml` | 追加 caddy 服务 + caddy_data volume |
| `scripts/init.sh` | **Create** — 初始化脚本 |
| `docs/plan-phase-5-mobile-https.md` | **Create** — 本文档 |

## 不做什么

- 不做手机 App（Android/iOS），那是独立仓库的事
- 不做 SESSION_DB 持久化（内存够用，后续再切 SQLite）
- 不做 Baikal 自动初始化（需要 Web UI 交互）

## 验证

```bash
# 初始化
bash scripts/init.sh

# 测试 agent message
curl -X POST https://your-domain.com/api/v1/agent/message \
  -H 'Content-Type: application/json' \
  -d '{"user_text": "帮我看看当前排程"}'

# → 返回 {session_id, status, tools_to_approve, response_text}

# 手机 App 验证：同一接口 + 批准流程
```
