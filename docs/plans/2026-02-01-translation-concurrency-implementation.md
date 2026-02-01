# Translation Batch Concurrency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 `AITranslator.translate_batch` 内部实现受限并发分片调用，降低整体翻译耗时且保持调用接口不变。

**Architecture:** 以 `valid_pairs` 为基础做分片，每片构造独立 prompt 并调用 `_call_api`，用 `asyncio.Semaphore` 控制并发，最后按原索引合并结果。保持原有解析与重试逻辑。

**Tech Stack:** Python 3.12, asyncio, pytest

### Task 1: 为分片并发添加回归测试

**Files:**
- Modify: `tests/test_ai_translator.py`

**Step 1: Write the failing test**

```python

def test_translate_batch_chunks_and_merges(monkeypatch):
    monkeypatch.setenv("PPIO_API_KEY", "dummy")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_CHUNK_SIZE", "2")
    monkeypatch.setenv("AI_TRANSLATE_BATCH_CONCURRENCY", "8")

    from core.ai_translator import AITranslator

    monkeypatch.setattr(AITranslator, "_init_ppio", lambda self: None)

    translator = AITranslator(model="glm-4-flash-250414", source_lang="en", target_lang="zh")
    calls = {"count": 0}

    async def fake_call_api(prompt: str, max_tokens: int = 2000) -> str:
        calls["count"] += 1
        import re
        lines = re.findall(r"^\d+\.\s+(?:TEXT:\s*)?(.*)$", prompt, flags=re.MULTILINE)
        outputs = [f"{i + 1}. OUT:{line.strip()}" for i, line in enumerate(lines)]
        return "\n".join(outputs)

    monkeypatch.setattr(translator, "_call_api", fake_call_api)

    texts = ["A", "B", "C", "D", "E"]
    result = asyncio.run(translator.translate_batch(texts))

    assert calls["count"] == 3
    assert result == [f"OUT:{t}" for t in texts]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_translator.py::test_translate_batch_chunks_and_merges -v`
Expected: FAIL (calls count remains 1)

### Task 2: 在 translate_batch 内实现分片并发

**Files:**
- Modify: `core/ai_translator.py`

**Step 1: Write minimal implementation**

- 读取环境变量：`AI_TRANSLATE_BATCH_CHUNK_SIZE`、`AI_TRANSLATE_BATCH_CONCURRENCY`（默认 8，<1 则回退到默认）。
- 将 `valid_pairs` 分片；当分片数为 1 时走现有单次调用路径。
- 当分片数 >1 时：
  - 用 `asyncio.Semaphore` 控制并发。
  - 每片复用原 prompt/解析/重试逻辑，返回 `(orig_idx, translation)` 映射。
  - 合并到 `full_results`（保持原索引顺序）。
- 日志中增加 slice 信息（可选）：`slice i/n`。

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_ai_translator.py::test_translate_batch_chunks_and_merges -v`
Expected: PASS

### Task 3: 运行最小回归测试并提交

**Files:**
- Modify: `tests/test_ai_translator.py`
- Modify: `core/ai_translator.py`

**Step 1: Run targeted tests**

Run: `pytest tests/test_ai_translator.py -v`
Expected: PASS

**Step 2: Commit**

```bash
git add tests/test_ai_translator.py core/ai_translator.py
git commit -m "feat: add concurrent chunking for translate_batch"
```

