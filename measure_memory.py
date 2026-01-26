"""
内存测量脚本 - 测量各个核心模块的内存占用。

测量指标：
- 初始内存
- 模型加载后内存
- 推理/处理时的峰值内存
"""

import os
# 抑制日志
os.environ["PADDLE_PDX_LOG_LEVEL"] = "ERROR"
os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_log_level"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"

import asyncio
import gc
import psutil
import time
import warnings
from pathlib import Path

# 抑制警告
warnings.filterwarnings("ignore")

# 获取当前进程
process = psutil.Process(os.getpid())

def get_memory_mb():
    """获取当前进程的 RSS 内存 (MB)。"""
    return process.memory_info().rss / 1024 / 1024

async def measure_module(name: str, measure_func):
    """
    测量指定模块的内存占用。
    
    Args:
        name: 模块名称
        measure_func: 异步测量函数，接受 (baseline_mem) 参数
    """
    print(f"\n[{name}] 测量开始...")
    gc.collect()
    time.sleep(1)
    baseline = get_memory_mb()
    print(f"  基准内存: {baseline:.2f} MB")
    
    start_time = time.time()
    try:
        peak_mem, loaded_mem = await measure_func(baseline)
        
        print(f"  加载后内存: {loaded_mem:.2f} MB (+{loaded_mem - baseline:.2f} MB)")
        print(f"  峰值内存: {peak_mem:.2f} MB")
        print(f"  耗时: {time.time() - start_time:.2f}s")
        
        return {
            "module": name,
            "baseline": baseline,
            "loaded": loaded_mem,
            "peak": peak_mem,
            "increase": loaded_mem - baseline
        }
    except Exception as e:
        print(f"  ❌ 测量失败: {e}")
        return None

# === 测量函数 ===

async def measure_ocr(baseline):
    from core.vision.ocr_engine import get_cached_ocr
    
    # 模拟加载
    print("  正在加载模型...")
    ocr = get_cached_ocr()
    loaded_mem = get_memory_mb()
    
    # 模拟推理
    print("  正在推理测试...")
    test_img = "test_img/chapter_98/001.jpg"
    if Path(test_img).exists():
        ocr.ocr(test_img)  # 移除 cls=True，因为默认就是开启的或者参数名不同
    
    peak_mem = get_memory_mb()
    return peak_mem, loaded_mem

async def measure_inpainter(baseline):
    from core.vision.inpainter import LamaInpainter
    
    print("  正在加载模型...")
    inpainter = LamaInpainter() 
    # 触发加载
    test_img = "test_img/chapter_98/001.jpg"
    if Path(test_img).exists():
        print("  正在推理测试 (触发加载)...")
        # 造一些假数据触发加载
        import cv2
        import numpy as np
        img = cv2.imread(test_img)
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        # 画一个框
        mask[100:200, 100:200] = 255
        
        # 定义一个简单的 RegionData
        from core.models import RegionData, Box2D
        region = RegionData(id="1", box=Box2D(x1=100, y1=100, x2=200, y2=200), text="test")
        
        # 调用 inpaint_regions 触发加载
        await inpainter.inpaint_regions(test_img, [region], "temp_out.png", "temp_debug")
        if Path("temp_out.png").exists():
            Path("temp_out.png").unlink()
        
    loaded_mem = get_memory_mb()
    peak_mem = loaded_mem
    return peak_mem, loaded_mem

async def measure_translator(baseline):
    from core.ai_translator import AITranslator
    
    print("  正在初始化...")
    translator = AITranslator()
    loaded_mem = get_memory_mb()
    
    print("  正在调用 API...")
    await translator.translate_batch(["Hello world"])
    
    peak_mem = get_memory_mb()
    return peak_mem, loaded_mem

# === 主流程 ===

async def main():
    print("=== 漫画翻译器内存测量 ===")
    print(f"PID: {os.getpid()}")
    
    results = []
    
    # 1. 测量 OCR
    res = await measure_module("PaddleOCR", measure_ocr)
    if res: results.append(res)
    
    # 清理
    import core.vision.ocr_engine as ocr_module
    ocr_module._ocr_cache = {}
    gc.collect()
    
    # 2. 测量 Inpainter (LaMa)
    # 重启个进程可能更准，但这里先尽量模拟
    res = await measure_module("LaMa Inpainter", measure_inpainter)
    if res: results.append(res)
    
    # 3. 测量 AI Translator
    res = await measure_module("AI Translator", measure_translator)
    if res: results.append(res)
    
    print("\n\n=== 测量总结 ===")
    print(f"{'模块':<20} | {'增量 (MB)':<12} | {'总占用 (MB)':<12}")
    print("-" * 50)
    for r in results:
        print(f"{r['module']:<20} | {r['increase']:<12.1f} | {r['loaded']:<12.1f}")

if __name__ == "__main__":
    asyncio.run(main())
