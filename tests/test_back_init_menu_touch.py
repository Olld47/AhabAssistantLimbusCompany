"""回归测试：返回主界面（back_init_menu）在触摸端的最后手段。

键盘端最后手段是按 ESC 打开暂停/设置浮层；触摸端（PlayCover/MaaTools 的 ``key_press``
是空实现）原来在这一步完全空转，只能等 ``loop_count`` 耗尽后重启游戏。现在改为点界面上
的设置/返回入口 —— 尤其是 ``mirror/road_in_mir/setting_assets.png``：它在主循环前面的
点击被 ``legend_assets.png`` 识别门控，识别抖动时会漏掉。
"""

import pytest

from tasks.base import back_init_menu as back_init_menu_module

MIRROR_SETTING = "mirror/road_in_mir/setting_assets.png"
WINDOW = "home/window_assets.png"
MAIL = "home/mail_assets.png"


class LoopDetected(RuntimeError):
    """界面一直没推进，说明最后手段没有生效。"""


class FakeDevice:
    MAX_ITERATIONS = 20

    def __init__(self, *, supports_keyboard: bool):
        self.supports_keyboard = supports_keyboard
        self.model = "clam"
        self.escaped = False
        self.iterations = 0
        self.setting_clicks = 0
        self.key_presses = []

    def _tick(self):
        self.iterations += 1
        if self.iterations > self.MAX_ITERATIONS:
            raise LoopDetected("界面未推进，back_init_menu 空转")

    def click_element(self, target, *args, **kwargs):
        self._tick()
        if target == MIRROR_SETTING:
            self.setting_clicks += 1
            self.escaped = True  # 浮层打开，主界面随后可识别
            return True
        if target == WINDOW:
            return self.escaped
        return False

    def find_element(self, target, *args, **kwargs):
        if target == MAIL:
            return (100, 100) if self.escaped else None
        return None

    def mouse_click_blank(self, *args, **kwargs):
        return True

    def key_press(self, key):
        self.key_presses.append(key)
        if self.supports_keyboard:
            self.escaped = True  # ESC 打开浮层


@pytest.fixture
def run_back_init_menu(monkeypatch):
    def _run(*, supports_keyboard: bool):
        device = FakeDevice(supports_keyboard=supports_keyboard)
        monkeypatch.setattr(back_init_menu_module, "auto", device)
        monkeypatch.setattr(back_init_menu_module, "ensure_simulator_game_started", lambda: False)
        monkeypatch.setattr(back_init_menu_module, "retry", lambda: True)
        monkeypatch.setattr(back_init_menu_module, "update_model_for_retry", lambda *a, **k: None)
        assert back_init_menu_module.back_init_menu() is True
        return device

    return _run


def test_touch_device_clicks_setting_entry_instead_of_escape(run_back_init_menu):
    """键盘无效：最后手段点界面设置入口，不按 ESC，且不死循环。"""
    device = run_back_init_menu(supports_keyboard=False)

    assert device.setting_clicks == 1
    assert device.key_presses == []


def test_keyboard_device_still_uses_escape(run_back_init_menu):
    """键盘可用：最后手段仍按 ESC，不点界面入口（Windows 行为不变）。"""
    device = run_back_init_menu(supports_keyboard=True)

    assert device.key_presses == ["esc"]
    assert device.setting_clicks == 0
