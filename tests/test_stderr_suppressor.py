from core.utils.stderr_suppressor import suppress_native_stderr


def test_suppress_native_stderr_context_manager():
    with suppress_native_stderr():
        assert True
