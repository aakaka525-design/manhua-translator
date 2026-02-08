# 04 Remediation Roadmap

- 生成日期: 2026-02-08
- 基线参考: `docs/perf_audit/2026-02-08/00_baseline.md`, `docs/perf_audit/2026-02-08/baseline_metrics.json`
- 排序原则: 优先级分数 + 对 W2/W3（章节与高文本页）的实测影响
- 本轮重点: OCR、translator；超分非本轮主焦点，仅保留必要兼容项

## M1（快速收益，1-2 天）

### 1. OCR 全局串行锁导致任务互斥
- 问题: `core/modules/ocr.py` 使用全局 `_ocr_lock`，多任务并发时 OCR 阶段被强制串行。
- 涉及文件: `core/modules/ocr.py`, `core/pipeline.py`
- 改造动作（可执行步骤）:
  1. 将全局锁替换为可配置并发门限（如 `OCR_MAX_CONCURRENCY`）。
  2. 对同进程 OCR engine 调用加信号量而非全局互斥。
  3. 在 pipeline metrics 增加 `ocr_queue_wait_ms`。
- 风险与兼容性: PaddleOCR 线程安全风险，需要先在单机压测验证 2~4 并发稳定性。
- 预计收益（耗时下降区间）: OCR 阶段 15%~30%，W2 E2E 8%~18%。
- 验收指标: W2 `ocr` p50 降低 >=15%，失败率不升高。

### 2. 长图 tile 串行处理，边缘二次识别叠加耗时
- 问题: `core/vision/ocr/paddle_engine.py` 对 tiles 串行循环，且默认追加 edge tiles。
- 涉及文件: `core/vision/ocr/paddle_engine.py`, `core/vision/tiling.py`
- 改造动作（可执行步骤）:
  1. 新增 `OCR_TILE_MAX_CONCURRENCY` 并行处理 tiles（受信号量控制）。
  2. 仅在边界重叠命中率低时触发 edge tiles（条件化）。
  3. 输出 `tile_count`, `tile_avg_ms`, `edge_tile_count` 到质量报告。
- 风险与兼容性: 过高并发可能降低识别稳定性；默认从 2 并发起步。
- 预计收益（耗时下降区间）: OCR 阶段 20%~40%。
- 验收指标: W3 `ocr` p50 从 54s 下降到 <=43s。
  - 已验证安全旋钮（W3 720x19152 单页，regions=84）:
    - `OCR_TILE_HEIGHT=1024 OCR_TILE_OVERLAP_RATIO=0.25` 将 OCR 从 ~44.8s 降到 ~31.9s（tile_count 36 -> 25）。
    - `OCR_TILE_HEIGHT=1536 OCR_TILE_OVERLAP_RATIO=0.25` 更快但 regions +2，需确认是否引入噪声/重复。

### 3. Translator 单批次优先导致尾延迟放大
- 问题: `core/ai_translator.py` 默认“单大批次优先，失败再切块”，在高文本页出现长尾。
- 涉及文件: `core/ai_translator.py`
- 改造动作（可执行步骤）:
  1. 将策略改为“按 token 预算预切块 + 小并发”而非先 full-batch。
  2. 引入 `max_chars_per_batch` 与 `max_items_per_batch` 双阈值。
  3. 保留 full-batch 作为小样本特例（<=N 条）。
- 风险与兼容性: API 调用数上升，需要配额监控。
- 预计收益（耗时下降区间）: translator p95 降低 25%~45%。
- 验收指标: W3 `translator` p95 降低 >=30%。

### 4. Translator 回退链过长，失败路径重复调用
- 问题: 主模型超时/失败后触发多层 fallback，单页可能重复远端调用。
- 涉及文件: `core/ai_translator.py`, `core/modules/translator.py`
- 改造动作（可执行步骤）:
  1. 增加每页总重试预算与每批次重试预算。
  2. 对同一文本失败引入短期负缓存（避免重复重试）。
  3. 区分可重试错误与不可重试错误。
