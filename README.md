# agentHarnessForModelEvaluation

这是一个接入主流模型评测的 agent，进行大模型评测的平台。

当前完成的是**平台内核（阶段 1～4）**：用 GSM8K 和 MMLU 两个评测集跑通"加载数据 → 构造 prompt → 调模型 → 抽取答案 → 打分 → 统计 → 归档"的完整链路，并具备并发、重试、缓存续跑、可复现记录、离线重打分和运行对比能力。

## 快速开始

```bash
# 安装依赖（需要 uv：https://docs.astral.sh/uv/）
uv sync

# 方式一：本地 Ollama，不需要 API key
ollama pull qwen2.5:0.5b-instruct
uv run harness run -c configs/ollama-smoke.yaml

# 方式二：云端 API（以阿里云百炼为例）
export DASHSCOPE_API_KEY=sk-...
uv run harness run -m dashscope/qwen-plus -t gsm8k -t mmlu --limit 50
```

模型用 `provider/model` 指定，所有兼容 OpenAI 接口的服务都能接：

| provider | 默认 base_url | API key 环境变量 |
|---|---|---|
| `openai` | `OPENAI_BASE_URL` 或 OpenAI 官方 | `OPENAI_API_KEY` |
| `dashscope` | 阿里云百炼兼容模式 | `DASHSCOPE_API_KEY` |
| `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| `ollama` | `http://localhost:11434/v1` | 不需要 |
| `vllm` | `http://localhost:8000/v1` | 不需要 |

其他兼容服务可以用 `--base-url` 覆盖。

## 命令

```bash
harness list-tasks                                   # 列出已注册的评测集
harness run -c configs/example.yaml                  # 按配置文件运行
harness run -m ollama/qwen2.5:0.5b-instruct -t gsm8k --limit 20 \
    -p gsm8k.n_shot=3 --temperature 0 --seed 0       # 命令行参数覆盖配置
harness show runs/<run_id>                           # 汇总 + 抽取方式分布
harness show runs/<run_id> -t gsm8k --outcome extract_failed -n 5   # 查看某类失败样本
harness rescore runs/<run_id>                        # 改了打分逻辑后，不调模型直接重打分
harness diff runs/<a> runs/<b>                       # 对比两次运行：配置/环境差异 + 逐样本翻转
```

`-p task.key=value` 的值按 YAML 解析，例如 `-p mmlu.subjects=[anatomy,virology]`。

## 架构

```text
src/harness/
├── core/
│   ├── types.py      Sample、GenerateConfig、ModelOutput、Score、SampleResult、Outcome
│   ├── model.py      Model 抽象、兼容 OpenAI 接口的模型、MockModel、provider 预设
│   ├── solver.py     Solver 协议和 PromptSolver（system + few-shot 多轮 + 问题）
│   ├── scorer.py     NumberMatchScorer（数值题）、ChoiceScorer（选择题）
│   ├── task.py       Task、DatasetSpec、任务注册表、确定性抽样
│   ├── runner.py     并发、重试、超时、缓存、落盘、manifest
│   ├── cache.py      按请求内容哈希的磁盘缓存
│   ├── manifest.py   运行环境和任务指纹
│   └── config.py     YAML 运行配置
├── tasks/            每个评测集一个文件：gsm8k.py、mmlu.py
├── analysis/         stats（bootstrap 置信区间）、rescore、diff
└── cli.py
```

几个核心概念：

- **Task** = 数据集（`DatasetSpec`，固定 HuggingFace revision）+ `Solver` + `Scorer` + 参数。
- **Solver** 拿到的是 runner 包装好的 `generate` 函数（已带缓存、重试、超时），因此后续的 Agent 循环可以多次调用模型，而不用关心这些工程细节。
- **Scorer** 只依赖样本和模型原始输出，所以可以离线重跑。
- 新增评测集只需在 `tasks/` 下写一个文件并用 `@register("name")` 注册，不需要改 runner。

## 每次运行的产物

```text
runs/<run_id>/
├── manifest.json          运行配置、环境、每个任务的数据集版本和指纹、汇总结果
├── gsm8k/
│   ├── samples.jsonl      每道题一行：样本、完整 messages、原始输出、token、耗时、抽取结果、outcome
│   └── summary.json
└── mmlu/...
```

`manifest.json` 记录了复现一次评测需要的全部信息：

- 模型 provider、名称、base_url（不含 API key）
- 采样参数（temperature、max_tokens、seed 等）
- 数据集路径、split、**固定的 revision**，以及抽样后样本 id 列表的哈希
- Solver 指纹（prompt 模板、system、few-shot 设置）和 Scorer 指纹（抽取规则）
- harness 的 git commit、工作区是否有未提交修改、Python 版本、关键依赖版本、`uv.lock` 的哈希

## 诊断指标

每道题都会被归为以下一类，而不只是"对/错"：

| outcome | 含义 |
|---|---|
| `correct` | 答对 |
| `wrong` | 抽到了答案但答错 |
| `extract_failed` | 没能从输出中抽取出答案，通常是格式问题而不是能力问题 |
| `truncated` | 输出因 `max_tokens` 被截断 |
| `api_error` | 调用失败（重试后仍失败），计入分母，避免虚高 |

此外还会统计**抽取方式分布**（答案是按 `The answer is`、`####`、`\boxed{}` 还是兜底规则抽出来的），用来判断模型是否遵守了要求的输出格式。

## 实测示例

在 Ollama 上用 `qwen2.5:0.5b-instruct`（CPU）运行 `configs/ollama-smoke.yaml` 的结果：

| task | n | accuracy | 95% CI | correct | wrong | extract_failed | truncated |
|---|---|---|---|---|---|---|---|
| gsm8k | 20 | 0.450 | [0.25, 0.65] | 9 | 9 | 0 | 2 |
| mmlu | 40 | 0.425 | [0.275, 0.575] | 17 | 22 | 0 | 1 |

从这次运行能直接看到几个现象：

- **格式不遵守**：prompt 要求以 `The answer is <number>` 结尾，但 GSM8K 有 18/20 的回答用了 `\boxed{}`。如果只认 `The answer is`，这些都会被误判为错。
- **样本量太小时置信区间很宽**：20 道题的 95% 置信区间横跨 40 个百分点，这种规模下的分数差异不能说明问题。
- **指标抖动**：把 temperature 改成 0.8 再跑一次，准确率仍是 0.450，但 `harness diff` 显示有 2 道题由对变错、2 道题由错变对，20 道题的输出全部不同。总分不变不代表结果稳定。
- **缓存续跑**：相同配置第二次运行全部命中缓存，耗时从约 70 秒降到约 3 秒。

## 测试

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

测试全部离线运行（使用 `MockModel` 和内存数据集），覆盖答案抽取、outcome 分类、重试与超时、并发上限、缓存续跑、manifest、重打分和 diff。

## 路线图

- [x] 阶段 1～4：平台内核（GSM8K、MMLU、并发/重试/缓存、可复现 manifest、诊断统计、rescore、diff）
- [ ] 阶段 5：Agent 评测和 Docker 沙箱，接入 SWE-bench / Terminal-Bench，mini-swe-agent 作为 Solver 插件
- [ ] 阶段 6：LLM-as-Judge（交换位置去偏、多裁判投票）
- [ ] 阶段 7：多次运行的方差分析、错误自动归类报告
- [ ] 阶段 8：用 Agent 自动接入新评测集
