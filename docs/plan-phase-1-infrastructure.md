# 轮 1：基础设施 — config.py + models.py + state.py

## 背景

projarvis 是一个 CP-SAT 调度引擎，分 L1（多周分配）和 L2（单周精确排程）。现在要在引擎之上加一个应用层，管状态持久化、任务合并、引擎编排、日历同步。详见 `docs/plan.md`。

## 本轮任务

创建三个文件：

### `app/config.py` — Pydantic Settings

从 `config/app_config.toml` 读配置：

```toml
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
```

用 `pydantic-settings` 的 `BaseSettings`，支持 TOML 文件 + 环境变量覆盖。暴露一个 `AppConfig` 类。

### `app/models.py` — 所有数据类

```python
# PlanState：完整计划状态
#   horizon_start: str          # 对齐周一 00:00
#   horizon_weeks: int          # 默认 4
#   weekly_available: dict      # day_name → [[start, end]]
#   overrides: list[dict]       # 时段封锁
#   tasks: dict[str, TaskInfo]  # UUID → TaskInfo
#   task_solutions: dict[str, TaskSolution]  # UUID → TaskSolution
#   constraints: list[ConstraintSpec]
#   last_status: str
#   revision: int
#   random_seed: int

# TaskInfo（引擎输入）：
#   id: str                    # UUID
#   total_duration: int        # 15分钟槽位数
#   priority: int = 100
#   l2_metadata: dict          # title, deadline, fixed_time, focus_multiplier,
#                              # exercise_multiplier, locked_start, previous_start

# TaskSolution（引擎输出）：
#   task_id: str
#   start: str                 # ISO 8601
#   end: str                   # ISO 8601
#   duration_minutes: int
#   week_index: int

# ConstraintSpec:
#   type: str
#   params: dict

# DeltaRequest（LLM 传入）：
#   add: list[AddTask]
#   modify: list[ModifyTask]
#   delete: list[str]          # UUID 列表

# AddTask:
#   title: str                 # 会放入 l2_metadata.title
#   duration_minutes: int
#   priority: int = 100
#   metadata: dict = {}        # deadline, fixed_time, focus_multiplier, exercise_multiplier

# ModifyTask:
#   id: str                    # UUID
#   title: str | None = None
#   duration_minutes: int | None = None
#   priority: int | None = None
#   metadata: dict | None = None
```

所有数据类用 dataclass 或 Pydantic。关键：title 放 metadata（`l2_metadata.title`）。locked_start/previous_start 由 merger 自动填入，LLM 不设。

### `app/state.py` — Git + 文件读写

```
config/state/ 目录就是一个 git repo
├── .git/
├── state.json    ← 当前计划
├── log           ← 操作日志（后续轮次用）
└── dialog/       ← 对话日志（后续轮次用）
```

函数：
- `init_git_repo(state_dir)` — 如果 state_dir 不存在或无 .git，`git init`
- `load(config)` — 读 state.json，反序列化为 PlanState。不存在则从 config 创建默认状态（horizon_start=本周一，空 tasks，空 solutions，seed 从 config 拿）
- `save(config, state)` — 原子写入（写 .tmp → os.replace）。`git add state.json && git commit -m "save"`
- `git_log(config, n=20)` — `git log --oneline -n`
- `git_diff(config, ref1, ref2)` — `git diff ref1..ref2 -- state.json`

`save()` 时自动 `git add && git commit`。后续轮次用到的分支操作（checkout -b whatif, merge）先不实现——但 save 的 commit 已经为它们铺好路。

注意：state.json 放在 `config.state_dir`（默认 `config/state/`），不是项目根目录。

## 依赖

需要 `Python >= 3.11`（stdlib `tomllib`）。需添加到 `pyproject.toml` 的 `[project.dependencies]`（各轮次各自加自己的依赖，不用 optional groups）：

- `pydantic>=2.5`, `pydantic-settings>=2.1` — 配置和数据模型
- 标准库 `json`, `subprocess`, `datetime`, `uuid`, `tomllib`

另外需在 `.gitignore` 追加 `config/state/`，防止外层 repo 跟踪内层 state git repo。

## 不做什么

- 不实现 merger、runner、caldav、server、agent loop
- 不实现 git 分支操作（checkout/merge）
- 不写测试文件（本轮手动验证）

## 验证

```python
from app.config import AppConfig
from app.state import load, save, init_git_repo, git_log

config = AppConfig()
config.state_dir = "/tmp/projarvis-test/state"
init_git_repo(config.state_dir)

state = load(config)
print(state.horizon_start)  # 本周一 00:00
print(state.tasks)           # {}

save(config, state)
print(git_log(config))
```
