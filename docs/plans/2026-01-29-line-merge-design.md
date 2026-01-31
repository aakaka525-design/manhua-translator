# Line Merge Design (Crosspage Context)

Date: 2026-01-29
Project: manhua
Focus: OCR 后同字幕框文本合并（行内合并），提升翻译连贯性与擦除一致性

## 1. 背景
OCR 输出常出现同一字幕框被切分为多个碎片（例如“너무”+“좋아”），导致翻译不连贯、擦除范围不完整、渲染位置异常。需要在翻译前合并碎片，并确保 inpaint 使用合并后的 box。

## 2. 目标
- 将同一字幕框/同一行内的碎片合并为单条文本。
- 合并后使用 union box 参与擦除与渲染。
- 维持水印/拟声词等特殊区域不被误合并。
- 保持实现轻量、可配置、易回退。

## 3. 非目标
- 引入新的气泡检测/分割模型。
- 全页级语义重排或上下文改写。

## 4. 方案概览
新增 `LineMerger`，位于 OCR 后、翻译前，工作流：

```
OCR -> OCRPostProcessor -> BubbleGrouper -> LineMerger -> Translation -> Inpaint -> Render
```

- BubbleGrouper 负责初步分组（沿用现有 `group_adjacent_regions()`）。
- LineMerger 在每个 group 内进行“行内聚类 + 拼接”。
- 合并文本**不保留换行**，由渲染器自动断行。
- 合并前过滤 `is_watermark/is_sfx`，避免污染对话文本。

## 5. 合并规则（建议默认）
以分组内 `median_height` 作为基准：

- 同行判定：
  - `y_gap <= 0.6 * median_height`
  - `abs(h1 - h2) <= 0.5 * median_height`
- 行内邻近：
  - `x_gap <= 0.8 * median_height`
- 行内拼接：按 `x1` 升序拼接
  - CJK: 直接拼接
  - 英数字：词边界插入单空格
- 跨行顺序：按 `(row_y, x)` 排序拼接

### 回退条件
- `max_h / min_h > 2.0`（高度差过大）
- 合并后 `union_box` 超出 group 边界过多
- 低置信（`confidence < 0.4`）可不参与合并

## 6. 数据与日志
- 新增字段（可选）：
  - `merged_from_ids: list[UUID]`
  - `line_count: int`
- 记录：每页 `merge_count`、`merged_from_ids`

## 7. 集成点
- 新模块：`core/text_merge/line_merger.py`（或放入 `core/translator.py` 辅助区）
- 在 `core/modules/translator.py` 中调用（翻译前）
- 保持 inpaint 使用合并后的 `box_2d`

## 8. 测试计划
1) 单元测试：
   - 输入 `너무` + `좋아`，输出 `너무좋아`
   - `box_2d` 为 union
2) 负样例：
   - 不同气泡/高度差异过大不合并
3) 端到端：
   - Mock OCR 产生碎片，验证最终渲染为合并后文本

## 9. 风险与缓解
- 误合并：阈值配置 + 回退策略 + 负样例测试
- 合并过度：排除 `is_watermark/is_sfx`

## 10. 配置项（建议）
- `line_merge.yml`：
  - `row_gap_ratio: 0.6`
  - `x_gap_ratio: 0.8`
  - `height_ratio: 0.5`
  - `max_height_ratio: 2.0`
  - `min_confidence: 0.4`

---

Ready for implementation plan after approval.
