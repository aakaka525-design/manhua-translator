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
- 进程级指标已补齐到 QualityReport（见 `process.*`、`queue_wait_ms` 与 `run_config`）；后续复审应直接从 report 取证（不要依赖外部笔记）

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

Recommended runtime knobs (deploy; config-only):
- `OCR_TILE_OVERLAP_RATIO=0.25` (W3: OCR ~44.8s -> ~31.1s; raw regions stable at 84)
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1` (opt-in; reduces zh fallback remote-call tail)
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000` (Gemini + fallback chain only; reduces timeout->fallback stacking)

QualityReport explainability additions (commit `44449b9`):
- `run_config`: sanitized env whitelist (no secrets)
- `process`: `cpu_user_s`, `cpu_system_s`, `max_rss_mb`
- `queue_wait_ms`: measured at pipeline start (useful for API/chapter workloads)

### 6.2 M3 Gates (W3)
M3 gate definition is in `docs/perf_audit/2026-02-08/08_m3_plan.md` and uses W3 as the primary workload.

Baseline (M2, W3):
- OCR: 48.0s
- Translator: 101.0s
- OCR raw regions: 84

Measured (M3, W3; sample runs on 2026-02-08):
- OCR with `OCR_TILE_OVERLAP_RATIO=0.25`: ~31.1s (stable)
- Translator stage: large variance across runs; variance looks dominated by remote-call tail latency / fallback stacking rather than local compute.
- Explainability gap (Translator stage vs internal `total_translate_ms`): <= 1.43% (across sampled runs)

W3 A/B (same page; `OCR_TILE_OVERLAP_RATIO=0.25` + `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`):
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=12000`:
  - total=169.3s; translator=120.1s; requests_primary=7 / fallback=9; zh_retranslate_ms=43.8s
  - AI log: primary timeout=6; fallback_provider=6; mixed-language heuristic `no_cjk_with_ascii=9`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`:
  - total=132.3s; translator=83.8s; requests_primary=8 / fallback=5; zh_retranslate_ms=4.0s
  - AI log: primary timeout=2; fallback_provider=2; mixed-language heuristic `no_cjk_with_ascii=4`

Verdict:
- OCR gate (<=36s): PASS
- Explainability gate (<=10%): PASS
- Translator gate (<=70s): NOT CONSISTENTLY MET
  - Notes: variance looks dominated by remote-call tail latency / fallback stacking rather than local compute. Needs more sampling (especially W2 chapter concurrency) and/or tighter provider-side call strategy to reduce p95.

### 6.3 Quality Guardrails (M3 sampling)
- OCR raw regions: PASS (W3 raw regions remained 84; see `translator.log` “开始翻译 84 个区域”)
- Mixed-language regression heuristic:
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=12000`: `no_cjk_with_ascii=9`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`: `no_cjk_with_ascii=4` (improved; aligns with fewer timeouts/fallbacks)
  - Both A/B runs have `"[翻译失败]"=0` in quality report JSON.
- Inpaint/repair: NOT RE-VALIDATED IN M3 (no code changes in inpaint/renderer, but still requires 3-region manual spot-check on output images)

