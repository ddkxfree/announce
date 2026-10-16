# 02 · Agent 评测与 Docker 沙箱（阶段 5 前半）

## 这一轮做了什么

让平台能评测"模型 + Agent"在需要执行环境的任务上的表现：每道题一个隔离的 Docker 容器，Agent 在容器里执行命令，结束后由测试脚本检查容器的最终状态来判分。

对应路线图阶段 5 的第 1～5 步：

| 步骤 | 内容 | 主要代码 |
|---|---|---|
| 1. 沙箱抽象 | `Sandbox` 接口（`exec`、`write_file`、`read_file`、`copy_dir`、`close`）和 `SandboxProvider`；Docker 实现：每题一个容器，默认断网、限内存和 CPU，按目录内容哈希构建并复用镜像，带标签便于清理 | `sandbox/base.py`、`sandbox/docker.py` |
| 2. Runner 接入沙箱 | 任务声明 `sandbox` 后，runner 为每道题创建容器，传给 Solver 和 Scorer，结束后无论成败都销毁；环境故障归为新的 outcome `env_error`，与模型调用失败 `api_error` 分开 | `core/runner.py`、`core/types.py` |
| 3. 基线 Agent | 最简单的工具调用循环：`bash` 和 `submit` 两个工具，步数上限、命令超时、输出截断；参数解析错误、未知工具等会作为观察结果返回给模型而不是让整题失败 | `solvers/basic_agent.py` |
| 4. 轨迹记录 | 每一步记录模型输出、工具调用、执行结果、退出码、token 和耗时；`harness show --sample` 打印完整轨迹；汇总里新增 Agent 统计（结束原因、平均步数、失败命令数） | `core/types.py`、`analysis/stats.py`、`cli.py` |
| 5. 自建终端任务 | 仿照 Terminal-Bench / Harbor 的目录约定写了 3 个任务，外加 Oracle Solver 用参考答案验证任务本身是否正确 | `tasks/terminal.py`、`tasks/terminal_data/`、`solvers/oracle.py` |

配套改动：

- 模型接口支持传入 `tools` 并解析返回的 `tool_calls`；缓存键包含工具定义。
- Solver 统一返回 `SolveResult`（messages、output、steps），可以接收沙箱。
- 新增 `SandboxScorer` 协议：需要在容器里判分的 Scorer。这类运行无法离线 `rescore`，会被跳过并给出说明。
- `none/none` 占位模型，用于不需要模型的 Oracle 运行。
- 新命令 `harness sandbox-cleanup`，清理异常退出后残留的容器。

## 任务格式

```text
tasks/terminal_data/<task-id>/
├── instruction.md          给 Agent 的任务描述
├── task.toml               元数据（难度、类别）和测试超时
├── environment/Dockerfile  Agent 所在的容器
├── tests/test.sh           退出码 0 表示通过；Agent 结束后才复制进容器，Agent 看不到
└── solution/solve.sh       参考答案，供 Oracle Solver 使用
```

三个任务：

| 任务 | 难度 | 内容 | 考察点 |
|---|---|---|---|
| `hello-file` | easy | 创建内容精确的文件 | 基本的工具使用 |
| `count-errors` | medium | 统计日志中级别为 ERROR 的行数 | 有陷阱：部分 INFO、WARN 消息正文里也有 "ERROR"，直接 `grep -c ERROR` 会多数 |
| `fix-mean` | easy | 修复 `mean` 函数的 bug，不能改动其他函数 | 读代码、改代码、验证 |

## 怎么用

```bash
# 需要 Docker
# 1. 先用 Oracle 验证任务本身没问题（不需要模型）
uv run harness run -m none/none -t terminal -p terminal.solver=oracle

# 2. 用模型跑 Agent
ollama pull qwen2.5:3b-instruct
uv run harness run -c configs/terminal-ollama.yaml

# 3. 查看某道题的完整轨迹
uv run harness show runs/<run_id> --sample terminal/count-errors

# 异常退出后清理残留容器
uv run harness sandbox-cleanup
```

## 验证

- 单元测试从 47 个增加到 67 个，全部通过：
  - 16 个 Agent 测试使用内存版的假沙箱，覆盖工具执行、提交、步数上限、错误的工具调用、沙箱创建失败、出错时也会销毁沙箱、每题独立沙箱、缓存回放和 Agent 统计。
  - 4 个 Docker 集成测试（没有 Docker 时自动跳过），覆盖命令执行、文件读写、超时、断网隔离、容器清理，以及两条对任务本身的检查：**Oracle 必须解出全部任务，什么都不做的 Agent 必须全部失败**。后者能防止"不做任何事也能通过"的测试。
- Oracle 运行：3/3 通过，没有残留容器。
- 用本地 CPU 上的 Ollama 跑了两个真实模型：

| 模型 | 通过 | 结束原因 | 平均步数 |
|---|---|---|---|
| qwen2.5:0.5b-instruct | 0/3 | 不调用工具直接回复 | 约 2 |
| qwen2.5:3b-instruct | 1/3 | 全部调用 submit | 3.3 |

## 从轨迹里看到的现象

这一轮最有价值的是轨迹记录，失败原因一眼就能看出来：

- **0.5B 模型"假装完成"**：在 `hello-file` 上只执行了 `touch /app/greeting.txt` 创建空文件，然后回复"文件已创建，内容是 Hello, harness!"。测试检查容器的真实状态，所以判为失败。只看模型的回复会被误导。
- **3B 模型掉进了 `count-errors` 的陷阱**：执行 `grep -c 'ERROR'` 得到 211，直接写入答案。实际级别为 ERROR 的行只有 96 行，其余是正文里提到 ERROR 的 INFO 和 WARN 消息。这说明任务设计能区分"会用命令"和"理解数据格式"。
- **3B 模型在 `fix-mean` 上原地打转**：看了源码后连续执行了 7 次什么都没改的 `sed`（例如把 `total ` 替换成 `total `），没有验证结果就提交了。

## 遗留和下一步

阶段 5 剩下的部分：

1. 接入 SWE-bench Lite / Verified 的少量样本：复用官方 Docker 镜像和单测判分。
2. 把 mini-swe-agent 包装成 Solver 插件，和基线 Agent 在同一批题上对比。
3. 接入真实的 Terminal-Bench 任务，验证不改 `core/` 就能接入第二种 Agent 评测集。

已知限制：

- 沙箱只有 Docker 一种实现，镜像需要有 `bash` 和 `timeout` 命令。
- 单题没有总时长上限，目前靠步数上限和单条命令超时来约束。
- 自建任务只有 3 个，结论只能说明链路可用，不能说明模型能力。
