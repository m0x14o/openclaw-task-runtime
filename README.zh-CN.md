# openclaw-task-runtime

[English README](./README.md) | [一句话安装提示词](./OPENCLAW_ONE_LINER.md)

一个给 **OpenClaw** 用的轻量长任务运行层。

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

把下面这句话直接发给你自己的 OpenClaw：

> Install and enable https://github.com/m0x14o/openclaw-task-runtime in the current OpenClaw workspace: clone it into `repos/openclaw-task-runtime`, run `python3 install.py`, wire the task runtime recovery check into `HEARTBEAT.md`, and if no skill exists for my task, scaffold a temporary resume adapter under `tmp/task-runtime/<task-slug>/task_resume.py`. Then show me the minimal `task card + resume_adapter` pattern for my next long-running task.

如果你的 OpenClaw 能在自己的 workspace 里执行 shell，这一句通常就够了。

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
