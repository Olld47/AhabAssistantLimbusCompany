"""macOS 启动时不能悄悄覆盖用户可配置的开关。

线上问题：上次在设置里打开了「使用模拟器」，下次启动后又变回关闭。

原因：apply_mac_configuration() 把 simulator 当作"平台不变量"强制写死为
False。这条规则来自只支持 CrossOver 的旧 mac 分支；合并后 PlayCover 已是
macOS 上受支持的路径（走触摸输入，代码里有完整分支），继续强制关闭就等于
每次启动都撤销用户的选择。
"""

from unittest.mock import patch

import pytest

from module.macos.bootstrap import apply_mac_configuration


class _FakeCfg:
    """最小配置替身：支持读写，行为与 Config 的对应方法一致。"""

    def __init__(self, **values):
        self.values = dict(values)

    def get_value(self, key, default=None):
        return self.values.get(key, default)

    def unsaved_set_value(self, key, value):
        self.values[key] = value


@pytest.mark.parametrize("enabled", [True, False])
def test_simulator_setting_is_preserved(enabled):
    """模扠器开关是用户偏好，启动时不得改写。"""
    cfg = _FakeCfg(simulator=enabled, simulator_type=20, background_click=True)

    apply_mac_configuration(cfg)

    assert cfg.values["simulator"] is enabled, (
        f"用户设置 simulator={enabled}，启动后变成 {cfg.values['simulator']}"
    )
    assert cfg.values["simulator_type"] == 20, "模拟器类型也不应被改写"


def test_background_click_kept_for_playcover():
    """PlayCover 下 background_click 仍要保留：它决定用后台/前台输入。"""
    cfg = _FakeCfg(simulator=True, simulator_type=20, background_click=True)

    apply_mac_configuration(cfg)

    assert cfg.values["background_click"] is True


def test_background_click_forced_off_without_simulator():
    """CrossOver 桌面版固定前台语义，background_click 不适用。"""
    cfg = _FakeCfg(simulator=False, background_click=True)

    apply_mac_configuration(cfg)

    assert cfg.values["background_click"] is False


@pytest.mark.parametrize(
    "key",
    ["set_windows", "set_reduce_miscontact", "memory_protection", "autostart"],
)
def test_platform_invariants_still_forced(key):
    """真正不适用的项仍按平台固定，避免回归。"""
    cfg = _FakeCfg(**{key: True})

    apply_mac_configuration(cfg)

    assert cfg.values[key] is False
