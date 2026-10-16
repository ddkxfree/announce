# 路线图与设计背景

## 项目目标

这是一个用来学习和展示"大模型评测平台"工程能力的项目，对标的是"大模型评测研发工程师"岗位的要求：

- 评测平台架构：数据集管理、环境隔离、任务调度、指标计算、结果归档与可视化
- 评测集适配：SWE-bench、Terminal-Bench 等主流评测集的平台化接入，Benchmark 版本管理，结果可追踪、可对比、可复现
- Harness Engineering：把评测任务本身 Agent 化，自动接入评测集；自动诊断适配异常、指标抖动、环境漂移
- 前沿评测范式：LLM-as-Judge、多智能体评判、人类偏好对齐

核心定位：**我们做的是"考试中心"，不是"考生"。** mini-swe-agent、SWE-agent、OpenHands 这类 Agent 是被评测的对象，应当作为 `Solver` 插件接入；SWE-bench、Terminal-Bench 等评测集作为 `Task` 接入。不要重新实现这些 Agent。

## 设计原则

1. **生成和打分分离**。模型原始输出全部落盘到 `samples.jsonl`，改抽取或打分逻辑后用 `harness rescore` 离线重打分。
2. **Solver 拿到的是包装好的 `generate`**（已带缓存、重试、超时）。多步 Agent 循环直接多次调用它即可，不需要关心这些工程细节。
3. **可复现**：数据集固定 revision；solver/scorer 通过 `describe()` 产生指纹写入 manifest；manifest 还记录 git commit、依赖版本、`uv.lock` 哈希。
4. **诊断优先**：每道题归为 `correct / wrong / extract_failed / truncated / api_error`，并记录抽取方式；报告 bootstrap 置信区间。
5. **加新评测集不改 core**。如果做不到，说明抽象需要调整，先调整抽象。

## 当前状态：阶段 1～4 已完成

- GSM8K、MMLU 两个评测集，支持 few-shot、确定性抽样、MMLU 学科过滤
- 兼容 OpenAI 接口的模型接入（openai、dashscope、deepseek、ollama、vllm）
- 并发上限、可重试错误的指数退避、单题超时、单题失败隔离
- 按请求内容哈希的磁盘缓存，可中断续跑
- `manifest.json`、`samples.jsonl`、`summary.json` 运行产物
- CLI：`run`、`show`、`rescore`、`diff`、`list-tasks`
- 47 个离线单元测试，GitHub Actions CI

用 Ollama 上的 qwen2.5:0.5b-instruct 实测时观察到：GSM8K 20 题中 18 题用 `\boxed{}` 而非要求的 "The answer is N"；temperature 0.8 重跑时总分不变但有 4 道题对错翻转。这些都是诊断功能的实际用例。

## 下一步

### 阶段 5：Agent 评测与 Docker 沙箱

目标：平台能评测"模型 + Agent 框架"在需要执行环境的任务上的表现。

1. `core/sandbox.py`：`Sandbox` 抽象（`exec(cmd) -> (exit_code, stdout, stderr)`、`write_file`、`read_file`、`close`），先实现基于 Python `docker` SDK 的 `DockerSandbox`。每个样本一个容器，任务结束必须清理。
2. Runner 支持按样本创建和销毁沙箱，并把沙箱传给 solver 和 scorer。沙箱创建失败归类为新的 outcome `env_error`，与模型能力问题区分开。
3. `solvers/basic_agent.py`：最简单的工具调用循环（一个 `bash` 工具，步数上限、token 上限），作为基线 Solver。它只用来验证链路，不追求效果。
4. 轨迹记录：每一步的模型输出、工具调用、工具返回、耗时、token 写入 `samples.jsonl`。
5. 自建 3 个 Terminal-Bench 风格的小任务（任务描述 + Dockerfile + 验证脚本），跑通后再接入真实评测集。
6. 接入 SWE-bench Lite / Verified 的少量样本：复用官方 Docker 镜像和单测验证逻辑，包装为 Task 和 Scorer。
7. 把 mini-swe-agent 包装为 Solver 插件，和基线 Solver 在同一批题上对比。
8. 接入 Terminal-Bench（或通过 Harbor 的任务格式），验证不改 core 就能容纳第二种 Agent 评测集。

验收：同一个模型分别配基线 Solver 和 mini-swe-agent，在自建任务和 SWE-bench 小样本上都能跑出结果；`harness show` 能看到完整轨迹；沙箱不泄漏容器。

### 阶段 6：LLM-as-Judge

1. `JudgeScorer`：单点打分（rubric）和两两对比两种模式；裁判模型通过同样的 `get_model` 配置。
2. 两两对比时交换 A/B 顺序各评一次，不一致记为平局，并统计位置偏差率。
3. 多裁判投票。
4. 接入 MT-Bench 或 Arena-Hard 的少量样本作为验证。
5. 用一小批人工标注（或 lmarena 公开的人类偏好数据）计算裁判与人类的一致率。

注意：裁判调用也要走缓存和 manifest，裁判模型和裁判 prompt 的变化必须体现在 scorer 指纹里。

### 阶段 7：统计与诊断

1. 同一配置跑 N 次（`--epochs`），缓存键加入 epoch，报告均值、标准差和置信区间。
2. 两个模型的配对比较与显著性检验（同一批题）。
3. `harness diff` 增加"可能原因"提示：配置变化、环境变化、输出完全相同但打分变化（说明是 scorer 改动）等。
4. 错误归类报告：自动抽样各类失败样本，生成 Markdown 报告。

### 阶段 8：评测集接入 Agent 化

用一个 Agent 自动接入新评测集：读取数据集说明和样例，按 `tasks/` 的约定生成 Task 文件，用已知模型试跑并与论文或排行榜分数对比，分数对不上时查看失败样本、修改并重跑。

### 之后

- 分布式执行（Ray 或 K8s Job），结果存储换成数据库，简单的 Web 结果页
- 多模态评测（参考 VLMEvalKit、lmms-eval）
- 工具调用与多轮对话评测（BFCL、τ²-bench）
