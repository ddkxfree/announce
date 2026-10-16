# 03 · 接入 SWE-bench 与 mini-swe-agent（阶段 5 第 6、7 步）

## 这一轮做了什么

| 步骤 | 内容 | 主要代码 |
|---|---|---|
| 6. 接入 SWE-bench Lite | 新任务 `swebench`：数据集固定 revision，每道题用官方预构建镜像起一个容器；判分复用 `swebench` 官方包的评测脚本和日志解析；带"参考补丁" Oracle | `tasks/swebench.py` |
| 7. mini-swe-agent 作为 Solver 插件 | 不改 mini-swe-agent 源码，给它的 `DefaultAgent` 提供两个桥接对象：模型调用走平台的 `generate`（缓存、重试、超时、token 统计照常），命令在平台的沙箱里执行；轨迹照常记录 | `solvers/mini_swe_agent.py` |

配套改动：

- `swebench` 和 `mini-swe-agent` 作为可选依赖：`uv sync --extra swebench`。不装也能跑其他评测集，用到时会提示安装命令。
- 终端任务也能用 mini-swe-agent：`-p terminal.solver=mini`。
- 基线 Agent 的系统提示里的工作目录改为可配置（终端任务是 `/app`，SWE-bench 是 `/testbed`）。
- 新配置 `configs/swebench-ollama.yaml`。
- CI 安装全部可选依赖后再跑测试。

## SWE-bench 怎么判分

每道题是一个真实 GitHub issue，容器里 `/testbed` 是对应仓库在修复前的代码。Solver 结束后，`SweBenchScorer`：

1. **取补丁**：如果 Solver 的输出本身是 diff（mini-swe-agent 按约定会提交 diff），直接用；否则在容器里 `git diff` 收集改动（基线 Agent 走这条路）。
2. **重置并打补丁**：`git reset --hard` 回到原始代码，再依次尝试 `git apply`、`git apply --reject`、`patch --fuzz=5`，和官方做法一致。
3. **跑官方评测脚本**：恢复测试文件、打上隐藏的测试补丁、运行 FAIL_TO_PASS（修复前失败、修复后应通过）和 PASS_TO_PASS（不能被改坏）两组测试。
4. **用官方函数 `get_eval_report` 解析日志**，两组测试全部通过才算 `resolved`。

`score.extracted` 会写明结果类别，方便归因：

| extracted | 含义 |
|---|---|
| `resolved` | 解决 |
| `unresolved` | 补丁打上了，但有测试没过；`details.failed_tests` 列出没过的测试 |
| `empty_patch` | 没改任何代码 |
| `patch_failed` | 补丁打不上 |
| `tests_not_run` | 测试没能跑起来（例如改出了语法错误） |
| `timeout` | 评测脚本超时 |

评测基础设施本身出问题（例如 `pip install` 联网失败）会抛出 `SandboxError`，记为 `env_error`，不算模型答错。

和官方 harness 的差别：官方在一个**全新容器**里打补丁判分，我们在 Agent 用过的同一个容器里重置代码后判分。`/testbed` 之外的改动（比如 Agent 装了额外的包）会保留下来。在 scorer 的指纹里记录了 `same_container: true`。

另一个注意点：SWE-bench 容器**开着网络**，因为官方评测脚本里有 `pip install -e .`。

## mini-swe-agent 怎么接进来

mini-swe-agent 的 Agent 循环只依赖两个对象：模型（`query`）和环境（`execute`）。我们各写了一个实现：

```text
DefaultAgent.run()  ── 在工作线程里同步运行
   ├── HarnessModel.query()        → 平台的 generate（缓存 / 重试 / 超时 / token）
   └── SandboxEnvironment.execute() → 平台的沙箱 exec（同一个容器，最后由 scorer 判分）
```

- 用的是 mini-swe-agent 自带的 prompt 配置（SWE-bench 用 `swebench.yaml`，终端任务用 `mini.yaml`），只覆盖步数上限；花费上限关掉，因为成本由平台统计。
- 它的结束状态映射到平台的 `finish_reason`：`Submitted` → `submit`，`LimitsExceeded` → `max_steps`（outcome 为 `step_limit`），其他如 `RepeatedFormatError` 原样保留。
- 每次模型调用和命令执行都记成 `Step`，所以 `harness show --sample` 看到的轨迹格式和基线 Agent 一样。
- 它的 prompt、配置和版本号都进了 solver 指纹，升级 mini-swe-agent 会在 `harness diff` 里显示出来。

