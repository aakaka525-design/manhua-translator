# Debug Artifacts Design (Pipeline Stage Visuals)

Date: 2026-01-30  
Project: manhua  
Scope: 开发模式调试图输出（多阶段可视化）

## 1. 目标
- 在开发模式输出多张“阶段图”，直观展示 OCR/分组/翻译/擦除/渲染过程。
- OCR 检测框需贴标签显示识别文本。
- 通过统一目录与 manifest 方便定位问题与对比结果。

## 2. 开关与输出路径
- 环境变量：`DEBUG_ARTIFACTS=1`
- 输出目录：`output/debug/<task_id>/`

## 3. 产物清单（单图分阶段）
建议文件命名采用序号以便流程对照：
1) `01_ocr_boxes.png`  
   - 绘制 `box_2d`  
   - 标签：`normalized_text`，缺失时回退 `source_text`  
2) `02_grouping.png`  
   - 绘制 `render_box_2d`（无则用 `box_2d`）  
   - 标签：group_id / region_id（短 UUID）  
3) `03_watermark.png`（若启用水印）  
   - 标注 `is_watermark=True` 区域  
4) `04_translate.png`  
   - 在原图上绘制 `target_text` 标签  
5) `05_inpaint_mask.png`  
   - 合成 mask 二值图  
6) `06_inpainted.png`  
   - 擦除后中间图  
7) `07_layout.png`  
   - 渲染布局框（用于观察字号与位置）  
8) `08_final.png`  
   - 最终输出图（对照）

## 4. Manifest
输出 `manifest.json`，记录：
- task_id、image_path、output_dir
- 每阶段文件名、regions_count、notes、duration_ms

## 5. 约束
- 不影响生产（默认关闭）
- 输出统一、可复现、易对比
- 尽量不引入新依赖（使用 PIL 画框与标签）
