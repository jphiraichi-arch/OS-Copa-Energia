import pytest

from osapp.config import ConfigError, carregar_config

URL = "sqlite:///./teste.db"


def test_database_url_ausente_gera_erro_claro():
    with pytest.raises(ConfigError, match="OS_DATABASE_URL"):
        carregar_config({})


def test_database_url_vazia_gera_erro_claro():
    with pytest.raises(ConfigError, match="OS_DATABASE_URL"):
        carregar_config({"OS_DATABASE_URL": "   "})


def test_database_url_ausente_no_ambiente_real(monkeypatch, tmp_path):
    monkeypatch.delenv("OS_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # sem .env por perto
    monkeypatch.setattr("osapp.config.load_dotenv", lambda *a, **k: False)
    with pytest.raises(ConfigError, match="OS_DATABASE_URL"):
        carregar_config()


def test_padroes():
    config = carregar_config({"OS_DATABASE_URL": URL})
    assert config.database_url == URL
    assert config.tz == "America/Sao_Paulo"
    assert config.sessao_timeout_min == 30
    assert config.log_level == "INFO"


def test_valores_informados():
    config = carregar_config(
        {
            "OS_DATABASE_URL": URL,
            "OS_TZ": "America/Manaus",
            "OS_SESSAO_TIMEOUT_MIN": "45",
            "OS_LOG_LEVEL": "debug",
        }
    )
    assert (config.tz, config.sessao_timeout_min, config.log_level) == (
        "America/Manaus",
        45,
        "DEBUG",
    )


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("OS_TZ", "Marte/Olympus"),
        ("OS_SESSAO_TIMEOUT_MIN", "abc"),
        ("OS_SESSAO_TIMEOUT_MIN", "0"),
        ("OS_LOG_LEVEL", "VERBOSO"),
    ],
)
def test_valores_invalidos(variavel, valor):
    with pytest.raises(ConfigError, match=variavel):
        carregar_config({"OS_DATABASE_URL": URL, variavel: valor})


def test_repr_nao_expoe_a_url():
    config = carregar_config({"OS_DATABASE_URL": "postgresql://u:segredo@h/db"})
    assert "segredo" not in repr(config)
    assert "segredo" not in str(config)
