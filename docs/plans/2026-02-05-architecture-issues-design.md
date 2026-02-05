# 代码架构问题整治设计

> 生成日期: 2026-02-05

## 目标
- 解决 ARCHITECTURE_ISSUES.md 中 P2 + P3 全部问题
- 减少重复实现与漂移风险，统一配置与工具入口
- 清理无引用/legacy 代码，降低维护成本
- 每完成一部分在 ARCHITECTURE_ISSUES.md 中标记并给出简短摘要

## 非目标
- 不做功能扩展（除为消除重复而必要的共享模块/接口）
- 不改变现有对外 API 的语义（新增接口保持兼容）
- 不进行大规模重构或跨模块性能优化

## 已确认的决策
- 删除 `core/quality_gate.py` 与 `tests/test_quality_gate.py`
- 语言设置接入后端：运行期生效 + 写入 `.env` 持久化；翻译模块采用 lazy binding 读取 settings
- `/parser/parse-list` 与 `/scraper/catalog` 合并
- CLI 入口统一 `main.py`；`scripts/cli.py` 变薄封装或标记开发工具；`batch_translate.py` 合并为 `main.py` 子命令
- 前端由 FastAPI 仅 dev 提供（`SERVE_FRONTEND=dev`），生产统一 Nginx
- Settings 字段保留并统一使用（替代散落 `os.getenv()`）
- 模型设置 API 统一 `_model_override` 单通道
- 噪声过滤：OCR 阶段为主、翻译阶段轻量语义判断；删除 `line_merger` 过滤
- 删除 `image_processor.py` 与 `detector.py`
- 新建 `core/constants.py`，`EDGE_BAND_RATIO = 0.12`
- 删除 `ocr_engine.py` 并更新 import 链
- Tk GUI 保留但移动到 `tools/` 或 `legacy/` 并标注 deprecated
- 删除 `app/static/js/main.js` 与 `app/static/manifest.json`
- 删除 `MODEL_WARMUP_TIMEOUT`
- 统一 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK`（修改 `main.py`）
- 删除 `docker-compose.yml` 中重复 Paddle flags
- SFX 规则合并到 `translator._is_sfx`
- 抽取 `scraper/url_utils.py`、`scraper/challenge.py`、`scraper/cookies.py`
- parser 抓取复用 scraper
- stderr 抑制统一为 `core/utils/stderr_suppressor.py`，使用 `SUPPRESS_NATIVE_STDERR`
- 删除 `postprocessing.merge_line_regions`（legacy）
- 删除 `paddle_engine.recognize_batch`、`detect_and_recognize_roi`
- 删除 `translator.merge_adjacent_regions`

## 分阶段设计

### 阶段 A：配置与设置统一
- 新增 `POST /settings/language`：更新 runtime 覆盖并写入 `.env`
- `get_current_settings` 返回覆盖后的语言设置
- pipeline/translator 使用 lazy binding 读取 settings，避免重建 pipeline
- 删除 `MODEL_WARMUP_TIMEOUT` 配置
- 统一模型源检查变量名
- 移除 docker-compose 中重复 Paddle flags
- 模型设置 API 只保留 `_model_override`

### 阶段 B：OCR/翻译链路一致性
- 噪声过滤统一到 OCR 阶段为主，翻译阶段仅保留语义判断
- 合并 SFX 规则到 `translator._is_sfx`
- 新增 `core/constants.py`，统一 `EDGE_BAND_RATIO`
- 删除 legacy/无引用函数（`postprocessing.merge_line_regions`、`translator.merge_adjacent_regions`）
- 删除 `paddle_engine.recognize_batch`、`detect_and_recognize_roi`
- 删除 `ocr_engine.py` 并更新 import
- 删除 `image_processor.py`、`detector.py`
- stderr 抑制抽成统一模块

### 阶段 C：Scraper/Parser/CLI 统一
- 抽共享工具：`url_utils` / `challenge` / `cookies`
- `/parser/parse-list` 合并到 `/scraper/catalog`
- parser 抓取统一复用 scraper fetch
- CLI 入口整合：`main.py` 为标准入口，`batch_translate.py` 合并为子命令

### 阶段 D：前端残留与工具整理
- FastAPI 仅 dev 模式提供前端（`SERVE_FRONTEND=dev`）
- 删除 `app/static/js/main.js` 与 `app/static/manifest.json`
- Tk GUI 移动到 `tools/` 或 `legacy/` 并标记 deprecated

## 风险与缓解
- 噪声过滤规则调整可能影响边缘文本：用指定样例回归验证
- CLI 行为统一可能影响脚本使用方式：保留薄封装兼容旧路径
- 设置 runtime 更新避免重建 pipeline：确保语言读取点使用最新 settings

## 验证清单
- 噪声过滤样例：普通对话、SFX、边缘水印、章节编号
- 翻译 API：默认语言、更新语言后的请求
- CLI：单图翻译、批量翻译
- Scraper：URL 解析、Cloudflare 识别、Cookie 解析
- 前端：dev 模式可由 FastAPI 提供，生产路径无冲突

