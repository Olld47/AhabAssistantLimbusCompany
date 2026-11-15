"""macOS 上按 CapsLock 不得让进程崩溃。

崩溃现场（macOS crash report，SIGTRAP / EXC_BREAKPOINT，崩在监听线程）：

    _dispatch_assert_queue_fail
    TSMGetInputSourceProperty
    ProcessCapsLockSequenceKeyUp
    TSMAdjustCapsLockPressAndHold
    CreateEventWithCGEvent
    +[NSEvent eventWithCGEvent:]
    ... m_CGEventTapCallBack（pynput 的 CGEventTap 回调）...

CapsLock 在 macOS 上是 NSSystemDefined 类型事件。pynput 收到后在监听线程里
调 NSEvent.eventWithCGEvent_，它内部访问 Carbon TIS（输入源管理），要求在主
队列执行；后台线程调用会撞上 dispatch_assert_queue 断言，以 SIGTRAP 杀掉
整个进程——所以按一下 CapsLock 就闪退，Python 层抓不到。

修复：把 NSSystemDefined 从监听的事件掩码里去掉，事件根本不会进入
_handle_message。代价是媒体键一并失效，但本程序不需要媒体键。

（早前尝试在 _handle_message 里按 keycode 过滤，实测无法阻止崩溃，
因为崩溃发生在事件被分发到 Python 之前的系统层路径上。）
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


@darwin_only
def test_system_defined_removed_from_event_mask():
    """NSSystemDefined 必须从监听掩码里移除——这是 CapsLock 事件的来源。"""
    from pynput.keyboard import _darwin

    bit = _darwin.CGEventMaskBit(_darwin.NSSystemDefined)
    assert (_darwin.Listener._EVENTS & bit) == 0, (
        "NSSystemDefined 仍在监听掩码中，CapsLock 事件会进入会崩溃的分支"
    )


@darwin_only
def test_keyboard_events_still_monitored():
    """普通按键与修饰键的监听不能受影响，否则快捷键全失效。"""
    from pynput.keyboard import _darwin

    for name in ("kCGEventKeyDown", "kCGEventKeyUp", "kCGEventFlagsChanged"):
        bit = _darwin.CGEventMaskBit(getattr(_darwin, name))
        assert (_darwin.Listener._EVENTS & bit) != 0, f"{name} 被误移除，快捷键会失效"


def test_caps_lock_vk_value():
    """0x39 是 pynput 里 Key.caps_lock 对应的 vk。"""
    assert _CAPS_LOCK_VK == 0x39
