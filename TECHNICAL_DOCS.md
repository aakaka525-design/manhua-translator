# 漫画翻译项目技术文档 (Manga Translator Technical Documentation)

## 1. 项目概览
本项目旨在实现全自动、高质量的漫画翻译与嵌字流程。核心通过深度学习技术解决复杂的漫画文本检测、去除、翻译及回填问题，追求"完美"的视觉效果。

## 2. 核心架构

系统采用模块化 Pipeline 设计：

```
Detector → OCR → Translator → Inpainter → Renderer
```

### 2.1 视觉引擎 (Core Vision)

#### OCR 引擎 (`core/vision/ocr_engine.py`)
*   集成 **PaddleOCR v3**（PP-OCRv5），针对漫画场景深度定制。
*   **模型配置**: 轻量级 Mobile 模型
    - 检测: `PP-OCRv5_mobile_det`
    - 识别: `en_PP-OCRv5_mobile_rec`
*   **动态切片 (Tiling)**:
    - `TilingManager` 自动切分长图为 768px 高度切片（50% 重叠）
    - 自动坐标映射（局部 → 全局）
    - NMS 去重（IoU > 0.5）
*   **预处理增强**:
    - L 通道 CLAHE 对比度增强
    - 锐化滤波器
*   **噪声过滤**:
    - 尺寸过滤（< 15px 宽或 < 10px 高）
    - 宽高比过滤（> 20 或 < 0.05）
    - 短文本高置信度要求（≤ 3 字符需 > 0.85 置信度）
    - 纯数字过滤
    - 常见噪声模式正则过滤
*   **字段解析**: 使用 `rec_boxes` 获取边界框（优先于 `rec_polys`/`dt_polys`）

#### 切片管理器 (`core/vision/tiling.py`)
```python
tile_height = 768       # 切片高度
overlap_ratio = 0.5     # 重叠率 50%（384px）
min_tile_height = 256   # 最小切片高度
```
*   触发条件：图像高度 > 1152px (768 × 1.5)
*   滑动步长：384px

#### 图像修复 (`core/vision/inpainter.py`)
*   集成 **LaMa (Large Mask Inpainting)** 模型
*   **智能 Mask 生成**: 基于 OCR 区域生成，自动膨胀 8px
*   **间隙填充**: 自动填充垂直相邻文本块间隙

### 2.2 翻译模块 (`core/translator.py`)

*   **区域合并** (`merge_adjacent_regions`):
    - 翻译前自动合并相邻 OCR 区域为完整段落
    - 先按行分组（center_y 接近），再按 X 排序拼接
    - 大幅提升翻译上下文质量
*   **翻译器支持**:
    - `GoogleTranslator`: 使用 deep-translator 库（免费）
    - `ContextAwareTranslator`: 支持 Gemini/OpenAI API
    - `MockTranslator`: 测试用
*   **SFX 识别**: 自动识别拟声词并特殊处理

### 2.3 渲染引擎 (`core/renderer.py`)

*   **样式估算** (`StyleEstimator`):
    - 自动提取原图文字颜色（主色提取）
    - 估算字号、描边宽度
*   **智能排版**:
    - 二分查找适配气泡的最大字号
    - 中文避头尾规则自动换行
    - 自动描边增强

### 2.4 Pipeline 模块 (`core/modules/`)

**流程**: OCR → Translator → Inpainter → Renderer

| 模块 | 文件 | 职责 |
|------|------|------|
| OCRModule | `modules/ocr.py` | 检测+识别（`detect_and_recognize()` 统一入口） |
| TranslatorModule | `modules/translator.py` | 合并区域 + Google 翻译 |
| InpainterModule | `modules/inpainter.py` | LaMa 修复 |
| RendererModule | `modules/renderer.py` | 使用 TextRenderer 高级排版渲染 |

> **注意**: DetectorModule 已移除，检测功能合并到 OCRModule

## 3. 关键技术实现

### 3.1 OCR 统一入口
`OCRModule.process()` 调用 `PaddleOCREngine.detect_and_recognize()`：
- 支持动态切片（长图）
- 支持 NMS 去重
- 支持完整后处理流程

### 3.2 翻译层区域合并
`TranslatorModule.process()` 在翻译前调用 `merge_adjacent_regions()`:
```
原始: 18 个碎片区域
合并后: 4 个完整段落
```
合并逻辑：
1. 按 center_y 聚类分行
2. 每行内按 x1 排序
3. 拼接文本

### 3.3 噪声过滤策略
```python
# 过滤规则（ocr_engine.py）:
1. 尺寸: width < 15 or height < 10
2. 宽高比: > 20 or < 0.05
3. 短文本低置信: len ≤ 3 and conf < 0.85
4. 纯数字: /^[0-9,.]+$/
5. 常见噪声模式: 纯破折号、竖线、0/O/S 混合等
```

## 4. 文件结构

```
/
├── core/
│   ├── vision/
│   │   ├── ocr_engine.py    # PaddleOCR 引擎
│   │   ├── tiling.py        # 切片管理器
│   │   ├── text_detector.py # ContourDetector/YOLODetector
│   │   ├── inpainter.py     # LaMa 修复
│   │   └── image_processor.py
│   ├── modules/
│   │   ├── detector.py      # 检测模块
│   │   ├── ocr.py           # OCR 模块（统一入口）
│   │   ├── translator.py    # 翻译模块（含合并）
│   │   ├── inpainter.py     # 修复模块
│   │   └── renderer.py      # 渲染模块
│   ├── translator.py        # 翻译器实现
│   ├── renderer.py          # 渲染器实现
│   ├── pipeline.py          # Pipeline 管理器
│   └── models.py            # 数据模型
├── app/                     # FastAPI 服务接口
└── output/                  # 处理结果输出
```

## 5. 已知问题与优化方向

### 已知问题
- [ ] 切片边界可能导致小文本漏检（如 `IS.` 被切分）
- [ ] 手写体/拟声词检测效果待提升

### 优化方向
- [ ] 调整切片策略（增大重叠或使用自适应切片）
- [ ] 引入独立 SFX 检测器
- [ ] 优化 LaMa 本地推理速度
- [ ] 嵌字字体随机化