这一步也验证了路线图里"加新 Agent 不改 core"的原则：`core/` 没有任何改动。

## 验证

- 测试从 67 个增加到 83 个，全部通过：
  - mini-swe-agent 桥接 8 个：提交流程、提交命令失败时不算提交、步数上限、连续格式错误、命令超时提示、模型报错向上抛出、指纹稳定性、终端任务可选 mini。
  - SWE-bench 6 个：补丁来源选择、git 失败归为环境错误、`git apply` 失败后回退到 `patch`、打不上的补丁、任务参数校验。
  - Docker 集成 2 个（本地有镜像时才跑）：参考补丁必须 `resolved`，什么都不做必须 `empty_patch`。
- Oracle（参考补丁）在两道题上都判为解决，且确实跑了测试：

| 实例 | FAIL_TO_PASS | PASS_TO_PASS | 结果 |
|---|---|---|---|
| django__django-11099 | 3/3 | 19/19 | resolved |
| pytest-dev__pytest-5227 | 3/3 | 34/34 | resolved |

## 用本地 3B 模型的实测

CPU 上的 Ollama `qwen2.5:3b-instruct`，最多 20 步：

| 任务 | Solver | 结果 | 结束原因 |
|---|---|---|---|
| 3 个终端任务 | 基线 Agent（上一轮） | 1/3 | 全部 submit |
| 3 个终端任务 | mini-swe-agent | 1/3 | 全部 RepeatedFormatError |
| SWE-bench 2 题 | 基线 Agent | 0/2 | 第 1 步就空回复（并发 2 和并发 1 各跑一次，结果相同） |
| SWE-bench 2 题 | mini-swe-agent | 0/2 | 1 题格式错误、1 题用完 20 步 |

0 分在意料之中：SWE-bench 对 3B 模型太难。这一轮的目的是证明链路可用，结论要用更强的模型（例如云端 API）才有意义。从轨迹里看到的现象：

- **小模型照抄 prompt 里的示例**：mini-swe-agent 的 prompt 里有一行示例 `[Makes bash tool call with {"command": "ls -la"} as arguments]`，3B 模型把这行文字原样写进回复，而不是真的调用工具，连续 3 次后被判 `RepeatedFormatError`。同一个模型在基线 Agent 的简短 prompt 下能正常调用工具。**Agent 框架的 prompt 风格会显著影响小模型的表现**，这正是要把 Agent 当作可替换的 Solver 来对比的原因。
- **原地打转**：pytest-5227 上 mini-swe-agent 用满了 20 步，其中十几次是 `ls -la src`，一直没有打开要改的文件。
- **空回复（原因未定，待排查）**：基线 Agent 在 SWE-bench 第 1 步拿到 `content=""`、没有工具调用、`finish_reason=stop`，但消耗了 55～86 个输出 token。并发改成 1 后仍然稳定复现，所以不是并发导致的。用同步版 OpenAI SDK 手工发同样的 messages 和 tools，有一次返回了正常的工具调用。推测是模型生成的工具调用格式不对，被 Ollama 的解析丢掉了，但还没确认。复现方法：取 `samples.jsonl` 第一条的前两条 messages，带 `BASH_TOOL`、`SUBMIT_TOOL` 调用 `get_model("ollama/qwen2.5:3b-instruct").generate(...)`（Ollama 0.40.5）。这类情况在 outcome 上和"模型不会做"看起来一样，以后的诊断报告里值得单独标出来，例如把"输出 token 大于 0 但文本和工具调用都为空"归为一类。

## 遗留和下一步

1. 用更强的模型（云端 API）在同样 2 题和更多题上重跑，比较基线 Agent 和 mini-swe-agent。
2. 阶段 5 第 8 步：接入真实的 Terminal-Bench 任务。
3. 可以加一个导出命令，把补丁写成官方 `predictions.jsonl` 格式，用官方 harness 交叉验证我们的判分。
4. 判分改成在全新容器里进行，和官方完全一致。

已知限制：

- SWE-bench 镜像只有 x86_64 版本。在 Apple Silicon 的 Mac 上需要 Docker Desktop 的 Rosetta 转译，能跑但更慢。每个镜像 3～4 GB。
- 单题没有总时长上限；CPU 上的小模型跑一道 SWE-bench 可能要十几分钟。
