# 00 Baseline

- 生成日期: 2026-02-08
- 样本来源: `output/quality_reports`（有效报告 12）
- 说明: 当前日志无 CPU/内存峰值字段，本轮先完成 OCR/translator 分段基线，资源峰值列为待补采。

## Workload 定义

- W1: single-page translation (small pages); sampled from chapter-71-raw reports
- W2: chapter translation (fixed pages): wireless-onahole/chapter-68/*
- W3: high-text-density pages: top-3 by region count and translator time

## 指标概览（ms）

| Workload | 样本数 | E2E p50 | E2E p95 | OCR p50 | Translator p50 | 估算翻译请求均值 | 重试建议均值 |
|---|---:|---:|---:|---:|---:|---:|---:|
| W1 | 2 | 30683.97 | 36336.27 | 2615.44 | 10486.61 | 3.50 | 0.00 |
| W2 | 9 | 127212.17 | 160055.35 | 37313.03 | 33778.50 | 27.44 | 0.00 |
| W3 | 3 | 140318.51 | 150172.34 | 54250.37 | 54962.78 | 40.33 | 0.00 |

## 初步结论

- W2/W3 中 OCR 与 translator 共同主导总耗时；OCR 抖动和 translator 尾延迟同时存在。
- translator 在高文本页存在显著长尾，符合大批次请求 + 回退链路叠加开销。
- 需在后续整改补齐 CPU/内存峰值采集（psutil）完成资源瓶颈闭环。

## M3 Targeted Benchmarks (UPSCALE_ENABLE=0)

本节记录 M3 在固定输入集上的实测结果，口径与上面的“统计基线”不同：
- M3 仅用于验证特定旋钮与改动的方向性，以及将 Translator wall-time 变得可解释。
- 所有命令均强制 `UPSCALE_ENABLE=0`、`OCR_RESULT_CACHE_ENABLE=0`，避免超分与 OCR 缓存影响。

证据来源：
- 质量报告：`output/quality_reports_m3/*.json`
- 翻译阶段日志：`logs/translator/20260208/translator.log`（包含 raw_regions、translated_done、translator_internal_ms）

### W3 (Single Long Page)

- Image: `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg` (720x19152)
- OCR raw regions (pre-merge): 84（见 `translator.log` 的 “开始翻译 84 个区域”）
- 注意：Translator 会先做 merge（`merge_line_regions`），因此质量报告中的 `regions` 数（58/59）是 merge 后的数量。

对比（同一天多次运行；存在远端波动/长尾，表内如实记录）：

| Label | AI_TRANSLATE_ZH_FALLBACK_BATCH | OCR_TILE_OVERLAP_RATIO | total_ms | ocr_ms | translator_stage_ms | translator_internal_ms | gap_pct | report |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A1 | 0 | 0.50 | 123264.29 | 44746.41 | 63176.60 | 62272 | 1.43 | `wireless-onahole__chapter-68__9__c708a11e-b8b8-48e4-9cd5-42a049cc1598.json` |
| A2 | 0 | 0.50 | 203465.72 | 44904.60 | 143175.89 | 142349 | 0.58 | `wireless-onahole__chapter-68__9__90240554-72cb-4070-a502-d7627247c778.json` |
| B1 | 1 | 0.25 | 134515.78 | 31405.14 | 88764.54 | 87936 | 0.93 | `wireless-onahole__chapter-68__9__e0aed731-7874-479c-8184-901903555a7a.json` |
| B2 | 1 | 0.25 | 119098.35 | 31089.75 | 73614.15 | 72787 | 1.12 | `wireless-onahole__chapter-68__9__4e2e3452-7389-4c97-8068-171a1d132009.json` |
| C1 (safe) | 0 | 0.25 | 133075.09 | 31343.50 | 87481.19 | 86655 | 0.94 | `wireless-onahole__chapter-68__9__6a090d5f-bb18-41a0-ad9f-9402cb301b16.json` |

关键结论：
- OCR：`OCR_TILE_OVERLAP_RATIO=0.25` 将 W3 OCR 阶段从 ~44.8s 降到 ~31.1s，且 raw regions=84 不变（满足质量底线）。
- Explainability：Translator stage wall-time 与内部 `total_translate_ms` 的差距 < 1.5%（达到 M3 “<=10%” 门槛）。
- Translator：同配置下仍存在大幅长尾（A2），更像远端调用波动/限流/回退叠加，而不是本地 CPU 性能瓶颈。

### W2 (Chapter, `-w 2`)

固定页集：`/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/`（9 页）。

说明：
- 单页 `total_ms` 不可直接相加得出章节 wall-time（因为 `-w 2` 并行处理）；表格用于观察“尾页/尾延迟”来源。
- 本次章节 runs 的每页质量报告文件为：`wireless-onahole__chapter-68__{1..8}__*.json` + page9 `wireless-onahole__chapter-68__9__6a090d5f-*.json`。

| Page | total_ms | ocr_ms | translator_stage_ms | report |
|---:|---:|---:|---:|---|
| 1 | 98381.19 | 19762.15 | 69688.25 | `wireless-onahole__chapter-68__1__50ccdef4-c4a8-4234-a4ba-4dedbb187d98.json` |
| 2 | 72392.01 | 32648.64 | 30995.72 | `wireless-onahole__chapter-68__2__783a63dd-5577-4f42-af32-105c1c315120.json` |
| 3 | 65619.24 | 14948.36 | 39676.08 | `wireless-onahole__chapter-68__3__4543ceb9-2659-47e7-864b-75c88df2dfe8.json` |
| 4 | 65621.96 | 14077.92 | 42281.58 | `wireless-onahole__chapter-68__4__9854e685-d909-4554-b940-0d85cd5f7f8c.json` |
| 5 | 59390.36 | 15572.56 | 31749.88 | `wireless-onahole__chapter-68__5__7ba7e746-7417-49dc-aa33-86dff2ec0b0f.json` |
| 6 | 66476.74 | 14208.14 | 42382.42 | `wireless-onahole__chapter-68__6__b7c94e49-a7de-4154-9130-e0af5425563b.json` |
| 7 | 132200.69 | 18136.94 | 99890.27 | `wireless-onahole__chapter-68__7__d075436d-85cb-46b4-8cf7-c8379ad65fc7.json` |
| 8 | 54765.80 | 12157.19 | 33614.00 | `wireless-onahole__chapter-68__8__c9b0dfb9-7ac7-42cf-a744-32ad5d208040.json` |
| 9 | 133075.09 | 31343.50 | 87481.19 | `wireless-onahole__chapter-68__9__6a090d5f-bb18-41a0-ad9f-9402cb301b16.json` |

### W1 (Single Short Page)

- Image: `/Users/xa/Desktop/projiect/manhua/data/raw/sexy-woman/chapter-1/15.jpg`
- Report: `sexy-woman__chapter-1__15__39249e5d-dc7a-4172-9838-86af55c554eb.json`
- Timings: total=86342.96ms, ocr=17226.63ms, translator=59582.24ms
