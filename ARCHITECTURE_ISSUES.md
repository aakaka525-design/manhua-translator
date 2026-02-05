# 架构问题清单（重建）

> 说明：原文件误删，按实现计划与已完成提交重建，请校对补充。

标记说明：
- [x] 已完成（含简短摘要）
- [ ] 未完成

P1：运行时错误
- [ ] （待补充）如需记录具体运行时错误，请注明复现步骤与日志。

P2：配置与设置（阶段 A）
- [x] 语言更新 API + `.env` 持久化 — 新增 `/settings/language`，运行期生效并写回 `.env`。
- [x] 翻译模块语言 lazy binding — 翻译阶段按 `get_settings()` 动态读取语言。
- [x] 模型设置仅 `_model_override` 单通道 — 移除环境变量写入。
- [x] 统一模型源检查变量名 — `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK`。
- [x] 删除 `MODEL_WARMUP_TIMEOUT` 与重复 Paddle flags — 清理 `docker-compose.yml` / `README.md`。
- [x] Settings 使用统一入口 — 相关调用收敛到 `get_settings()`。

P2：OCR/翻译链路（阶段 B）
- [x] 噪声过滤以 OCR 阶段为主 — 翻译阶段保留轻量兜底（如短噪声/符号）。
- [x] 行合并噪声过滤范围偏窄 — `line_merger` 对齐短大写/罗马数字/短数字等规则，避免噪声参与合并。
- [x] SFX 规则合并到 `translator._is_sfx` — 保留现有规则。
- [x] `EDGE_BAND_RATIO` 常量化 — 已统一到 `core/constants.py`。
- [x] stderr 抑制统一 — `core/utils/stderr_suppressor.py`。
- [x] 删除 legacy OCR 与无引用函数 — `quality_gate.py`、`merge_line_regions`、`recognize_batch`、`detect_and_recognize_roi` 等。
- [x] 删除无用模块与重导出 — `ocr_engine.py`、`image_processor.py`、`detector.py`。

P2：Scraper/Parser/CLI（阶段 C）
- [x] 抽取 `scraper/url_utils.py` — 统一 URL 解析与推断。
- [x] 抽取 `scraper/challenge.py` — Cloudflare 识别统一。
- [x] 统一 cookie 解析 — 使用共享 helper。
- [x] 路由仍保留 `_normalize_base_url` — parser/scraper 改为复用 `scraper/url_utils.normalize_base_url`。
- [x] `ParseRequest` 与 `ParseListRequest` 重复 — 统一为同一模型别名。
- [x] `/parser/parse-list` 与 `/scraper/catalog` 合并 — parser 列表走 scraper catalog。
- [x] parser fetch 复用 scraper fetch — 统一抓取实现。
- [x] CLI 入口统一 `main.py` — `scripts/cli.py` 薄封装、`batch_translate.py` 移除 CLI。

P3：前端与工具（阶段 D）
- [x] FastAPI 前端仅 dev 模式提供 — `SERVE_FRONTEND=dev` gate + 删除残留静态资源。
- [x] Tk GUI 脚本迁移至 `tools/` 并注明 deprecated。
- [x] `tools/scraper_gui.py` 仍含 `_slugify_keyword` 重复逻辑 — 改为复用 `scraper.url_utils.slugify_keyword`。