- 风险与兼容性: 过严预算可能降低成功率，需要平衡。
- 预计收益（耗时下降区间）: translator 阶段 10%~25%。
- 验收指标: `retry_count_est_avg` 下降 >=20%，成功率不下降。

### 4b. zh Fallback 重翻译逐条调用导致远端请求过多（可选 batch）
- 问题: 当目标语言为 zh 时，若首轮输出缺少 CJK 或英文占比过高，会触发逐条 retranslate（`translate()`）+ 可能的 Google fallback；在长图高文本页容易放大尾延迟。
- 涉及文件: `core/modules/translator.py`
- 改造动作（可执行步骤）:
  1. 增加 A/B 开关 `AI_TRANSLATE_ZH_FALLBACK_BATCH=0|1`（默认 0）。
  2. 当开关启用时，将 zh retranslate 从逐条 `translate()` 改为一次 `translate_batch()`（带 per-item contexts）。
  3. 保持 Google fallback 作为 batch 后仍失败的兜底。
  4. 输出可解释指标：`zh_retranslate_items/ms`、`google_fallback_items/ms`。
- 风险与兼容性: batch 可能改变输出（跨条目同请求）；默认关闭，仅在 W1/W2/W3 通过质量门槛后再推广。
- 预计收益（耗时下降区间）: translator p95 降低 10%~30%（取决于 fallback 条目数与远端 RTT）。
- 验收指标: W3 translator 阶段耗时下降 >=30% 且抽样译文语义不回退。

### 4c. Gemini primary timeout 12s -> 15s（config-only，减少 timeout->fallback 堆叠）
- 问题: `core/ai_translator.py` 在 fallback chain 存在时启用 `asyncio.wait_for` 超时护栏（默认 `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=12000`）。对 `gemini-3-flash-preview` 来说 12s 过紧，会频繁触发超时并进入 fallback，放大远端调用次数与尾延迟。
- 涉及文件: `core/ai_translator.py`
- 改造动作（可执行步骤）:
  1. 部署侧在 docker env/.env 添加 `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`（保持代码默认不改）。
  2. 仅在 Gemini + fallback chain 场景启用；单 provider 无 fallback 时该护栏不生效（保持旧行为）。
  3. 在 W2/W3 采样记录 `primary timeout` 与 `fallback provider` 次数，作为验收指标的一部分。
