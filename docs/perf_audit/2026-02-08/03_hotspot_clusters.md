# 03 Hotspot Clusters

- 生成日期: 2026-02-08
- 聚合文件数: 108

## OCR 链路

- 根因描述: 全局串行锁与 tile 串行处理叠加，长图 OCR 阶段易成为固定瓶颈。
- 涉及文件数: 10（高关键度 3）
- 优先级均分: 64.9
- 预估收益区间: OCR 阶段 20%~40%，E2E 15%~30%
- 涉及文件集合（Top 8）:
  - `core/modules/ocr.py`
  - `core/vision/ocr/paddle_engine.py`
  - `core/vision/tiling.py`
  - `core/vision/ocr/cache.py`
  - `core/vision/ocr/post_recognition.py`
  - `core/vision/ocr/preprocessing.py`
  - `core/ocr_postprocessor.py`
  - `core/vision/ocr/__init__.py`

## Translator 链路

- 根因描述: 大批次单请求、失败重试回退链和上下文拼装共同放大尾延迟。
- 涉及文件数: 8（高关键度 2）
- 优先级均分: 63.5
- 预估收益区间: Translator 阶段 20%~45%，E2E 10%~25%
- 涉及文件集合（Top 8）:
  - `core/ai_translator.py`
  - `core/modules/translator.py`
  - `core/crosspage_carryover.py`
  - `core/crosspage_pairing.py`
  - `core/crosspage_processor.py`
  - `core/quality_report.py`
  - `core/translator.py`
  - `core/crosspage_splitter.py`

## API/任务调度链路

- 根因描述: pipeline 串行阶段 + SSE 广播逐连接 await，限制章节任务吞吐。
- 涉及文件数: 16（高关键度 2）
- 优先级均分: 53.8
- 预估收益区间: 章节吞吐 15%~25%，前端进度延迟降低
- 涉及文件集合（Top 8）:
  - `core/pipeline.py`
  - `app/routes/translate.py`
  - `scraper/base.py`
  - `scraper/downloader.py`
  - `scraper/engine.py`
  - `scraper/fetch.py`
  - `scraper/implementations/mangaforfree.py`
  - `scraper/implementations/toongod.py`

## 前端状态与事件链路

- 根因描述: 高频 SSE 事件导致状态写入和组件重渲染频率偏高。
- 涉及文件数: 34（高关键度 1）
- 优先级均分: 46.1
- 预估收益区间: 主线程压力下降，交互流畅度提升
- 涉及文件集合（Top 8）:
  - `frontend/src/stores/translate.js`
  - `frontend/src/api/index.js`
  - `frontend/src/views/ReaderView.vue`
  - `frontend/src/components/ui/SlicedImage.vue`
  - `frontend/src/composables/useReadingHistory.js`
  - `frontend/src/stores/manga.js`
  - `frontend/src/views/HomeView.vue`
  - `frontend/src/stores/settings.js`
