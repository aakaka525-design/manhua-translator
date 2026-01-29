import importlib.util
import warnings

from pydantic.warnings import PydanticDeprecatedSince20


def _collect_pydantic_deprecation_warnings(module_name: str) -> list[warnings.WarningMessage]:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    isolated_name = f"_pydantic_check_{module_name.replace('.', '_')}"
    isolated_spec = importlib.util.spec_from_file_location(isolated_name, spec.origin)
    assert isolated_spec is not None and isolated_spec.loader is not None
    module = importlib.util.module_from_spec(isolated_spec)
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", PydanticDeprecatedSince20)
        isolated_spec.loader.exec_module(module)
    return [
        warning for warning in recorded if issubclass(warning.category, PydanticDeprecatedSince20)
    ]


def test_core_models_no_pydantic_deprecation_warnings():
    warnings_list = _collect_pydantic_deprecation_warnings("core.models")
    assert not warnings_list


def test_app_deps_no_pydantic_deprecation_warnings():
    warnings_list = _collect_pydantic_deprecation_warnings("app.deps")
    assert not warnings_list
