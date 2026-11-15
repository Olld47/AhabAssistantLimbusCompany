from __future__ import annotations

import itertools
import sys
import threading
from collections.abc import Callable

from pynput import keyboard

from module.logger import log

_MODIFIER_KEYS = {
    keyboard.Key.alt,
    keyboard.Key.alt_gr,
    keyboard.Key.cmd,
    keyboard.Key.ctrl,
    keyboard.Key.shift,
}

#: CapsLock 的 macOS 虚拟键码（pynput 里 Key.caps_lock 对应的 vk）。
_CAPS_LOCK_VK = 0x39


def _install_caps_lock_guard() -> None:
    """让 pynput 的 macOS 监听跳过 CapsLock 事件。

    崩溃现场（macOS crash report，SIGTRAP / EXC_BREAKPOINT）：

        _dispatch_assert_queue_fail
        TSMGetInputSourceProperty
        ProcessCapsLockSequenceKeyUp
        TSMAdjustCapsLockPressAndHold
        CreateEventWithCGEvent
        +[NSEvent eventWithCGEvent:]
        ... pynput 监听线程 ...

    CapsLock 抬起时，pynput 在**监听线程**里调 ``NSEvent.eventWithCGEvent_``，
    而它内部要访问 Carbon TIS（输入源管理），该 API 要求在主队列执行；
    在后台线程调用会撞上 dispatch_assert_queue 断言，直接以 SIGTRAP
    杀掉整个进程——所以按一下 CapsLock 程序就闪退。

    这里包装 ``_handle_message``：识别到 CapsLock 的按键事件就原样丢弃，
    不进入 pynput 那条会崩溃的分支。CapsLock 本来也不作为快捷键使用
    （录入控件已把它排除），因此忽略它不影响任何功能。
    """
    if sys.platform != "darwin":
        return
    try:
        from pynput.keyboard import _darwin as _pynput_darwin
    except Exception as exc:  # 平台模块结构变化时不影响主流程
        log.debug(f"CapsLock 保护补丁跳过（无法导入 _darwin）: {exc}")
        return

    listener_cls = _pynput_darwin.Listener
    if getattr(listener_cls, "_caps_lock_guard_installed", False):
        return

    original = listener_cls._handle_message

    def _guarded_handle_message(self, proxy, event_type, event, refcon, injected):
        try:
            if _pynput_darwin.CGEventGetIntegerValueField(
                event, _pynput_darwin.kCGKeyboardEventKeycode
            ) == _CAPS_LOCK_VK:
                return  # 丢弃 CapsLock，避免后台线程调用 Carbon TIS 导致 SIGTRAP
        except Exception:
            pass  # 取不到键码时按原逻辑处理
        return original(self, proxy, event_type, event, refcon, injected)

    listener_cls._handle_message = _guarded_handle_message
    listener_cls._caps_lock_guard_installed = True
    log.debug("已安装 CapsLock 保护补丁（避免 macOS 上按 CapsLock 闪退）")


_install_caps_lock_guard()

#: 快捷键映射提供者：重建监听时现取，保证调用方能读到最新的 cfg 值。
HotkeyProvider = Callable[[], dict[str, Callable[[], None]]]


class _ExactHotKey:
    def __init__(self, keys: list[keyboard.Key | keyboard.KeyCode], on_activate: Callable[[], None]):
        self._keys = set(keys)
        self._state: set[keyboard.Key | keyboard.KeyCode] = set()
        self._required_modifiers = {key for key in self._keys if key in _MODIFIER_KEYS}
        self._is_active = False
        self._on_activate = on_activate

    def press(
        self,
        key: keyboard.Key | keyboard.KeyCode,
        pressed_modifiers: set[keyboard.Key],
    ) -> None:
        if key in self._keys:
            self._state.add(key)

        should_activate = self._state == self._keys and pressed_modifiers == self._required_modifiers
        if should_activate and not self._is_active:
            self._is_active = True
            self._on_activate()
        elif not should_activate:
            self._is_active = False

    def release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        self._state.discard(key)
        self._is_active = False


