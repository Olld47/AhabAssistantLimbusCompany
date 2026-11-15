"""macOS 上按 CapsLock 不得让进程崩溃。

崩溃现场（macOS crash report，SIGTRAP / EXC_BREAKPOINT，非主线程）：

    _dispatch_assert_queue_fail
    TSMGetInputSourceProperty
    ProcessCapsLockSequenceKeyUp
    TSMAdjustCapsLockPressAndHold
    CreateEventWithCGEvent
    +[NSEvent eventWithCGEvent:]
    ... pynput 键盘监听线程 ...

CapsLock 抬起时 pynput 在监听线程里调用 NSEvent.eventWithCGEvent_，
它内部访问 Carbon TIS（输入源管理），该 API 要求在主队列执行；
后台线程调用会撞上 dispatch_assert_queue 断言，直接以 SIGTRAP 杀进程。

修复：包装 pynput 的 Listener._handle_message，键码为 CapsLock(0x39)
的事件直接丢弃，不进入那条会崩溃的分支。
"""

import sys

import pytest

import module.hotkey_listener  # noqa: F401  导入即安装补丁
from module.hotkey_listener import _CAPS_LOCK_VK

darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="仅 macOS 有该崩溃路径")


@darwin_only
def test_caps_lock_guard_installed():
    """导入 hotkey_listener 后补丁必须已生效。"""
    from pynput.keyboard import _darwin

    assert getattr(_darwin.Listener, "_caps_lock_guard_installed", False) is True
    assert _darwin.Listener._handle_message.__name__ == "_guarded_handle_message"


@darwin_only
def test_caps_lock_event_is_dropped(monkeypatch):
    """CapsLock 事件必须被丢弃，不能进入 pynput 的解析路径。"""
    from unittest.mock import MagicMock

    from pynput.keyboard import _darwin

    guarded = _darwin.Listener._handle_message
    fake_self = MagicMock()

    monkeypatch.setattr(_darwin, "CGEventGetIntegerValueField", lambda *a: _CAPS_LOCK_VK)
    # NSEvent 一旦被调用就说明走进了崩溃分支
    monkeypatch.setattr(
        _darwin, "NSEvent", MagicMock(side_effect=AssertionError("不应调用 NSEvent"))
    )

    guarded(fake_self, None, 999, MagicMock(), None, False)

    assert fake_self._event_to_key.called is False, "CapsLock 不应进入按键解析"
    assert fake_self.on_press.called is False


@darwin_only
def test_normal_key_still_handled(monkeypatch):
    """普通按键必须照常处理，补丁不能误伤。"""
    from unittest.mock import MagicMock

    from pynput.keyboard import _darwin

    guarded = _darwin.Listener._handle_message
    fake_self = MagicMock()
    fake_self._event_to_key.return_value = "q"

    monkeypatch.setattr(_darwin, "CGEventGetIntegerValueField", lambda *a: 0x0C)  # Q

    guarded(fake_self, None, _darwin.kCGEventKeyDown, MagicMock(), None, False)

    assert fake_self._event_to_key.called is True
    assert fake_self.on_press.called is True


def test_caps_lock_vk_value():
    """0x39 是 pynput 里 Key.caps_lock 对应的 vk，不能写错。"""
    assert _CAPS_LOCK_VK == 0x39
