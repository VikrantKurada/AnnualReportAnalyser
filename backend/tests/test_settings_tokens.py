from app import db, settings, tokens


def make_conn(tmp_path):
    conn = db.get_conn(tmp_path / "t.db")
    db.init_db(conn)
    return conn


def test_defaults_returned_when_unset(tmp_path):
    conn = make_conn(tmp_path)
    assert settings.get_setting(conn, "llm_provider") == "ollama"
    assert settings.get_setting(conn, "embed_model") == "nomic-embed-text"


def test_set_and_get_roundtrip(tmp_path):
    conn = make_conn(tmp_path)
    settings.set_setting(conn, "llm_provider", "anthropic")
    assert settings.get_setting(conn, "llm_provider") == "anthropic"


def test_masked_settings_hides_keys(tmp_path):
    conn = make_conn(tmp_path)
    settings.set_setting(conn, "openai_api_key", "sk-secret123")
    masked = settings.masked_settings(conn)
    assert masked["openai_api_key"] == settings.MASK
    assert "sk-secret123" not in str(masked)
    # unset keys stay empty, not masked
    assert masked["nvidia_api_key"] == ""


def test_update_settings_ignores_mask_placeholder(tmp_path):
    conn = make_conn(tmp_path)
    settings.set_setting(conn, "openai_api_key", "sk-secret123")
    settings.update_settings(conn, {"openai_api_key": settings.MASK, "llm_model": "gpt-x"})
    assert settings.get_setting(conn, "openai_api_key") == "sk-secret123"
    assert settings.get_setting(conn, "llm_model") == "gpt-x"


def test_token_recording_and_totals(tmp_path):
    conn = make_conn(tmp_path)
    tokens.record_usage(conn, "sess1", "ollama", "glm", 100, 50, "chat")
    tokens.record_usage(conn, "sess1", "ollama", "glm", 10, 5, "analysis")
    tokens.record_usage(conn, "sess2", "openai", "gpt", 7, 3, "chat")
    t = tokens.session_totals(conn, "sess1")
    assert t["input_tokens"] == 110
    assert t["output_tokens"] == 55
    assert t["calls"] == 2
    everything = tokens.totals_all(conn)
    assert everything["input_tokens"] == 117
