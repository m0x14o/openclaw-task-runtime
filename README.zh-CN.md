# openclaw-task-runtime

[English README](./README.md) | [快速上手](./QUICKSTART.zh-CN.md) | [复制即用提示词（中文）](./OPENCLAW_ONE_LINER.zh-CN.md) | [Copy-paste prompts (EN)](./OPENCLAW_ONE_LINER.md)

一个给 **OpenClaw** 用的轻量长任务运行层。

## 给小白的 3 句话

如果你懒得看文档，直接复制下面 3 句之一给你自己的 OpenClaw。

### 1）一句话安装

> 帮我把 https://github.com/m0x14o/openclaw-task-runtime 装到当前 OpenClaw 工作区里：克隆到 `repos/openclaw-task-runtime`，运行 `python3 install.py`，把任务恢复检查接到 `HEARTBEAT.md`，然后告诉我已经可以用了。

### 2）一句话把一个已有 skill 接进来

> 帮我把 `<skill-name>` 接到 `openclaw-task-runtime`：用模板生成 `task_resume.py`，给长任务阶段加 task card 和 checkpoint，只对安全阶段开自动续跑，顺手把最简用法写进这个 skill 的文档，最后直接告诉我以后怎么用。

### 3）一句话执行一个临时长任务（哪怕还没做成 skill）

> 把下面这件事按“可续跑的长任务”来跑：如果还没有 skill，就先在 `tmp/task-runtime/<task-slug>/task_resume.py` 生成一个临时 adapter，建 task card，给安全阶段打 checkpoint，开 heartbeat 自动续跑。最少给我三种结果之一：最终结果 / 部分结果 / 明确卡点。任务是：<在这里替换成你的任务>

你**不需要先理解** task card、checkpoint、adapter 这些词。先复制一句跑起来就行。

它补的是长任务最容易掉链子的几件事：

- 持久化任务卡（`data/task-runs/*.json`）
- checkpoint
- heartbeat 巡检卡死任务
- 通过 skill adapter 做安全自动续跑

这不是业务 skill，而是一个 **workspace 级 runtime**。任何 skill 都可以接进来。

## 这东西解决什么问题

OpenClaw 很能干活，但长任务经常会遇到这些破事：

- 过夜任务半路卡住
- agent 超时后状态断掉
- 最贵的前半段都跑完了，结果渲染最后一步炸了
- 一个任务明明适合分阶段恢复，却只能当成一坨黑箱重来

`openclaw-task-runtime` 的目标，就是给 OpenClaw 补一个小而实用的 durable execution 层，不引入一整套重型工作流平台。

## 它不是什么

它不是：

- plugin 系统替代品
- 队列系统
- 通用 DAG 引擎
- 某个单独业务 skill

更准确地说，它是：

> **给 OpenClaw workspace 用的 LangGraph / Inngest-lite**

## 一句话用法

如果你只想直接复制，优先看这里：`OPENCLAW_ONE_LINER.zh-CN.md`

如果你的 OpenClaw 能在自己的 workspace 里执行 shell，上面那 3 句通常就够了。

## 手动安装

把仓库 clone 到你的 OpenClaw workspace 里：

```bash
git clone https://github.com/m0x14o/openclaw-task-runtime ~/.openclaw/workspace/repos/openclaw-task-runtime
cd ~/.openclaw/workspace/repos/openclaw-task-runtime
python3 install.py
```

安装器会自动：

- 复制 runtime 脚本到 `<workspace>/scripts/`
- 复制文档到 `<workspace>/docs/openclaw-task-runtime/`
- 复制 adapter 模板到 `<workspace>/templates/openclaw-task-runtime/`
- 以幂等方式把 Task Runtime Recovery Check 接到 `<workspace>/HEARTBEAT.md`

## 工作方式

```text
heartbeat -> task_runtime_watch.py -> task_runtime_resume.py -> skill adapter
```

### 核心文件

- `scripts/task_runtime.py`：任务卡 / run-state 管理器
- `scripts/task_runtime_watch.py`：heartbeat 看门狗，负责巡检 stale 任务
- `scripts/task_runtime_resume.py`：通用恢复 dispatcher
- `templates/task_resume.py`：给你自己的任务或 skill 用的 adapter 模板

## 什么时候适合用

适合这类任务：

- 预计运行超过 10 分钟
- 多阶段
- 可以从文件 / 中间状态 checkpoint 接着跑
- 某些 phase 允许自动重试

例如：

- 过夜研究任务
- 报告生成
- 批处理分析
- 代码分析 + 测试 + 汇总
- 可安全 checkpoint 的多步排障

## 哪些动作不要自动续跑

除非你自己加了安全门禁，否则别自动重试这些不可逆动作：

- 对外发消息
- 发布
- 部署
- 重启
- 浏览器确认点击
- 删除数据

## 没做成 skill，也能用

任务**不需要先做成正式 skill**，也能吃到这套 runtime。

`resume_adapter` 本质上只是一个脚本路径，它可以放在：

- `skills/<skill>/scripts/task_resume.py`：适合可复用 skill
- `tmp/task-runtime/<task-slug>/task_resume.py`：适合一次性长任务
- `automation/<task-slug>/task_resume.py`：适合重复出现但还没正式封装的流程

### 给小白最友好的方式

如果还没有 skill，就先让 OpenClaw 为当前任务生成一个临时 adapter，先跑起来。等这类任务反复出现，再把它升级成正式 skill。

更多说明见：`docs/no-skill-usage.md`

## 最小接入方式

### 1）创建 task card

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py create \
  --task-type my-long-task \
  --title "My long-running job" \
  --mode overnight \
  --phase collect \
  --resume-adapter ~/.openclaw/workspace/skills/my-skill/scripts/task_resume.py \
  --allow-auto-resume \
  --stale-after-minutes 30 \
  --max-retries 2
```

### 2）在阶段之间写 checkpoint

```bash
python3 ~/.openclaw/workspace/scripts/task_runtime.py checkpoint <task_id> \
  --phase render \
  --artifact normalized_input=/tmp/job-normalized.json \
  --message "ready to render final report"
```

### 3）实现 skill adapter

先拷贝模板：

```bash
cp ~/.openclaw/workspace/templates/openclaw-task-runtime/task_resume.py \
  ~/.openclaw/workspace/skills/my-skill/scripts/task_resume.py
```

然后在这个 adapter 里写清楚：你的 skill 哪些 phase 可以安全恢复，恢复时依赖哪些 artifacts。

## Adapter 契约

你的 adapter 至少要做到：

1. 接受 `--task-id` 和可选 `--timeout-seconds`
2. 读取 task card
3. 只恢复安全 / 幂等 phase
4. 更新 `status`、`phase`、`artifacts`、`last_checkpoint_at`
5. 尽量把结果以 JSON 打到 stdout

完整约定见：`docs/task-runtime-adapters.md`

## 设计思路

这套东西借了几家成熟方案的脑子，但故意保持很轻：

- **LangGraph**：durable / stateful task flow
- **Inngest**：step/run state + flow control
- **Temporal**：workflow 纪律和 replay 思维

但它不想把你正常的 OpenClaw workspace 变成一套重型平台。

## 仓库结构

```text
.
├── docs/
├── scripts/
├── templates/
├── install.py
└── README.md
```

## License

MIT
