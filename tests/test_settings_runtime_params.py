"""运行参数（截图间隔 / 鼠标间隔等）在 macOS 上必须仍然可配置。

合并 CrossOver 移植时，为了隐藏不适用的「窗口分辨率 / 窗口位置」，
把整个「窗口设置」复选框在 macOS 上藏掉了。而截图间隔、鼠标间隔、
鼠标按下时长、异步输入这些运行参数也挂在这一页里，于是整页失去入口，
用户无法再调整它们。

修复：这一页在所有平台都保留，只在 macOS 上隐藏与窗口管理相关的两项。
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from app.page_card import PageSetWindows


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def page(qapp):
    return PageSetWindows()


@pytest.mark.parametrize(
    "name",
    [
        "recovery_window",
        "screenshot_interval",
        "mouse_action_interval",
        "mouse_down_duration",
        "use_post_message",
    ],
)
def test_runtime_settings_are_placed_on_macos(page, name):
    """这些控件必须真正加进布局（parent 不为空），否则界面上看不到。"""
    widget = getattr(page, name)
    assert widget.parent() is not None, f"{name} 没有加入布局，界面上无法访问"


@pytest.mark.skipif(sys.platform != "darwin", reason="仅在 macOS 上校验窗口管理项被隐藏")
@pytest.mark.parametrize("name", ["win_size", "win_position"])
def test_window_management_rows_hidden_on_macos(page, name):
    """窗口分辨率 / 位置由 CrossOver 管理，这两项不放在界面上。"""
    widget = getattr(page, name)
    assert widget.parent() is None, f"{name} 不应在 macOS 上加入布局"


def test_windows_page_entry_available_on_every_platform():
    """「窗口设置」入口在所有平台都要挂到任务列表上。

    这一页同时承载运行参数（截图间隔、鼠标间隔等）。曾为隐藏 macOS 上
    不适用的窗口分辨率，把整个入口在 macOS 上跳过，导致这些运行参数
    没有入口可进。
    """
    import inspect

    from app.farming_interface import FarmingInterfaceLeft

    source = inspect.getsource(FarmingInterfaceLeft._FarmingInterfaceLeft__init_layout)
    assert "addWidget(self.set_windows)" in source, "「窗口设置」入口不应被平台条件跳过"
    assert "sys.platform != \"darwin\"" not in source.replace(
        "    ", " "
    ), "入口挂载不能按平台分支跳过"
