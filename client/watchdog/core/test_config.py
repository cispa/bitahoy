from watchdog.core.config import Config


def test_config_path_resolved():
    config = Config()
    config.config = {"test": "test"}
    assert config.get("test") == "test"
    assert config.get(["test"]) == "test"


def test_config_priority_lookup():
    config = Config()
    config.config = {"test": {"test": "test1"}, "test.test": "test2", "test1": "test3"}
    assert config.get("test") == {"test": "test1"}
    assert config.get(["test"]) == {"test": "test1"}
    assert config.get(["test", "test"]) == "test1"
    assert config.get(["test.test"]) == "test2"
    assert config.get(["test1"]) == "test3"
