# 质量报告 Debug 字段设计

日期：2026-02-01  
项目：manhua  
状态：设计已确认（方案 A）

## 背景
当前质量报告缺少对 OCR/合并/擦除/翻译的调试信息，导致问题定位成本高。需要在**不改变主流程**、**不污染生产报告**的前提下，提供可选的调试字段，并避免与现有字段（如 `source_text`、`normalized_text`）重复。

## 目标
- 在质量报告中可选写入调试信息（默认关闭）。
- 仅保留必要字段，避免冗余。
- 提供 Inpainter mask 的统计信息（面积、bbox、覆盖率）。
- 明确区分 `no_regions` 与 `empty_mask` 的跳过原因。
- 可关联 debug 产物（mask/overlay 等）路径。

## 非目标
- 不改变 OCR/翻译/渲染逻辑。
- 不强制保存 debug 产物文件（仅在开启 DEBUG_ARTIFACTS 时保存）。
- 不引入额外模型或推理步骤。

## 方案概览（A：在质量报告内嵌 Debug）
当 `QUALITY_REPORT_DEBUG=1` 时，质量报告新增顶层 `debug` 与 `regions[].debug`。默认关闭以保证生产报告体积稳定。

### 顶层 `debug`
```json
{
  "debug": {
    "enabled": true,
    "artifacts": [
      {"name": "05_inpaint_mask", "path": "output/debug/.../05_inpaint_mask.png"},
      {"name": "05_inpaint_mask_cc_overlay", "path": "..."}
    ],
    "flags": {
      "debug_artifacts": true,
      "debug_report": true
    }
  }
}
```

### 区域级 `regions[].debug`
仅保留必要字段，避免重复 `source_text/normalized_text`。
```json
{
  "regions": [
    {
      "region_id": "...",
      "source_text": "...",
      "normalized_text": "...",
      "debug": {
        "ocr_text_raw": "...",
        "merge_reason": "same_bubble|line_merge|edge_merge|...",
        "group_id": "g12",
        "post_rec_applied": true,
        "translator_fallback": {"used": true, "reason": "api_error"},
        "inpaint_mask_stats": {
          "area_px": 1234,
          "bbox": [x1, y1, x2, y2],
          "coverage_ratio": 0.021,
          "empty_mask": false
        },
        "inpaint_skipped_reason": "no_regions|skip_translation|inpaint_disabled|empty_mask"
      }
    }
  ]
}
```

> 说明：`ocr_text_raw` 仅保留原始 OCR 文本；`normalized_text` 已在顶层字段存在，不再重复。

## Inpaint 统计策略
- **不依赖磁盘保存**：在内存中统计 mask 的面积、bbox 与覆盖率，直接写入 `regions[].debug.inpaint_mask_stats`。
- **DEBUG_ARTIFACTS=1** 时可额外保存 mask 与 overlay 图片，但统计逻辑不依赖保存。
- 新增 `empty_mask`：mask 生成但面积为 0（例如极小区域被过滤），与 `no_regions` 区分。

## 错误处理
- 质量报告写入失败不阻塞主流程，记录日志并设置 `debug.flags.report_write_failed=true`。
- debug 字段缺失用 `null` 表示，并用 `debug.flags` 标注原因。

## 测试计划
1. **质量报告开关测试**：开启/关闭 `QUALITY_REPORT_DEBUG` 时字段存在性正确。
2. **mask 统计测试**：构造小矩形 mask 验证 `area/bbox/coverage`。
3. **错误路径测试**：`empty_mask` 与 `no_regions` 区分正确。
4. **端到端**：确认 `debug.artifacts` 路径写入且不影响常规字段。

## 兼容性
debug 关闭时报告结构保持原样，不影响旧版解析器。
