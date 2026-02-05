import asyncio
import inspect

import pytest


@pytest.fixture(autouse=True)
def _reset_settings_overrides():
    """Ensure settings overrides do not leak between tests."""
    try:
        from app.routes import settings as settings_route

        settings_route._model_override = None
        settings_route._upscale_model_override = None
        settings_route._upscale_scale_override = None
    except Exception:
        pass
    yield
    try:
        from app.routes import settings as settings_route

        settings_route._model_override = None
        settings_route._upscale_model_override = None
        settings_route._upscale_scale_override = None
    except Exception:
        pass


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
