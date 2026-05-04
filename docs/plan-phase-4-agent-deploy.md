# 轮 4：Agent + 部署 — agent_loop.py + Dockerfile + docker-compose.yml

## 背景

轮 3 完成了 HTTP 服务 + 日历同步。用户现在可以 `curl POST /what-if` 出排程，`POST /commit` 推日历。但这需要手动调 API。本轮实现自然语言入口——Agent 层（Claude API tool-use loop）+ 容器化部署。

## 本轮任务

### `app/agent_loop.py`

一个极薄的 tool-use loop：

```python
while True:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=conversation_history,
    )
    if response.stop_reason == "tool_use":
        for block in response.content:
            if block.type == "tool_use":
                # 写 pending log
                # 等用户批准（input("批准? [y/N] ")）
                # 调对应的 App API
                # 写 ok/err log
                # 把 tool_result 喂回消息历史
    elif response.stop_reason == "end_turn":
        # 展示文本给用户
        print(response.content[0].text)
        # 等用户下一条输入
```

**SYSTEM_PROMPT 内容：**

```
你是 projarvis 日程助手。你帮用户管理任务和日程。

## 架构

用户 → 你（Agent）→ App API（HTTP）→ CP-SAT 引擎 → CalDAV → 手机日历

## 规则

1. 每次调工具前，先生成一个 pending 日志行，等用户批准后执行
2. 工具 2-6（add/modify/delete/block_time/constraints）只暂存变更，不动真计划
3. what_if() 才跑引擎看影响。用户确认后 commit() 才生效
4. 用 get_plan() 获取当前上下文（任务列表、已排程时间）
5. title 始终放 metadata 里。用户说的任务名就是 title

## 插件调用参考

deadline
  参数: {}（空开关）
  metadata: deadline (ISO 8601)
  L1: 任务必须在 deadline 周或之前  L2: end <= deadline_slot
  触发: constraint + task.metadata.deadline

dependency
  参数: pairs [[前置id, 后继id]] 必填, buffer_slots int=0
  metadata: 无
  L1: 前置周 <= 后继周  L2: 后继.start >= 前置.end + buffer_slots
  触发: constraint 含非空 pairs

energy_budget
  参数: focus_budget_per_day int=0, exercise_budget_per_day int=0,
        focus_target_per_day int=0, exercise_target_per_day int=0,
        focus_shortfall_weight int=0, exercise_shortfall_weight int=0
        [仅L2] focus/exercise_budget_overrides dict={}
  metadata: focus_multiplier float=0, exercise_multiplier float=0
  L1: 周级硬上限+软目标（权重1/3）  L2: 天级硬上限+软目标（全权重）
  触发: constraint + metadata.multiplier

fixed_time
  参数: {}（空开关）
  metadata: fixed_time (ISO 8601)
  L1: 任务锁定到 fixed_time 所在周  L2: start==fixed_start, end==fixed_end
  触发: constraint + task.metadata.fixed_time

schedule_lock
  参数: {}（空开关）
  metadata: locked_start (ISO 8601, merger 自动填入，你不要设)
  L1: 锁任务到 locked_start 所在周  L2: start==locked_slot
  触发: merger 自动管理

schedule_stability
  参数: default_weight int=2 (L1) / default_weight int=5 (L2)
  metadata: previous_start (ISO 8601, merger 自动填入)
  行为: 偏离惩罚。L1 weight=2 刚好>1，抗1周偏移

task_distribution (仅L1)
  参数: mode str="earliest_bias", task_ids list[str] 必填(even模式), weight int=1
  模式: earliest_bias(默认)/even/front_load/ramp_up/deadline_driven
  metadata: 无

task_break (仅L2)
  参数: default_gap int=1, exempt_task_ids list[str]=[]
  metadata: 无
```

**8 个工具 JSON Schema：**

对应轮 3 的 8 个 API 端点。每个工具调用 → 调对应 API。agent_loop 不 import app 模块，通过 HTTP 连接。

```python
TOOLS = [
    {"name": "get_plan", ...},           # GET /api/v1/plan
    {"name": "add_tasks", ...},          # POST /api/v1/tasks/add
    {"name": "modify_task", ...},        # POST /api/v1/tasks/{id}/modify
    {"name": "delete_task", ...},        # DELETE /api/v1/tasks/{id}
    {"name": "block_time", ...},         # POST /api/v1/block-time
    {"name": "set_constraints", ...},    # POST /api/v1/constraints
    {"name": "what_if", ...},            # POST /api/v1/what-if
    {"name": "commit", ...},             # POST /api/v1/commit
]
```

### `Dockerfile`

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -e .
COPY app/ ./app/
COPY projarvis/ ./projarvis/
RUN mkdir -p /app/config/state
ENV TZ=Asia/Shanghai
EXPOSE 8000
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

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

### 更新 `pyproject.toml`

追加依赖到 `[project.dependencies]`（各轮次各自加自己的依赖）：

```toml
"fastapi>=0.110",
"uvicorn>=0.29",
"icalendar>=5.0",
"caldav>=1.3",
"anthropic>=0.30",
```

## 依赖

- 轮 3：`app.server`（HTTP API 必须在运行）
- 需添加到 `pyproject.toml` 的 `[project.dependencies]`：`anthropic`

## 重要细节

- agent_loop 是独立的命令行程序，不嵌入 server。通过 HTTP 与 server 通信
- 用户批准机制：CLI 中用 `input()`。后续可换成 Telegram bot / WebSocket / iOS Shortcut
- pending log 格式见 plan：`{timestamp} pending {tool} | {params} | {摘要}`
- model 用 `claude-sonnet-4-6`。后续可按需切 Opus
- 环境变量 `ANTHROPIC_API_KEY` 需要设置

## 不做什么

- 不做 Telegram/WebSocket/iOS Shortcut 集成。CLI 交互先用着
- 不写测试文件

## 验证

```bash
# 启动服务
docker compose up -d

# 另开终端启动 agent
export ANTHROPIC_API_KEY=sk-ant-...
python -m app.agent_loop

# 对话
你: 今天下午休息，帮我看看行不行
Agent: [pending] block_time | "2026-05-03", "14:00", "18:00" | 移除下午可用块
批准? [y/N] y
Agent: [ok] block_time | 完成
Agent: [pending] what_if | 跑调度
批准? [y/N] y
Agent: [ok] what_if | 1个任务移动，容量85%→72%
      休息的话，写周报移到明天上午9点。还剩12小时。确认吗？
你: 行
Agent: [pending] commit | merge + 推日历
批准? [y/N] y
Agent: [ok] commit a7d9e0f1 | 2个事件已推CalDAV
```
