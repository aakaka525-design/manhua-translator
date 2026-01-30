import asyncio
import inspect


def pytest_pyfunc_call(pyfuncitem):
    """Run async tests marked with pytest.mark.asyncio without external plugins."""
    if "asyncio" not in pyfuncitem.keywords:
        return None
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(pyfuncitem.obj(**pyfuncitem.funcargs))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
    return True
