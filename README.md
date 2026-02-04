# 漫画翻译器

使用 OCR、AI 翻译与智能修复，自动翻译漫画/条漫文本。

## ✨ 功能特性

- **多语言 OCR** - PaddleOCR v5，支持韩语/日语/英语/中文
- **AI 翻译** - PPIO GLM / Google Gemini 高质量翻译
- **智能擦除** - LaMa 模型无痕去除原文
- **自动排版** - 动态字体大小适配气泡
- **网页爬虫** - 内置漫画下载器
- **Web 界面** - Vue 3 现代化前端

## 🚀 快速开始

### Docker（CPU，服务器推荐）

```bash
# 构建并启动
docker compose up -d --build

# 健康检查
curl http://localhost:8000/api/v1/system/models

# 首次启动需要下载模型，等待 API 健康后再启动前端：
docker compose up -d web
```

前端访问地址：

```
http://<host>/
```

注意事项：
- 模型与输出通过 bind mount 持久化：`./models`、`./data`、`./output`、`./logs`。
- CPU-only 默认参数在 `docker-compose.yml` 中已设置（禁用 OneDNN/PIR）。
- web 容器会反向代理 `/api`、`/data`、`/output` 到 API 服务。
- Apple Silicon / ARM 主机：PaddlePaddle 可能在 arm64 崩溃，请使用 amd64：
  - `DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose up -d --build`
  - 或在 `docker-compose.yml` 中保留 `platform: linux/amd64`
- LaMa 在 Docker 内为可选项（Pillow 与 PaddleOCR 版本有冲突时需关闭）。开启方式：
  - 编辑 `docker-compose.yml`，在 `api.build.args` 下设置 `INSTALL_LAMA: "1"`
  - 重新构建：`docker compose up -d --build`

**Docker 公网部署安全提示**
- 默认 `api` 仅绑定本机 `127.0.0.1:8000`，请通过 `web` 访问，不建议暴露 API 端口。
- `/`、`/api/`、`/data/`、`/output/` 已加 BasicAuth（前端静态资源也会要求登录）。
  - 如需公开前端，请移除 `docker/nginx.conf` 中 `location /` 的认证配置。
- 需先生成 `.htpasswd`（推荐容器方式）：
  ```bash
  docker run --rm -v "$PWD/.htpasswd:/etc/nginx/.htpasswd" httpd:2.4-alpine htpasswd -Bbc /etc/nginx/.htpasswd <user> <password>
  ```
- 如果本机已有 `htpasswd`，也可：`htpasswd -Bbc .htpasswd <user> <password>`
- BasicAuth 在 HTTP 下明文传输，生产环境必须配合 HTTPS（建议在外层反代/Caddy/Nginx/云平台 TLS 终止）。
- 若使用 `docker-compose.auth.yml` 的认证浏览器，请只对你的 IP 开放 `3000` 端口。

**常用 Docker 命令（排错用）**
```bash
# 查看容器状态
docker compose ps

# 查看 API 日志（最近 200 行）
docker compose logs api --tail 200

# 进入 API 容器查看环境变量
docker compose exec api env | grep -E 'PPIO|GEMINI'

# 仅重建 API 镜像并重启
docker compose up -d --build api

# 停止并清理（保留数据卷）
docker compose down
```

### 安装

```bash
# 本地依赖 + Real-ESRGAN（二进制）
./scripts/setup_local.sh

# CPU-only OCR 依赖（Linux 服务器）
pip install -r requirements-cpu.txt

# 前端依赖（可选，仅开发用）
cd frontend && npm install
```

### Linux（CPU）系统依赖

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y \
  libgl1 \
  libglib2.0-0 \
  ffmpeg \
  fonts-noto-cjk \
  fonts-noto-cjk-extra
```

### 配置

复制 `.env.example` 到 `.env` 并填写 API Key：

```env
# PPIO GLM API（主选）
PPIO_API_KEY=your_ppio_api_key
PPIO_BASE_URL=https://api.ppio.com/openai
PPIO_MODEL=zai-org/glm-4.7-flash

# Google Gemini API（备选）
GEMINI_API_KEY=your_gemini_api_key

# 翻译设置
SOURCE_LANGUAGE=korean
TARGET_LANGUAGE=zh

