# ESG 定性 RAG 方法（无 Reranker）

面向 ESG 定性指标证据召回的可复现流水线。当前冻结版本使用：

```text
PDF 结构化自然段语料
  ├─ BM25 Top150
  └─ Qwen3.7 Dense Top150
          ↓
本地特征融合（语义、词法、通道排名、指标 facet）
          ↓
BM25 / Dense / facet 通道保护
          ↓
Top50 证据候选
```

本版本**不使用 reranker 模型，也不进行 LLM 评分**。仓库同时提供完整实验数据、人工 Ground Truth、embedding 缓存、1,060 个检索任务的逐任务结果和汇总指标。

## 已验证结果

实验规模为 20 份 ESG 报告 × 53 个定性指标：

| Top-K | Evidence Recall | Component Recall | 段落组件 Recall | 结构化组件 Recall | 至少命中一个任务 |
|---:|---:|---:|---:|---:|---:|
| 10 | 67.12% | 52.92% | 56.99% | 38.86% | 83.00% |
| 25 | 81.19% | 68.37% | 71.76% | 56.68% | 91.96% |
| 50 | **89.71%** | **78.99%** | **81.79%** | **69.31%** | **95.98%** |

- 有 GT 的任务：647 个
- 人工证据行：1,244 条
- 证据组件：1,799 个
- Top50 命中人工证据行：1,116 条

## 与 PDF 解析仓库的关系

本仓库不重复维护 PDF 解析代码。结构恢复、自然段切分、表格/结构化单元生成和 `retrieval_chunks.jsonl` 契约由独立项目维护：

- [`HKUBSAIRI/esg-qualitative-pdf-parser`](https://github.com/HKUBSAIRI/esg-qualitative-pdf-parser)

为保证实验可复现，本仓库只保留该解析器对 20 份评测报告生成的**冻结检索语料**，不包含解析器源码，也不包含原始 PDF。

## 仓库内容

```text
esg_qualitative_rag/                 检索、embedding、评测和 CLI
data/
  corpus/<document_id>/
    retrieval_chunks.jsonl          20 份冻结检索语料
  ground_truth/                     20 份人工 GT 与对齐审计文件
  metrics/metrics_53.json           53 指标定义、关键词和证据问题
results/no_reranker_20x53/
  results/                           1,060 个 PDF×指标 Top50 结果
  embedding_cache/                   冻结 Qwen3.7 embedding 缓存
  summary.json                       总体配置与汇总指标
  per_query.csv                      逐任务指标
  per_metric.csv                     逐指标指标
  EXPERIMENT_REPORT.md               实验报告
tests/                               无网络单元测试
```

## 快速核验已发布结果

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
esg-qualitative-rag verify-results
```

该命令不访问网络、不调用模型，只从人工 GT 和 1,060 个已发布结果重新计算 Recall。

## 重新运行完整流水线

仓库附带完整 embedding 缓存。对冻结的 20×53 数据重新运行时，缓存完整命中，不需要 reranker；如果输入或查询发生变化导致 cache miss，则需要 DashScope API Key：

```bash
cp .env.example .env
export DASHSCOPE_API_KEY="你的密钥"
esg-qualitative-rag run --output outputs/reproduction
```

只运行少量指标：

```bash
esg-qualitative-rag run \
  --metric-ids 1 2 3 \
  --output outputs/metrics-1-3
```

不要把 `.env` 或 API Key 提交到仓库。

## 核心打分公式

候选集合为 BM25 Top150 与 Dense Top150 的并集。各候选的本地综合分为：

```text
0.35 × normalized_dense
+ 0.20 × normalized_bm25
+ 0.20 × normalized_dense_rank
+ 0.10 × normalized_bm25_rank
+ 0.15 × facet_score
```

最终选择时保护 BM25 前 10、Dense 前 10，并为每个指标 facet 保护至少一个高分候选，再按综合分补齐 Top50。这样避免二次模型重排对长尾证据造成召回损失。

## 评测口径

- **Evidence Recall**：同一人工证据行映射出的多个 chunk ID 视为一组，命中任意一个即为召回。
- **Component Recall**：所有 GT chunk ID 分别计数，口径更严格。
- **任务命中率**：有 GT 的 PDF×指标任务中，至少召回一个 GT 组件的比例。
- GT 只参与最终评测，不参与查询生成后的候选排序，也不会写回检索结果。

更完整的实验解释见 [`results/no_reranker_20x53/EXPERIMENT_REPORT.md`](results/no_reranker_20x53/EXPERIMENT_REPORT.md)。

## 数据说明

仓库中的报告正文是公开 ESG 报告经结构化解析得到的派生语料；人工 GT 和实验结果用于研究复现。使用者仍需自行确认其具体使用场景下的版权、合规与再分发要求。