### 6.4 W2 Tail Sampling (chapter-68 pages 7+9, `-w 2`, timeout=15000)
Context:
- Workload: `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/7.jpg` + `9.jpg` (tail pages only)
- Fixed knobs: `UPSCALE_ENABLE=0`, `OCR_RESULT_CACHE_ENABLE=0`, `OCR_TILE_OVERLAP_RATIO=0.25`, `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- Evidence:
  - Reports: `/tmp/quality_reports_m3_w2tail_t15_20260208_161650/*.json`
  - `MANHUA_LOG_DIR=/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.OfkmC0GfFL`

Results (from reports + AI log counters):
- AI log (global for this run): `primary timeout after 15000ms=3`, `fallback provider=3`, `missing number|missing items lines=29`.
- Per-page (quality report; merged regions):
  - Page 7: total=99.5s; translator=64.5s; regions=33; `"[翻译失败]"=0`; `no_cjk_with_ascii=2`; `hangul_left=0`.
  - Page 9: total=173.1s; translator=104.0s; regions=58; `"[翻译失败]"=0`; `no_cjk_with_ascii=0`; `hangul_left=0`.

Conclusion:
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000` 在章节并发 tail 页下仍有少量 timeout，但未引入翻译失败/韩文残留，且 mixed-language 指标可接受。
- 该结果支持将 15000ms 作为 Gemini + fallback chain 的部署侧推荐配置；W2 全量 9 页采样已补齐（见 6.6），但 p95 仍被尾页（page 9）远端调用尾延迟主导。

### 6.6 W2 Full Chapter Sampling (chapter-68, 9 pages, `-w 2`, timeout=15000)
Context:
- Workload: `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/` (9 pages)
- Fixed knobs: `UPSCALE_ENABLE=0`, `OCR_RESULT_CACHE_ENABLE=0`, `OCR_TILE_OVERLAP_RATIO=0.25`, `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- Evidence:
  - Reports: `output/quality_reports_m3_w2full_t15/*.json`
  - `MANHUA_LOG_DIR=/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.yIOpbiWXDs`

Results (nearest-rank p50/p95; N=9 so p95==max):
- total: p50=70.7s; p95=188.3s
- ocr: p50=15.7s; p95=33.8s
- translator: p50=40.3s; p95=133.6s
- process peak (from reports): `max_rss_mb` ~= 5263.7

Quality:
- All pages: `"[翻译失败]"=0`, `hangul_left=0`
- `no_cjk_with_ascii` exists but low (likely short labels/tags); no systemic mixed-language regression observed
- Some pages have `empty_target` (page 9 has 12); requires output spot-check if this becomes frequent

AI log counters (global for this run):
- `primary timeout after 15000ms=7`
- `fallback provider=14`
- `missing number|missing items lines=65`

Conclusion:
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000` 在 W2 全量章节并发（`-w 2`）下仍能维持质量门槛（无失败标记/韩文残留）。
- 尾延迟仍主要由远端调用与回退链决定；下一步证据需要来自云端更高并发多章节压测与崩溃模式（OOMKilled vs exception）确认。

### 6.5 Cloud Stress Sampling (3 concurrent chapters, 42 pages, UPSCALE=0)
Context:
- Workload: 3 chapters in parallel (total 42 pages), each ran `python main.py chapter ... -w 2` inside docker.
- Fixed knobs: `UPSCALE_ENABLE=0`, `OCR_RESULT_CACHE_ENABLE=0`, `OCR_TILE_OVERLAP_RATIO=0.25`, `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- Evidence (server lists):
  - Before fix: `output/quality_reports/_stress_20260208_134907.list`
  - After fix: `output/quality_reports/_stress_20260208_142518_s2_afterfix.list`

Gates:
- `"[翻译失败]"` in quality reports: must stay 0 (PASS)
- `pages_has_hangul` / `regions_with_hangul`: must be 0 for zh output (PASS after fix)

Results (nearest-rank p50/p95; parsed from quality reports):
- Before fix:
  - `pages_total=42`, `pages_has_fail_marker=0`
  - `pages_has_hangul=2`, `regions_with_hangul=2`
  - timings (ms): `translator_p95=66908`, `translator_max=85902`, `total_p95=74367`
- After fix:
  - `pages_total=42`, `pages_has_fail_marker=0`
  - `pages_has_hangul=0`, `regions_with_hangul=0`
  - timings (ms): `translator_p95=29367`, `translator_max=77959`, `total_p95=66471`

Verdict:
- Quality: PASS (no failure markers; Hangul leakage removed)
- Performance: PASS for this sampling (translator long-tail improved); still need larger-scope sampling to claim p95 improvement is stable across titles.

### 6.7 Cloud Stress S3b (API, 4 concurrent chapters, 43 pages, UPSCALE=0; post `4e6263a`)
Context:
- Server: `185.218.204.62`
- Trigger: API `POST /api/v1/translate/chapter` (4 chapters started concurrently)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260208_190604_api_s3b`
- Evidence:
  - Report list: `output/quality_reports/_stress_20260208_190604_api_s3b.list`
  - Docker: `manhua-translator-api-1` healthy; `OOMKilled=false`, `RestartCount=0`
  - Kernel OOM grep: `/tmp/kernel_oom_s3b_20260208_190604.txt` (`0` lines)

Gates:
- `pages_has_hangul` / `regions_with_hangul`: must be 0 for zh output (PASS)
- `"[翻译失败]"` in quality reports: must stay 0 (NOT PASS in this sampling)

Results (nearest-rank p50/p95; parsed from quality reports):
- `pages_total=43`
- quality:
  - `pages_has_hangul=0`, `regions_with_hangul=0`
  - `pages_has_fail_marker=1`, `regions_with_fail_marker=7`
  - `no_cjk_with_ascii=23`, `empty_target_regions=52`
- timings (ms):
  - `translator_p50=14277`, `translator_p95=53667`, `translator_max=97212`
  - `total_p95=72163`, `total_max=121280`
- process peak (from reports):
  - `max_rss_max_mb=4376.7`
- failure file (all regions failed):
  - `taming-a-female-bully__chapter-57-raw__12__8d767d9a-dbcb-410a-a621-58f9512b8f9f.json`

Verdict:
- Stability: PASS at this concurrency (no restarts/OOM observed)
- Quality: NOT PASS (provider overload/timeout can still yield `[翻译失败]` under multi-chapter load; requires backpressure/concurrency cap to drive fail marker back to 0)

### 6.8 Cloud Stress S6 (API, 6 concurrent chapters, 108 pages, UPSCALE=0)
Context:
- Server: `185.218.204.62`
- Trigger: API `POST /api/v1/translate/chapter` (6 chapters started concurrently)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260208_192710_api_s6`
- Evidence:
  - Report list: `output/quality_reports/_stress_20260208_192710_api_s6.list`
  - Docker: api container healthy; `OOMKilled=false`, `RestartCount=0`
  - Kernel OOM grep: `/tmp/kernel_oom_s6_20260208_192710.txt` (`0` lines)

Results (nearest-rank p50/p95; parsed from quality reports):
- `pages_total=108`
- quality:
  - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
  - `pages_has_fail_marker=4`, `regions_with_fail_marker=18` (NOT PASS)
- timings (ms):
  - `translator_p50=11313`, `translator_p95=38087`, `translator_max=54892`
  - `total_p95=66145`, `total_max=82515`
- process peak (from reports):
  - `max_rss_max_mb=5666.1`

Verdict:
- Stability: PASS (no restarts/OOM observed)
- Quality: NOT PASS under this load (failure markers increased vs S3b)

### 6.9 Cloud Stress S9 (API, 9 concurrent chapters, 211 pages, UPSCALE=0)
Context:
- Server: `185.218.204.62`
- Trigger: API `POST /api/v1/translate/chapter` (9 chapters started concurrently)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260208_193832_api_s9`
- Evidence:
  - Report list: `output/quality_reports/_stress_20260208_193832_api_s9.list`
  - Docker: api container healthy; `OOMKilled=false`, `RestartCount=0`
  - Kernel OOM grep: `/tmp/kernel_oom_s9_20260208_193832.txt` (`0` lines)

Results (nearest-rank p50/p95; parsed from quality reports):
- `pages_total=211`
- quality:
  - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
  - `pages_has_fail_marker=6`, `regions_with_fail_marker=16` (NOT PASS)
- timings (ms):
  - `translator_p50=11839`, `translator_p95=42156`, `translator_max=73991`
  - `total_p95=72736`, `total_max=110472`
- process peak (from reports):
  - `max_rss_max_mb=5749.6`

Verdict:
- Stability: PASS with `UPSCALE_ENABLE=0` (no crash reproduced up to 9 concurrent chapters)
- Quality: NOT PASS (failure markers remain under high concurrency; requires backpressure to keep `"[翻译失败]"` at 0)
