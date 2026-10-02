from unittest.mock import patch

from module.automation import auto
from module.macos.window import window
from module.macos.bootstrap import apply_mac_configuration


def _set_input_type(value):
    """只改写 win_input_type，避免污染其他配置项（如 simulator）的读取。"""
    from module.config import cfg

    original = cfg.get_value

    def get_value(key, default=None, **kwargs):
        if key == "win_input_type":
            return value
        if key == "simulator":
            return False
        return original(key, default, **kwargs)

    return patch.object(cfg, "get_value", side_effect=get_value)


def test_background_choice_selects_driver_without_forcing_foreground():
    from module.automation.input_handlers.macos.background_input import BackgroundInput

    with _set_input_type("background"):
        auto.init_input()
    try:
        assert isinstance(auto.input_handler, BackgroundInput)
        assert window.background is True
    finally:
        with _set_input_type("foreground"):
            auto.init_input()
    assert window.background is False


def test_platform_configuration_preserves_selected_mode():
    class Config:
        def __init__(self):
            self.values = {'win_input_type': 'background'}

        def unsaved_set_value(self, key, value):
            self.values[key] = value

    config = Config()
    apply_mac_configuration(config)
    assert config.values['win_input_type'] == 'background'