class GlobalHotKeys:
    """进程内唯一的全局快捷键监听，各组件按需注册自己的快捷键映射。

    macOS 上 pynput 的键盘监听要走 Carbon TIS：监听线程在 TSMGetInputSourceProperty
    里会撞上 dispatch_assert_queue 断言。只要进程里出现过第二个存活的监听线程
    （两个监听重叠，或者旧监听还没退干净就新建一个），就会直接以 SIGTRAP 终止整个
    进程——这正是自动战斗小工具曾经的崩溃原因。因此底层 Listener 全进程只创建一次，
    注册/注销/暂停都只改快捷键表，绝不重建监听。

    同一个快捷键被多个组件注册时，后注册者优先；关闭/销毁的组件必须
    :meth:`unregister`，否则它的回调会一直占据该快捷键。
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._listener: keyboard.Listener | None = None
        self._registrations: dict[int, HotkeyProvider] = {}
        self._tokens = itertools.count()
        self._suspended = False
        # 监听线程只读、改动时整体替换，避免回调与改动互相看到半成品状态
        self._hotkeys: list[_ExactHotKey] = []
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        # canonical 是平台相关的实例方法（Windows 依赖监听器自身的键盘布局翻译器），
        # 只能取自那个唯一的监听器
        self._canonicalize: Callable[[keyboard.Key | keyboard.KeyCode], keyboard.Key | keyboard.KeyCode] = (
            lambda key: key
        )

    def register(self, provider: HotkeyProvider) -> int:
        """注册一组快捷键映射，返回可用于注销的 token。"""
        with self._lock:
            token = next(self._tokens)
            self._registrations[token] = provider
            self._refresh()
            return token

    def unregister(self, token: int) -> None:
        """注销 token 对应的快捷键映射；token 不存在时忽略。"""
        with self._lock:
            if self._registrations.pop(token, None) is not None:
                self._refresh()

    def stop(self) -> None:
        """暂停快捷键派发（录入新快捷键时用，避免旧快捷键被触发），保留注册。"""
        with self._lock:
            self._suspended = True
            self._refresh()

    def start(self) -> None:
        """恢复派发，并按当前注册重取快捷键（可读到最新的 cfg 值）。"""
        with self._lock:
            self._suspended = False
            self._refresh()

    def _refresh(self) -> None:
        self._hotkeys = [] if self._suspended else self._collect_hotkeys()
        if self._listener is not None or not self._hotkeys:
            return
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        try:
            listener.start()
        except Exception as e:
            log.error(f"快捷键监听启动失败: {e}")
            return
        self._canonicalize = listener.canonical
        self._listener = listener

    def _collect_hotkeys(self) -> list[_ExactHotKey]:
        resolved: dict[str, Callable[[], None]] = {}
        for provider in self._registrations.values():
            try:
                hotkeys = provider()
            except Exception as e:
                log.error(f"读取快捷键配置失败: {e}")
                continue
            resolved.update(hotkeys)  # 后注册者覆盖先注册者

        collected = []
        for hotkey, callback in resolved.items():
            try:
                keys = keyboard.HotKey.parse(hotkey)
            except ValueError:
                log.error(f"快捷键 {hotkey} 格式无效，请确认设置的快捷键格式有效")
                continue
            collected.append(_ExactHotKey(keys, callback))
        return collected

    def _on_press(self, key, injected=False):
        if injected:
            return

        canonical_key = self._canonicalize(key)
        self._pressed_keys.add(canonical_key)
        pressed_modifiers = {key for key in self._pressed_keys if key in _MODIFIER_KEYS}
        for hotkey in self._hotkeys:
            hotkey.press(canonical_key, pressed_modifiers)

    def _on_release(self, key, injected=False):
        if injected:
            return

        canonical_key = self._canonicalize(key)
        for hotkey in self._hotkeys:
            hotkey.release(canonical_key)
        self._pressed_keys.discard(canonical_key)


#: 进程内唯一的全局快捷键监听。
global_hotkeys = GlobalHotKeys()
