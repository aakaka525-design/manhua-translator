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
