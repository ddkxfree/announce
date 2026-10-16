# 01 · 平台内核：GSM8K 与 MMLU（阶段 1～4）

## 这一轮做了什么

把评测的完整链路跑通："加载数据 → 构造 prompt → 调用模型 → 抽取答案 → 打分 → 统计 → 归档"，并补上工程上必需的并发、重试、缓存、可复现记录和诊断能力。

| 阶段 | 内容 | 主要代码 |
|---|---|---|
| 1. 跑通单个评测集 | GSM8K：从 HuggingFace 加载、调用模型、抽取数字、计算准确率、逐题写 JSONL | `tasks/gsm8k.py`、`core/scorer.py` |
| 2. 抽象和配置化 | 拆出 `Sample`、`Model`、`Solver`、`Scorer`、`Task`、`Runner` 六个概念；任务注册表；YAML 配置；接入第二个评测集 MMLU 验证抽象 | `core/types.py`、`core/task.py`、`core/config.py`、`tasks/mmlu.py` |
| 3. 工程健壮性 | asyncio 并发上限；只对可重试错误（限流、超时、连接错误、5xx）做指数退避重试；单题超时；单题失败不影响整体；按请求内容哈希的磁盘缓存，可中断续跑 | `core/runner.py`、`core/retry.py`、`core/cache.py` |
| 4. 可复现与诊断 | 每次运行生成 `manifest.json`；每题归为五类 outcome；统计答案抽取方式；bootstrap 置信区间；离线重打分 `rescore`；两次运行对比 `diff` | `core/manifest.py`、`analysis/` |

## 关键设计

- **生成和打分分离**：模型原始输出全部落盘，改了抽取规则后 `harness rescore` 不用重新调用模型。
- **Solver 拿到的是包装好的 `generate`**：缓存、重试、超时都在 runner 里，Solver 只关心怎么提问。这为后面多步调用模型的 Agent 循环留好了接口。
- **数据集固定版本**：GSM8K、MMLU 都锁定了 HuggingFace 的 commit SHA。
- **指纹**：Solver（prompt 模板、few-shot 设置）和 Scorer（抽取规则）都会生成指纹写进 manifest，配置有任何变化 `diff` 都能看出来。
- **不只是对和错**：每道题归为 `correct`、`wrong`、`extract_failed`（格式问题）、`truncated`（被 max_tokens 截断）、`api_error`（调用失败，计入分母）。

## 怎么用

```bash
uv sync
uv run harness run -c configs/ollama-smoke.yaml          # 本地 Ollama，不需要 key
uv run harness run -m dashscope/qwen-plus -t gsm8k -t mmlu --limit 50
uv run harness show runs/<run_id> -t gsm8k --outcome truncated -n 3
uv run harness rescore runs/<run_id>
uv run harness diff runs/<a> runs/<b>
```

## 验证

- 47 个离线单元测试，覆盖答案抽取、outcome 分类、重试与超时、并发上限、缓存续跑、manifest、rescore 和 diff。
- GitHub Actions CI：ruff 检查 + pytest。
- 用 Ollama 上的 `qwen2.5:0.5b-instruct`（CPU）做了真实运行：

| task | n | accuracy | 95% CI | correct | wrong | extract_failed | truncated |
|---|---|---|---|---|---|---|---|
| gsm8k | 20 | 0.450 | [0.25, 0.65] | 9 | 9 | 0 | 2 |
| mmlu | 40 | 0.425 | [0.275, 0.575] | 17 | 22 | 0 | 1 |

## 实测中发现的现象

- **格式不遵守**：prompt 要求以 "The answer is N" 结尾，GSM8K 有 18/20 的回答却用了 `\boxed{}`。如果只认要求的格式，这些都会被误判。
- **小样本置信区间很宽**：20 道题的 95% 置信区间跨了 40 个百分点。
- **指标抖动**：temperature 改为 0.8 重跑，总分仍是 0.450，但 `diff` 显示 2 题由对变错、2 题由错变对，20 个输出全部不同。
- **缓存续跑**：相同配置第二次运行全部命中缓存，耗时从约 70 秒降到约 3 秒。

## 遗留和限制

- 只支持兼容 OpenAI 接口的模型。
- 结果存在本地文件，没有数据库和 Web 页面。
- 运行是单机 asyncio 并发，还没有分布式调度。
