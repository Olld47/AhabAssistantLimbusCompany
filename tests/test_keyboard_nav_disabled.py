"""关闭键盘寻路后，任何平台都不应再走键盘寻路。

线上问题：mirror_keyboard_navigation 已设为 False，PlayCover 模式下日志仍
持续出现「通过键盘按键寻路」。

根因有两处：
1. enter_next_node 的条件写成
       cfg.mirror_keyboard_navigation and auto.supports_key("up") or _macos_background()
   Python 中 and 优先级高于 or，等价于
       (A and B) or C
   于是只要 _macos_background() 为真，键盘寻路就被强制打开；
2. _macos_background() 只判断「darwin + background_click」，没有排除模拟器。
   PlayCover 模式下 background_click 为 True，函数恒为 True，条件 1 因此
   总是命中——即使在 PlayCover 上根本没有对应的按键投递路径。
"""

import sys
from unittest.mock import patch

import pytest

from tasks.mirror import search_road as road


def _config(simulator: bool):
    """构造配置读取：模拟器/后台开关按下述取值，键盘寻路明确关闭。"""
    values = {
        "simulator": simulator,
        "background_click": True,
        "mirror_keyboard_navigation": False,
        "set_win_size": 1080,
    }
    return lambda key, default=None: values.get(key, default)


def _run_enter_next_node(monkeypatch, simulator):
    """跑一次 enter_next_node，返回是否发生了按键调用。"""
    key_calls = []
    click_calls = []
    mirror_map = road.MirrorMap()

    monkeypatch.setattr(road.cfg, "get_value", _config(simulator))
    monkeypatch.setattr(road.cfg, "mirror_keyboard_navigation", False, raising=False)
    monkeypatch.setattr(road.auto, "supports_key", lambda _k: True, raising=False)
    monkeypatch.setattr(road.auto, "key_press", lambda k: key_calls.append(k), raising=False)
    monkeypatch.setattr(
        road.auto, "mouse_click", lambda x, y: click_calls.append((x, y)), raising=False
    )
    monkeypatch.setattr(road.auto, "click_element", lambda *a, **k: False, raising=False)
    monkeypatch.setattr(road, "_keyboard_enter_succeeded", lambda: False, raising=False)
    monkeypatch.setattr(road, "sleep", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        mirror_map, "_get_next_position", lambda direction: (500, 500), raising=False
    )

    mirror_map.enter_next_node("M")
    return key_calls, click_calls


@pytest.mark.skipif(sys.platform != "darwin", reason="该兜底逻辑只在 macOS 生效")
def test_playcover_does_not_use_keyboard_pathfinding_when_disabled(monkeypatch):
    """PlayCover（模拟器）不是 CrossOver 后台，不能触发键盘寻路兜底。"""
    key_calls, click_calls = _run_enter_next_node(monkeypatch, simulator=True)

    assert not key_calls, f"键盘寻路已关闭，却仍按下了 {key_calls}"
    assert click_calls, "应走点击寻路"


@pytest.mark.skipif(sys.platform != "darwin", reason="该兜底逻辑只在 macOS 生效")
def test_macos_background_excludes_simulator(monkeypatch):
    """_macos_background() 只代表 CrossOver 桌面后台，模拟器必须排除。"""
    monkeypatch.setattr(road.cfg, "get_value", _config(simulator=True))
    assert road._macos_background() is False

    monkeypatch.setattr(road.cfg, "get_value", _config(simulator=False))
    assert road._macos_background() is True


def test_keyboard_requires_explicit_switch(monkeypatch):
    """键盘开关关闭时，即使 supports_key 与后台兜底都成立，也不得走键盘。"""
    key_calls, _ = _run_enter_next_node(monkeypatch, simulator=False)
    assert not key_calls, "键盘寻路开关已关闭，不应按键"
