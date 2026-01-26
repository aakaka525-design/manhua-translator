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

# Frontend (optional, for development)
cd frontend && npm install
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

## 📄 License

MIT License
