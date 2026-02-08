# 07 M2 Plan (OCR/Translator Single-Task Latency)

- 生成日期: 2026-02-08
- 工作分支: `codex/perf-m1-ocr-translator` (worktree: `.worktrees/perf-m1-ocr-translator`)
- 范围: 只优化 OCR + Translator 的单任务耗时与尾延迟，不以“吞吐最大化”为第一目标。
- 质量底线: 不允许 OCR 识别率/准确度、译文语义/语境、擦除修复质量出现系统性回退。

## 0. 现有基线摘要（来自 Phase A）

> 注意：当前 `baseline_metrics.json` 的 `total_ms` 包含 `upscaler`。M2 重新采样会强制关闭超分或在统计上排除 upscaler，以免噪声掩盖 OCR/Translator。

来自 `docs/perf_audit/2026-02-08/baseline_metrics.json`：

- W2（章节页，regions_avg≈29.6）
  - OCR: p50≈37s, p95≈79s
  - Translator: p50≈33.8s, p95≈69.3s
- W3（高文本页，regions_avg≈43.7）
  - OCR: p50≈54.3s, p95≈55.9s
  - Translator: p50≈55.0s, p95≈76.4s

## 1. M2 的核心假设（待验证）

- OCR 长尾主要来自：长图 tiling 的 tile_count 过多 (当前默认 `tile_height=1024`, `overlap_ratio=0.5`)，耗时近似线性随 tile_count 增长。
- Translator 长尾主要来自：prompt/token 膨胀与大批次单次调用导致的 p95 放大，以及失败路径的重复远端调用。

## 2. 执行顺序（每一步都要写入 worklog）

### 2.1 基线重采样（剥离 upscaler）
- 固定 W1/W2/W3 输入集与并发
- 强制关闭超分（`UPSCALE_ENABLE=0` 或统计排除）
- 输出一份新基线:
  - `baseline_metrics_m2.json`
- Worklog 记录：
  - 输入集、环境变量、关键 task_id、以及 OCR/Translator 分段耗时 (p50/p95)

### 2.2 OCR 提速（默认行为不变，A/B 开关实验）
优先级从“降 tile_count”开始：

1. Tiling 参数可配置（不改默认值）
   - 文件: `core/vision/tiling.py`
   - Env:
     - `OCR_TILE_HEIGHT` (default: 1024)
     - `OCR_TILE_OVERLAP_RATIO` (default: 0.5)
     - `OCR_TILE_MIN_HEIGHT` (default: 256)
     - `OCR_EDGE_PADDING` (default: 64)
     - `OCR_EDGE_BAND_RATIO` (default: 0.15)
     - `OCR_EDGE_BAND_MIN_HEIGHT` (default: 128)
2. 小图 1.5x 二次 OCR 改为条件触发（默认保持 always）
   - 文件: `core/vision/ocr/paddle_engine.py`
   - Env:
     - `OCR_SMALL_IMAGE_SCALE_MODE` = `always|auto|off` (default: `always`)
     - `OCR_SMALL_IMAGE_SCALE_FACTOR` (default: 1.5)
     - `OCR_SMALL_IMAGE_SCALE_MIN_REGIONS` (default: 4, only for `auto`)
     - `OCR_SMALL_IMAGE_SCALE_MIN_CONF` (default: 0.60, only for `auto`)
3. Edge tiles 增加 auto 模式（默认 off）
   - 文件: `core/vision/ocr/paddle_engine.py`
   - Env:
     - `OCR_EDGE_TILE_MODE` = `off|on|auto` (default: `off`)
     - `OCR_EDGE_TILE_TOUCH_PX` (default: 8, only for `auto`)

验收（每条改动独立验收）：
- W3: `ocr` p50 下降 >= 20%
- OCR 结果质量：regions 数、低置信区域分布、抽样人工复核不回退

### 2.3 Translator 提速（压 p95 长尾）
1. 度量补齐（prompt/context 大小可解释）
   - 文件: `core/ai_translator.py`, `core/modules/translator.py`
   - 指标:
     - `prompt_chars_total`, `content_chars_total`, `ctx_chars_total`, `text_chars_total`
2. Context 裁剪（默认关闭，保守 A/B）
   - 文件: `core/modules/translator.py`
   - Env:
     - `AI_TRANSLATE_CONTEXT_CHAR_CAP` (default: 0 disabled)
3. 批处理切片策略（优先“预算切片+小并发”，保留小样本单批）
   - 文件: `core/ai_translator.py`
   - Env:
     - `AI_TRANSLATE_BATCH_CHAR_BUDGET` (default: 0 disabled)

验收：
- W3: `translator` p95 下降 >= 30%
- 失败率不升高，译文语义/语境不出现系统性回退

## 3. 风险与疑问（必须跟踪到关闭）

- PaddleOCR 并发风险：本轮不默认开启 tile 并行，仅通过“降 tile_count”先拿收益；若后续要并行，需要压测验证稳定性。
- Context 裁剪可能引入语境丢失：默认关闭，仅 A/B 验证后再决定是否推广。

## 4. 本轮 DoD（完成定义）

- 产物：
  - `baseline_metrics_m2.json`（含 OCR/Translator 的可解释指标）
  - `06_worklog.md` 全程记录每个关键点的完成状态与未解问题
- 指标：
  - 至少在 W2 或 W3 上完成一次可复现的 OCR/Translator 降耗时对比（同输入、同口径）

