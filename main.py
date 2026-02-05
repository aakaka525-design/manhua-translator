#!/usr/bin/env python3
"""
漫画翻译器 - 主程序入口

功能：
- 自动检测漫画中的文字 (PaddleOCR)
- AI 翻译 (PPIO GLM API)
- 智能擦除和重绘 (LaMa)
- 并行处理加速

用法：
    # 翻译单张图片
    python main.py image <图片路径> [--output 输出目录]
    
    # 翻译整章（并行处理）
    python main.py chapter <输入目录> <输出目录> [--workers 并发数]
    
    # 启动 Web 服务
    python main.py server [--port 8000]
"""

import os
import sys
import warnings

# 抑制日志噪音（必须在其他导入之前设置）
os.environ["PADDLE_PDX_LOG_LEVEL"] = "ERROR"
os.environ["GLOG_minloglevel"] = "3"  # 抑制 PaddlePaddle C++ 日志
os.environ["FLAGS_log_level"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"  # 跳过模型连接检查
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import argparse
import asyncio
from pathlib import Path


def translate_image_cmd(args):
    """翻译单张图片"""
    from core.pipeline import translate_image
    # 注意：OCR 缓存由 ocr_engine 模块自动管理，无需手动清空
    
    async def run():
        print(f"翻译图片: {args.image}")
        result = await translate_image(
            args.image,
            args.source,
            args.target,
            verbose=True
        )
        
        if result.success:
            # 移动到指定输出目录
            if args.output:
                import shutil
                output_dir = Path(args.output)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_name = f"{Path(args.image).stem}_translated.png"
                output_path = output_dir / output_name
                shutil.move(result.task.output_path, output_path)
                print(f"\n✅ 完成: {output_path}")
            else:
                print(f"\n✅ 完成: {result.task.output_path}")
        else:
            print("\n❌ 翻译失败")
            sys.exit(1)
    
    asyncio.run(run())


def translate_chapter_cmd(args):
    """翻译整章（并行处理）"""
    from batch_translate import translate_chapter
    
    asyncio.run(translate_chapter(
        args.input_dir,
        args.output_dir,
        source_lang=args.source,
        target_lang=args.target,
        max_concurrent=args.workers,
        verbose=True,
    ))


def server_cmd(args):
    """启动 Web 服务"""
    import uvicorn
    from app.main import app
    from app.deps import get_settings
    
    settings = get_settings()
    host = settings.host if hasattr(settings, 'host') else "0.0.0.0"
    port = args.port or settings.port
    
    print(f"启动服务: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


def main():
    parser = argparse.ArgumentParser(
        description="漫画翻译器 - 自动翻译漫画中的文字",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py image test.jpg                    # 翻译单张图片
  python main.py image test.jpg -o output/         # 指定输出目录
  python main.py chapter input/ output/ -w 3       # 并行翻译整章
  python main.py server --port 8000                # 启动 Web 服务
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # image 子命令
    image_parser = subparsers.add_parser("image", help="翻译单张图片")
    image_parser.add_argument("image", help="图片路径")
    image_parser.add_argument("-o", "--output", help="输出目录")
    image_parser.add_argument("-s", "--source", default="en", help="源语言 (默认: en)")
    image_parser.add_argument("-t", "--target", default="zh-CN", help="目标语言 (默认: zh-CN)")
    image_parser.set_defaults(func=translate_image_cmd)
    
    # chapter 子命令
    chapter_parser = subparsers.add_parser("chapter", help="翻译整章（并行处理）")
    chapter_parser.add_argument("input_dir", help="输入目录")
    chapter_parser.add_argument("output_dir", help="输出目录")
    chapter_parser.add_argument("-w", "--workers", type=int, default=3, help="并发数 (默认: 3)")
    chapter_parser.add_argument("-s", "--source", default="en", help="源语言 (默认: en)")
    chapter_parser.add_argument("-t", "--target", default="zh-CN", help="目标语言 (默认: zh-CN)")
    chapter_parser.set_defaults(func=translate_chapter_cmd)
    
    # server 子命令
    server_parser = subparsers.add_parser("server", help="启动 Web 服务")
    server_parser.add_argument("-p", "--port", type=int, default=8000, help="端口号 (默认: 8000)")
    server_parser.set_defaults(func=server_cmd)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