# 模型自动初始化
AUTO_SETUP_MODELS=on
MODEL_WARMUP_TIMEOUT=300
OCR_WARMUP_LANGS=korean
LAMA_DEVICE=cpu
```

### 超分（可选）

默认关闭，启用后会在**渲染完成后**对最终图进行超分处理并覆盖输出：

```env
UPSCALE_ENABLE=1
UPSCALE_BACKEND=pytorch
UPSCALE_DEVICE=auto
UPSCALE_MODEL_PATH=tools/bin/RealESRGAN_x4plus.pth
UPSCALE_MODEL=realesrgan-x4plus-anime
UPSCALE_SCALE=2
UPSCALE_TIMEOUT=120
UPSCALE_TILE=0
UPSCALE_STRIPE_ENABLE=0
UPSCALE_STRIPE_THRESHOLD=4000
UPSCALE_STRIPE_HEIGHT=2000
UPSCALE_STRIPE_OVERLAP=64
```

设备说明：
- `UPSCALE_DEVICE=auto`：优先 MPS（可用时），否则回退 CPU
- `UPSCALE_DEVICE=mps`：强制 MPS（不可用时直接报错）
- `UPSCALE_DEVICE=cpu`：固定 CPU

条带分块（用于超长图加速）：
- `UPSCALE_STRIPE_ENABLE=1` 且 `H > UPSCALE_STRIPE_THRESHOLD` 时启用
- `UPSCALE_STRIPE_HEIGHT` 控制每段高度
- `UPSCALE_STRIPE_OVERLAP` 控制段间重叠（避免接缝）

评估脚本（OCR 置信度对比）：

```bash
/Users/xa/Desktop/projiect/manhua/.venv/bin/python scripts/upscale_eval.py data/raw/sexy-woman/chapter-1/1.jpg --lang korean
```

评估脚本（固定检测框一致性）：

```bash
/Users/xa/Desktop/projiect/manhua/.venv/bin/python scripts/ocr_consistency_eval.py --orig input.jpg --upscaled output.jpg --lang korean --out output/consistency_eval/report.json
```

**模型选择说明**
- 所有 AI 模型通过 `PPIO_MODEL` 选择。
- 使用 PPIO 模型名（如 `zai-org/glm-4.7-flash`）走 PPIO。
- 使用 Gemini 模型名（如 `gemini-2.5-flash`）走 Gemini（需要 `GEMINI_API_KEY`）。
- 模型名包含 `gemini-` 会自动切换到 Gemini。

**OCR & 擦除模型**
- OCR 检测模型：`PP-OCRv5_mobile_det`
- OCR 识别模型：
  - 英文：`en_PP-OCRv5_mobile_rec`
  - 韩文：`korean_PP-OCRv5_mobile_rec`
- 擦除模型：LaMa（由 `core/modules/inpainter.py` 使用）

### 使用方式

```bash
# 启动服务（推荐）
python main.py server --port 8000

# 翻译单张图片
python main.py image test.jpg -o output/

