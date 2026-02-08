# 05 Acceptance Criteria

- 生成日期: 2026-02-08
- 基线引用: `docs/perf_audit/2026-02-08/baseline_metrics.json`
- 本轮目标: OCR、translator 优先，保证无功能回归

## 1. 验收工作负载

- S1 / W1: 单页翻译（小页样本，尽量关闭超分）
- S2 / W2: 整章翻译（固定页集：`wireless-onahole/chapter-68/*`）
- S3 / W3: 高文本密度页面（按区域数 top 页）
- S4: 前端 SSE 高频事件（章节并发翻译时）

## 2. 量化目标（优化后对比优化前）

### 2.1 端到端耗时
- W1: `total_ms_p50` 下降 >= 15%，`total_ms_p95` 下降 >= 20%
- W2: `total_ms_p50` 下降 >= 20%，`total_ms_p95` 下降 >= 25%
- W3: `total_ms_p50` 下降 >= 20%，`total_ms_p95` 下降 >= 30%

### 2.2 阶段耗时
- OCR: W2/W3 的 `ocr` p50 下降 >= 20%，p95 下降 >= 25%
- Translator: W2/W3 的 `translator` p50 下降 >= 25%，p95 下降 >= 30%
- API 调度: 章节任务排队等待 p95 下降 >= 20%

### 2.3 稳定性与质量
- 失败率: 不高于基线（允许波动 <= 1 个百分点）
- 重试率: `retry_count_est_avg` 下降 >= 20%
- 翻译质量: 不允许出现系统性漏译/错序回归（抽样人工复核）

### 2.4 前端体验
- SSE 高频时无明显卡顿，进度展示持续可读
- `chapter_complete` / `failed` 事件不可丢失

## 3. 数据采集要求

- 每次优化提交必须附同口径前后对比：
  - `baseline_metrics.json`（前/后）
  - 关键任务日志片段（task_id 级）
  - 质量报告样本（至少 3 页）
- 需补齐进程级指标（CPU%、RSS、队列等待）后再做第二轮复审

## 4. 通过/不通过判定

- 通过: 满足 2.1 + 2.2 + 2.3 的全部硬门槛
- 有条件通过: 达成耗时目标但失败率上升 <=1pp，需附后续修复计划
- 不通过: 任一核心门槛不达标，或出现明显功能回归

## 5. 回归检查清单

- 翻译失败接口状态码与错误信息语义一致
- 前端关闭超分后不应触发超分阶段
- 长图切片输出索引与切片顺序一致
- OCR 空结果与 fallback 路径行为符合预期

## 6. M3 Checkpoint (2026-02-08, OCR + Translator)

### 6.1 Setup (strict)
- `UPSCALE_ENABLE=0`
- `OCR_RESULT_CACHE_ENABLE=0`
- Reports: `output/quality_reports_m3/*.json`
- Translator log evidence: `logs/translator/20260208/translator.log`

### 6.2 M3 Gates (W3)
M3 gate definition is in `docs/perf_audit/2026-02-08/08_m3_plan.md` and uses W3 as the primary workload.

Baseline (M2, W3):
- OCR: 48.0s
- Translator: 101.0s
- OCR raw regions: 84

Measured (M3, W3; sample runs on 2026-02-08):
- OCR with `OCR_TILE_OVERLAP_RATIO=0.25`: ~31.1s (stable)
- Translator stage: 63.2s .. 143.2s (large variance across runs)
- Explainability gap (Translator stage vs internal `total_translate_ms`): <= 1.43% (across sampled runs)

Verdict:
- OCR gate (<=36s): PASS
- Explainability gate (<=10%): PASS
- Translator gate (<=70s): NOT CONSISTENTLY MET
  - Notes: variance looks dominated by remote-call tail latency / fallback stacking rather than local compute. Needs more sampling and/or tighter provider-side call strategy to reduce p95.

### 6.3 Quality Guardrails (M3 sampling)
- OCR raw regions: PASS (W3 raw regions remained 84; see `translator.log` “开始翻译 84 个区域”)
- Mixed-language regression heuristic: PASS (W3: `no_cjk_with_ascii=4` for multiple runs; stable across runs)
- Inpaint/repair: NOT RE-VALIDATED IN M3 (no code changes in inpaint/renderer, but still requires 3-region manual spot-check on output images)
