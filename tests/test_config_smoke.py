from pathlib import Path


def test_model_source_flag_name():
    content = Path("main.py").read_text(encoding="utf-8")
    assert "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK" in content
    assert 'os.environ["DISABLE_MODEL_SOURCE_CHECK"]' not in content


def test_model_warmup_timeout_removed():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "MODEL_WARMUP_TIMEOUT" not in compose
    assert "MODEL_WARMUP_TIMEOUT" not in readme


def test_compose_paddle_flags_removed():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "FLAGS_use_mkldnn" not in compose
    assert "FLAGS_use_pir_api" not in compose