# 翻译整章（并行）
python main.py chapter input/ output/ -w 3
```

### URL 解析

提供 URL 解析接口，用于解析漫画页面并返回结构化信息。

```bash
curl -X POST http://localhost:8000/api/v1/parser/parse \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/comic/1","mode":"http"}'
```

说明：`mode` 支持 `http`（默认）与 `playwright`（适用于 `/parser/parse` 与 `/parser/list`）。

**解析器列表**

获取当前可用解析器列表：

```bash
curl -X POST http://localhost:8000/api/v1/parser/list \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/comic/1","mode":"http"}'
```

说明：`mode` 支持 `http`（默认）与 `playwright`。

## 🧰 常见问题（Troubleshooting）

**1) 翻译全部失败 / `[翻译失败]`**
- 现象：质量报告里 `target_text` 以 `[翻译失败]` 开头，或翻译接口耗时极短。
- 原因：容器内缺少 `openai` 依赖，AI Translator 初始化失败。
- 修复：
  - 确保已安装 `openai`（Docker 已集成到 `docker/requirements-docker-cpu.txt`）
  - 重新构建镜像：`docker compose up -d --build`
  - 查看日志：`docker compose logs api --tail 200`

**2) `AI translator init failed: No module named 'openai'`**
- 现象：API 日志中出现上述错误。
- 修复：同上，重建镜像或手动安装 `openai`。

**3) OCR 返回空结果（`regions_count: 0`）**
- 现象：质量报告 `regions: []`，但图片有文字。
- 排查：
  - 确认 OCR 语言：`SOURCE_LANGUAGE=korean`、`OCR_WARMUP_LANGS=korean`
  - 查看 OCR 原始输出：`DEBUG_OCR=1` 并查看 `logs/*_app.log`
  - 检查 PaddlePaddle 兼容性（见下一条）

**4) Paddle 运行报错 / PIR / OneDNN 相关**
- 现象：`NotImplementedError: ConvertPirAttribute2RuntimeAttribute...`
- 修复：使用 CPU 兼容环境变量（默认已在 `docker-compose.yml` 中设置）：
  - `FLAGS_enable_pir_api=0`
  - `FLAGS_use_pir=0`
  - `FLAGS_use_pir_backend=0`

**5) Docker API 容器健康检查失败**
- 现象：`manhua-api-1 is unhealthy`
- 原因：首次启动模型下载较慢，健康检查未通过。
- 修复：等待模型下载完成后再启动 `web`，或查看日志：
  - `docker compose logs api --tail 200`

**6) 前端页面字体/图标加载失败（CORS / HTTPS）**
- 现象：浏览器报 `CORS policy: The request client is not a secure context...`
- 原因：公网 IP 通过 HTTP 访问时，Google Fonts / CDN 资源被浏览器限制。
- 修复：
  - 用 HTTPS 访问（推荐放在 Nginx/Caddy 反代上）
  - 或改为本地托管字体/图标资源

**7) 前端脚本 MIME 错误**
- 现象：`Failed to load module script: MIME type "text/html"`
- 原因：访问了错误的服务/端口（API 返回了 HTML）。
- 修复：
  - Docker 部署访问 `http://<host>/`（由 web 容器提供）
  - 开发模式访问 `http://<host>:5173`

**8) Vite CLI 报 `Unknown option --https`**
- 现象：`vite --https` 启动失败
- 原因：Vite CLI 不支持该参数
- 修复：在 `vite.config` 中配置 `server.https`，或移除 `--https` 改用反向代理提供 HTTPS。

## 📊 性能参考

| 指标 | 数值 |
|--------|-------|
| 单图 | ~25s |
| 并行处理 | ~11s/张 |
| OCR 检测 | ~8s |
| AI 翻译 | ~2s（批量） |
| 擦除 + 渲染 | ~15s |

## 🏗️ 项目结构

```
manhua/
├── main.py                 # CLI 入口
├── app/
│   ├── main.py             # FastAPI 服务
│   └── routes/             # API 路由
├── core/
│   ├── pipeline.py         # 处理管线
│   ├── ai_translator.py    # AI 翻译器（PPIO/Gemini）
│   ├── modules/            # 处理模块
│   │   ├── ocr.py          # OCR 模块
│   │   ├── translator.py   # 翻译模块
│   │   ├── inpainter.py    # 擦除模块
│   │   └── renderer.py     # 渲染模块
│   └── vision/
│       ├── ocr/            # PaddleOCR 引擎
│       └── inpainter.py    # LaMa 擦除器
├── scraper/                # 漫画下载器
├── frontend/               # Vue 3 Web UI
└── requirements.txt
```

## 🔧 处理流程

```
Image → OCR → Region Grouping → Translation → Inpainting → Rendering → Output
```

1. **OCR** - 使用 PaddleOCR 检测文本区域
2. **分组** - 合并相邻文本行
3. **翻译** - AI 批量翻译
4. **擦除** - LaMa 去除原文
5. **渲染** - 绘制译文并适配样式

## 🌐 Web 界面

服务启动后访问：`http://localhost:8000`

功能：
- 漫画库管理
- 章节翻译与进度
- 内置爬虫
- 左右对比视图

### Scraper 认证浏览器（Docker）

如需在手机上通过 Cloudflare 验证，可在服务器上运行远程浏览器，然后手机访问。

1) 启动认证浏览器服务：

```bash
docker compose -f docker-compose.auth.yml up -d
```

2) 打开服务器 `3000` 端口并设置认证地址：

```
SCRAPER_AUTH_URL=http://<server-ip>:3000/
```

3) 在爬虫页点击“打开认证页”完成验证，然后返回点击“检测状态”。

注意事项：
- docker compose 会将 `./data/toongod_profile` 挂载为浏览器 profile，请保持与爬虫设置一致。
- 如果使用 MangaForFree，请将卷改为 `./data/mangaforfree_profile:/config`。

## 📄 许可证

MIT License
