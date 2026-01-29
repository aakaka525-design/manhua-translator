# Manga Translator

Automatically translate manga/manhwa text with OCR, AI translation, and smart inpainting.

## ✨ Features

- **Multi-language OCR** - PaddleOCR v5 with Korean, Japanese, English, Chinese support
- **AI Translation** - PPIO GLM / Google Gemini for high-quality translations
- **Smart Inpainting** - LaMa model removes original text seamlessly
- **Auto Typography** - Dynamic font sizing to fit speech bubbles
- **Web Scraper** - Built-in manga/manhwa downloader
- **Web UI** - Modern Vue 3 interface for easy operation

## 🚀 Quick Start

### Installation

```bash
# Backend dependencies
pip install -r requirements.txt

# CPU-only OCR stack (Linux servers)
pip install -r requirements-cpu.txt

# Frontend (optional, for development)
cd frontend && npm install
```

### Linux (CPU) system dependencies

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

### Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```env
# PPIO GLM API (primary)
PPIO_API_KEY=your_ppio_api_key
PPIO_BASE_URL=https://api.ppio.com/openai
PPIO_MODEL=zai-org/glm-4.7-flash

# Google Gemini API (alternative)
GEMINI_API_KEY=your_gemini_api_key

# Translation settings
SOURCE_LANGUAGE=korean
TARGET_LANGUAGE=zh
```

**Model selection notes**
- All AI models are selected via `PPIO_MODEL`.
- Use a PPIO model name (e.g. `zai-org/glm-4.7-flash`) for PPIO.
- Use a Gemini model name (e.g. `gemini-2.5-flash`) to switch to Gemini (requires `GEMINI_API_KEY`).
- If the model name contains `gemini-`, the system automatically routes requests to Gemini.

**OCR & Inpainting models**
- OCR detector: `PP-OCRv5_mobile_det`
- OCR recognizer:
  - English: `en_PP-OCRv5_mobile_rec`
  - Korean: `korean_PP-OCRv5_mobile_rec`
- Inpainting: LaMa (used by `core/modules/inpainter.py`)

### Usage

```bash
# Start web server (recommended)
python main.py server --port 8000

# Translate single image
python main.py image test.jpg -o output/

# Translate chapter (parallel processing)
python main.py chapter input/ output/ -w 3
```

## 📊 Performance

| Metric | Value |
|--------|-------|
| Single image | ~25s |
| Parallel processing | ~11s/image |
| OCR detection | ~8s |
| AI translation | ~2s (batch) |
| Inpainting + Render | ~15s |

## 🏗️ Project Structure

```
manhua/
├── main.py                 # CLI entry point
├── app/
│   ├── main.py             # FastAPI server
│   └── routes/             # API routes
├── core/
│   ├── pipeline.py         # Processing pipeline
│   ├── ai_translator.py    # AI translator (PPIO/Gemini)
│   ├── modules/            # Pipeline modules
│   │   ├── ocr.py          # OCR module
│   │   ├── translator.py   # Translation module
│   │   ├── inpainter.py    # Inpainting module
│   │   └── renderer.py     # Text rendering
│   └── vision/
│       ├── ocr/            # PaddleOCR engine
│       └── inpainter.py    # LaMa inpainter
├── scraper/                # Manga/manhwa downloader
├── frontend/               # Vue 3 web UI
└── requirements.txt
```

## 🔧 Pipeline

```
Image → OCR → Region Grouping → Translation → Inpainting → Rendering → Output
```

1. **OCR** - Detect text regions with PaddleOCR
2. **Grouping** - Merge adjacent text lines
3. **Translation** - Batch translate with AI
4. **Inpainting** - Remove original text with LaMa
5. **Rendering** - Render translated text with proper styling

## 🌐 Web Interface

Access at `http://localhost:8000` after starting the server.

Features:
- Manga library management
- Chapter translation with progress tracking
- Built-in manga scraper
- Side-by-side comparison view

### Scraper Auth Browser (Docker)

If you need to complete Cloudflare challenges from a phone, run a remote browser on the server and open it from mobile.

1) Start the auth browser service:

```bash
docker compose -f docker-compose.auth.yml up -d
```

2) Open port `3000` on the server and set auth URL:

```
SCRAPER_AUTH_URL=http://<server-ip>:3000/
```

3) In the scraper page, click “打开认证页” to complete the challenge, then return and click “检测状态”.

Notes:
- The docker compose mounts `./data/toongod_profile` as the browser profile. Keep this path consistent with the scraper settings.
- To use MangaForFree, change the volume to `./data/mangaforfree_profile:/config`.

## 📄 License

MIT License