- 风险与兼容性: 阈值更高意味着单次最坏等待变长，但通常会减少 fallback 堆叠，降低 p95/p99。需要在 W2 并发场景复测确认整体吞吐/稳定性。
- 预计收益（耗时下降区间）:
  - W3（同一页 A/B 实测，`OCR_TILE_OVERLAP_RATIO=0.25` + `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`）:
    - `translator` 120.1s -> 83.8s（约 -30%）
    - `requests_fallback` 9 -> 5；`zh_retranslate_ms` 43.8s -> 4.0s
    - `primary timeout` 6 -> 2（AI 日志计数）
  - W2 tail（章节并发采样，pages 7+9, `-w 2`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`；用于验证稳定性而非对比收益）:
    - Page 9: `translator` 104.0s；`total` 173.1s；`[翻译失败]=0`；`no_cjk_with_ascii=0`
    - AI log（本次 run 全局计数）: `primary timeout after 15000ms=3`；`fallback provider=3`
- 验收指标:
  - W3: `translator` p95 下降，且 `primary timeout`/`fallback provider` 次数显著下降。
  - 质量守门: OCR regions 不下降、`[翻译失败]` 不上升、mixed-language heuristic 不回退。

### 4d. Prevent Hangul leakage in zh outputs（zh fallback 输入选择 + unknown SFX 保留原画）
- 问题: 并发压力场景下，部分 zh 目标输出中出现韩文残留（Hangul），会造成读者不可读/观感差；并且会触发额外的回退与重试，放大 `translator` 的尾延迟。
- 涉及文件: `core/modules/translator.py`, `core/sfx_dict.py`
- 改造动作（可执行步骤）:
  1. zh fallback 重翻译时，若首轮输出包含 Hangul，则强制使用 `src_text` 作为 fallback 输入（避免把“损坏输出”喂回模型）。
  2. SFX 路径对“不在词典中的 Hangul SFX”不渲染替换文字（`target_text=""`），保留原画（避免用中文字体重新绘制韩文）。
  3. 增加回归测试覆盖（Hangul+英文混杂输出、unknown Hangul SFX）。
- 风险与兼容性: 可能减少“强行覆盖”SFX 的范围（未知 SFX 不再尝试替换），但质量更稳定；对非 zh 目标无影响。
- 预计收益（耗时下降区间）:
  - 质量收益: `pages_has_hangul` -> 0（硬质量门槛）
  - 性能收益（云端 3 章并发采样，42 页）:
    - Before (`_stress_20260208_134907.list`): `pages_has_hangul=2`, `translator_p95=66908ms`
    - After  (`_stress_20260208_142518_s2_afterfix.list`): `pages_has_hangul=0`, `translator_p95=29367ms`
- 验收指标:
  - 并发章节压测（>=3 章并发，UPSCALE=0）下：`[翻译失败]=0` 且 `pages_has_hangul=0`。
  - `translator` p95/p99 不劣化（理想：下降），且容器无 OOM/restart。

### 5. 高频日志导致 I/O 与序列化放大
- 问题: translator/OCR 路径包含大量逐条日志与长文本日志。
- 涉及文件: `core/ai_translator.py`, `core/modules/translator.py`, `core/modules/ocr.py`
- 改造动作（可执行步骤）:
  1. 将逐条日志降级到 debug，info 仅保留聚合指标。
  2. 统一日志截断与抽样策略（按任务比例抽样）。
  3. 在错误日志中保留必要上下文 ID，去掉重复正文。
- 风险与兼容性: 排障信息减少，需要保留可开关详细日志。
- 预计收益（耗时下降区间）: E2E 3%~8%。
- 验收指标: 单任务日志行数下降 >=40%。

### 6. SSE 广播逐连接 await，推送链路阻塞
- 问题: `app/routes/translate.py` 广播时对每个 listener `await queue.put()`，慢消费者会拖慢广播。
- 涉及文件: `app/routes/translate.py`
- 改造动作（可执行步骤）:
  1. listener queue 改为有界队列 + 丢弃旧进度策略。
  2. 广播改为并发 fan-out，单个慢连接隔离。
  3. 增加 queue backlog 指标。
- 风险与兼容性: 进度事件可能被抽样/丢弃（但最终态不丢）。
- 预计收益（耗时下降区间）: API 调度链路 5%~12%。
- 验收指标: 高并发章节下 `progress` 事件延迟 p95 下降 >=30%。

### 7. 前端 progress 事件每条都写响应式状态
- 问题: `frontend/src/stores/translate.js` 对每条 progress 直接更新 chapter 对象，事件密集时重渲染频繁。
- 涉及文件: `frontend/src/stores/translate.js`, `frontend/src/views/MangaView.vue`
- 改造动作（可执行步骤）:
  1. 增加 200~500ms 前端节流合并更新。
  2. 只在关键字段变化时写状态。
  3. `chapter_complete` 保持实时，不节流。
- 风险与兼容性: 进度显示颗粒度变粗。
- 预计收益（耗时下降区间）: 前端主线程占用明显下降，体感卡顿减少。
- 验收指标: 翻译中页面 FPS 与输入响应稳定，无明显卡顿。

## M2（中等改造，2-5 天）

### 8. OCR 后处理链路复杂，可能出现 O(N²) 合并成本
- 问题: OCR 结果经过多轮过滤/包含关系/相邻合并与排序，区域数升高时成本陡增。
- 涉及文件: `core/vision/ocr/postprocessing.py`, `core/vision/ocr/paddle_engine.py`
- 改造动作（可执行步骤）:
  1. 对区域按网格分桶后再做候选匹配。
  2. 限制重复 merge 轮次并输出 merge 命中统计。
  3. 增加性能断言测试（大区域数样本）。
- 风险与兼容性: 可能影响框合并精度。
- 预计收益（耗时下降区间）: OCR 后处理 20%~35%。
- 验收指标: 区域数量与可读性无明显回归，耗时下降达标。

### 9. Cross-page 处理与翻译主路径耦合较重
- 问题: crosspage 文本拼接、补偿与二次翻译回写可能放大 translator 开销。
- 涉及文件: `core/modules/translator.py`, `core/crosspage_processor.py`, `core/crosspage_pairing.py`
- 改造动作（可执行步骤）:
  1. 将 crosspage 组与普通组完全拆分执行与计时。
  2. 对 crosspage 上下文长度设硬上限。
  3. 仅对置信度高的配对启用跨页补偿。
- 风险与兼容性: 跨页语义连贯性可能略降。
- 预计收益（耗时下降区间）: translator 阶段 8%~20%。
- 验收指标: crosspage 命中页的质量分数不下降。

### 10. Translator 请求上下文无差别拼接导致 token 膨胀
- 问题: context 拼接可能包含冗余文本，拉高单次请求长度。
- 涉及文件: `core/modules/translator.py`, `core/ai_translator.py`
- 改造动作（可执行步骤）:
  1. context 按“近邻优先+长度上限”裁剪。
  2. 只保留与当前 bubble 相关的术语和角色信息。
  3. 在质量报告记录 `prompt_chars`。
- 风险与兼容性: 过度裁剪可能丢失语境。
- 预计收益（耗时下降区间）: translator 阶段 10%~25%。
- 验收指标: 平均 prompt 长度下降 >=25%，准确率无明显下降。

### 11. Pipeline 每阶段写状态+报告为同步尾部开销
- 问题: `write_quality_report` 在主流程同步执行，章节批量时尾部累计明显。
- 涉及文件: `core/pipeline.py`, `core/quality_report.py`
- 改造动作（可执行步骤）:
  1. 质量报告写入改为后台异步队列。
  2. 失败场景保留同步关键报告，其余异步化。
  3. 增加写入失败重试与降级策略。
- 风险与兼容性: 异步写入可能导致极短窗口内文件未落盘。
- 预计收益（耗时下降区间）: E2E 2%~6%。
- 验收指标: 质量报告完整率 >=99.9%。

### 12. API 章节批处理缺少 OCR/translator 分离并发上限
- 问题: 批处理容易在 OCR 与 translator 阶段互相抢资源。
- 涉及文件: `app/routes/translate.py`, `core/pipeline.py`
- 改造动作（可执行步骤）:
  1. 增加分阶段并发限制（OCR 并发、translator 并发独立）。
  2. 采用带权队列，优先推进已开始章节。
  3. 增加章节级排队等待时间指标。
- 风险与兼容性: 调度逻辑复杂度上升。
- 预计收益（耗时下降区间）: W2 p95 下降 10%~20%。
- 验收指标: 章节任务排队等待 p95 下降 >=20%。

### 13. Frontend 多处 watch 触发重复列表动画与刷新
- 问题: `ScraperView.vue` 等页面 watch 较多，状态变化时可能重复触发昂贵 UI 更新。
- 涉及文件: `frontend/src/views/ScraperView.vue`, `frontend/src/views/MangaView.vue`
- 改造动作（可执行步骤）:
  1. 合并 watch 源并去重触发。
  2. 大列表更新改为局部 patch，不整体重算。
  3. 监控每次刷新耗时。
- 风险与兼容性: 逻辑重构需回归 UI 行为。
- 预计收益（耗时下降区间）: 前端响应延迟下降 15%~35%。
- 验收指标: 章节列表滚动与更新无掉帧。

### 14. Scraper 下载并发与译链并发缺少统一背压
- 问题: 抓取与翻译同时高并发会放大整体抖动。
- 涉及文件: `scraper/downloader.py`, `scraper/engine.py`, `app/routes/translate.py`
- 改造动作（可执行步骤）:
  1. 下载并发、翻译并发统一纳入全局资源预算。
  2. 抓取阶段加自适应降速（队列长度驱动）。
  3. 关键路径优先级：翻译任务优先于预抓取。
- 风险与兼容性: 峰值吞吐可能下降，但稳定性提升。
- 预计收益（耗时下降区间）: 高负载下失败率显著下降。
- 验收指标: 压测 30 分钟无明显超时雪崩。

## M3（结构性优化，>5 天）

### 15. OCR/translator 阶段拆分为独立 worker 池
- 问题: 目前多阶段在同进程资源竞争，难以独立扩容。
- 涉及文件: `core/pipeline.py`, `app/deps.py`, `app/routes/translate.py`
- 改造动作（可执行步骤）:
  1. 将 OCR、translator 拆为两个 worker pool。
  2. 通过任务队列交接中间结果。
  3. 增加 worker 级熔断与重试。
- 风险与兼容性: 架构复杂度明显上升。
- 预计收益（耗时下降区间）: 章节吞吐 30%~60%。
- 验收指标: W2 p95 下降 >=35%，服务稳定性提升。

### 16. 建立 token 预算驱动的 translator 调度器
- 问题: 当前批次策略主要按条数，未按 token 预算精细调度。
- 涉及文件: `core/ai_translator.py`, `core/modules/translator.py`
- 改造动作（可执行步骤）:
  1. 估算 token 成本并按预算打包。
  2. 动态调整并发与 chunk size。
  3. 记录 token 预算命中率与失败率。
- 风险与兼容性: 调度器实现复杂。
- 预计收益（耗时下降区间）: translator p95 再降 15%~30%。
- 验收指标: 长文本页长尾明显收敛。

### 17. 建立 OCR 结果增量缓存策略
- 问题: 同图重复处理时 OCR 重算成本高。
- 涉及文件: `core/modules/ocr.py`, `core/vision/ocr/cache.py`
- 改造动作（可执行步骤）:
  1. 增量缓存 key 增加图像 hash + 语言 + 引擎版本。
  2. 引入缓存命中统计与 TTL 策略。
  3. 对热点章节预热缓存。
- 风险与兼容性: 缓存一致性管理复杂。
- 预计收益（耗时下降区间）: 重复任务 OCR 耗时下降 50%+。
- 验收指标: 缓存命中率目标 >=60%。

### 18. 前端事件模型升级为“阶段快照”
- 问题: 事件驱动细粒度更新对前端过于频繁。
- 涉及文件: `app/routes/translate.py`, `frontend/src/stores/translate.js`
- 改造动作（可执行步骤）:
  1. 后端按固定周期推送阶段快照（非每个子事件）。
  2. 前端按 task_id 合并渲染。
  3. 保留关键事件即时推送（完成/失败）。
- 风险与兼容性: 需要前后端协议联调。
- 预计收益（耗时下降区间）: UI 更新成本下降 30%~50%。
- 验收指标: 高并发任务下界面稳定。

### 19. 指标体系补齐（CPU/内存/队列等待）
- 问题: 当前质量报告缺资源指标，根因归因不闭环。
- 涉及文件: `core/metrics.py`, `core/pipeline.py`, `core/quality_report.py`
- 改造动作（可执行步骤）:
  1. 新增进程级 CPU%、RSS、队列等待时间。
  2. 指标写入 quality report 与日志。
  3. 建立基线与回归告警阈值。
- 风险与兼容性: 指标采集带少量额外开销。
- 预计收益（耗时下降区间）: 不是直接降耗时，但显著提高优化效率。
- 验收指标: 每次任务都能给出完整资源指标。

### 20. 建立性能回归门禁
- 问题: 缺少自动化性能回归检查，优化成果易回退。
- 涉及文件: `tests/`（后续新增）, `docs/perf_audit/*`
- 改造动作（可执行步骤）:
  1. 固化 W1/W2/W3 样本与脚本。
  2. CI 增加关键阶段耗时阈值校验。
  3. PR 模板要求附优化前后对比。
- 风险与兼容性: CI 时间增加。
- 预计收益（耗时下降区间）: 保证收益可持续，避免回退。
- 验收指标: 回归任务稳定通过，超阈值自动阻断。
