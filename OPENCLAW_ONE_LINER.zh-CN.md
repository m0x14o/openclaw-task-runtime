# 给你自己的 OpenClaw 直接复制这 3 句

## 1）安装

> 帮我把 https://github.com/m0x14o/openclaw-task-runtime 装到当前 OpenClaw 工作区里：克隆到 `repos/openclaw-task-runtime`，运行 `python3 install.py`，把任务恢复检查接到 `HEARTBEAT.md`，然后告诉我已经可以用了。

## 2）接入一个已有 skill

> 帮我把 `<skill-name>` 接到 `openclaw-task-runtime`：用模板生成 `task_resume.py`，给长任务阶段加 task card 和 checkpoint，只对安全阶段开自动续跑，顺手把最简用法写进这个 skill 的文档，最后直接告诉我以后怎么用。

## 3）执行一个临时长任务（哪怕还没做成 skill）

> 把下面这件事按“可续跑的长任务”来跑：如果还没有 skill，就先在 `tmp/task-runtime/<task-slug>/task_resume.py` 生成一个临时 adapter，建 task card，给安全阶段打 checkpoint，开 heartbeat 自动续跑。最少给我三种结果之一：最终结果 / 部分结果 / 明确卡点。任务是：<在这里替换成你的任务>
