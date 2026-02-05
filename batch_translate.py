"""
并行批量翻译 - 同时处理多张图片加速翻译。

使用 asyncio 并发处理多张图片，减少总耗时。
"""

import asyncio
import os
import shutil
import time
from pathlib import Path


async def translate_chapter(
    input_dir: str,
    output_dir: str,
    source_lang: str = "en",
    target_lang: str = "zh-CN",
    max_concurrent: int = 3,
    verbose: bool = True,
):
    """
    并行翻译整章图片。
    
    Args:
        input_dir: 输入目录（包含 jpg/png 图片）
        output_dir: 输出目录
        source_lang: 源语言
        target_lang: 目标语言
        max_concurrent: 最大并发数（建议 2-3，避免 API 限流）
        verbose: 显示详细进度
    
    Returns:
        dict: 统计信息
    """
    from core.pipeline import translate_image
        # 注意：OCR 缓存由 core.vision.ocr 自动管理，无需手动清空
    
    # 创建输出目录（安全处理，不自动删除已有内容）
    output_path = Path(output_dir)
    if output_path.exists() and any(output_path.iterdir()):
        if verbose:
            print(f"⚠️  输出目录已存在且非空: {output_dir}")
            print(f"   将在该目录下创建/覆盖翻译文件")
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 获取图片列表
    input_path = Path(input_dir)
    images = sorted([
        f for f in input_path.iterdir() 
        if f.suffix.lower() in ['.jpg', '.jpeg', '.png']
    ])
    
    total = len(images)
    if verbose:
        print(f"=== 并行翻译 (最大并发: {max_concurrent}) ===")
        print(f"输入: {input_dir}")
        print(f"输出: {output_dir}")
        print(f"图片数: {total}")
        print()
    
    # 统计
    results = {
        "success": 0,
        "failed": 0,
        "total_regions": 0,
        "total_sfx": 0,
    }
    completed = 0
    lock = asyncio.Lock()
    
    async def process_image(img_path: Path):
        nonlocal completed
        
        start = time.time()
        try:
            result = await translate_image(
                str(img_path), 
                source_lang, 
                target_lang, 
                verbose=False
            )
            
            if result.success:
                # 移动输出文件
                output_name = f"{img_path.stem}_translated.png"
                shutil.move(result.task.output_path, output_path / output_name)
                
                elapsed = time.time() - start
                regions = len(result.task.regions)
                sfx = sum(1 for r in result.task.regions 
                         if r.target_text and r.target_text.startswith('[SFX:'))
                
                async with lock:
                    results["success"] += 1
                    results["total_regions"] += regions
                    results["total_sfx"] += sfx
                    completed += 1
                    
                    if verbose:
                        print(f"[{completed:02d}/{total}] ✅ {img_path.name} - {elapsed:.1f}s ({regions} 区域)")
                
                return True
            else:
                async with lock:
                    results["failed"] += 1
                    completed += 1
                    if verbose:
                        print(f"[{completed:02d}/{total}] ❌ {img_path.name} - 失败")
                return False
                
        except Exception as e:
            async with lock:
                results["failed"] += 1
                completed += 1
                if verbose:
                    print(f"[{completed:02d}/{total}] ❌ {img_path.name} - {str(e)[:30]}")
            return False
    
    # 使用信号量限制并发
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_limit(img_path):
        async with semaphore:
            return await process_image(img_path)
    
    # 并行处理
    total_start = time.time()
    await asyncio.gather(*[process_with_limit(img) for img in images])
    total_elapsed = time.time() - total_start
    
    if verbose:
        print()
        print(f"=== 完成 ===")
        print(f"成功: {results['success']}, 失败: {results['failed']}")
        print(f"总区域: {results['total_regions']}, 总 SFX: {results['total_sfx']}")
        print(f"总耗时: {total_elapsed:.1f}s ({total_elapsed/total:.1f}s/张)")
        print(f"输出: {output_dir}")
    
    results["total_time"] = total_elapsed
    results["avg_time"] = total_elapsed / total if total > 0 else 0
    
    return results


# CLI 入口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("用法: python batch_translate.py <输入目录> <输出目录> [并发数]")
        print("示例: python batch_translate.py test_img/chapter_98 output/chapter_98_v3 3")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    max_concurrent = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    
    asyncio.run(translate_chapter(input_dir, output_dir, max_concurrent=max_concurrent))
