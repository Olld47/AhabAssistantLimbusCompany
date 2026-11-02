"""macOS 前台输入：把引擎的 1920×1080 图像坐标映射到 CrossOver 游戏窗口。

本模块只在 macOS 上导入；Windows 继续使用 ``input_handlers.input`` 里的实现。
两者共同实现 ``AbstractInput``，由 ``automation.init_input`` 按平台选择。
"""
import random
from time import monotonic, sleep

import pyautogui
import pyperclip

from module.logger import log
from module.macos.gesture import held_mouse
from module.macos.window import window
from module.my_error.my_error import userStopError

from .. import AbstractInput

pyautogui.PAUSE = 0.03


def _segment_durations(duration, count):
    """把 ``duration`` 展开成每段的时长列表。

    ``duration`` 既可以是单段时长（各段相同），也可以是与段数对应的序列
    （用于「快速起步 + 减速 + 静止」这类需要逐段控制速度的手势）。
    """
    if count <= 0:
        return []
    if isinstance(duration, (list, tuple)):
        steps = [max(0.01, float(step)) for step in duration]
        if len(steps) >= count:
            return steps[:count]
        # 段数不足时用最后一段补齐，避免短列表导致少走几段。
        return steps + [steps[-1] if steps else 0.05] * (count - len(steps))
    return [max(0.01, float(duration))] * count


class Input(AbstractInput):
    """基于 ``pyautogui`` 的前台输入，坐标以 1920×1080 画布为准。"""

    def wait_pause(self):
        from time import time

        from module.macos.control import check_cancelled

        check_cancelled()
        while self.is_pause:
            check_cancelled()
            sleep(0.05)
            self.restore_time = time()

    def _geometry(self):
        self.wait_pause()
        try:
            pyautogui.failSafeCheck()
        except pyautogui.FailSafeException as e:
            raise userStopError("鼠标触及屏幕角落，已停止挂机") from e
        return window.input_geometry()

    def mouse_click(self, x, y, times=1, move_back=False):
        previous = pyautogui.position()
        for _ in range(times):
            point = self._geometry().to_screen(x, y)
            pyautogui.click(*point)
        if move_back:
            pyautogui.moveTo(*previous)
        return True

    def mouse_click_blank(self, coordinate=(32, 32), times=1, move_back=False):
        return self.mouse_click(
            coordinate[0] + random.randint(0, 10),
            coordinate[1] + random.randint(0, 10),
            times,
            move_back,
        )

    def _drag(self, points, duration, settle, move_back):
        """按住拖动；``duration`` 可以是单段时长，也可以是与各段一一对应的列表。"""
        g = self._geometry()
        mapped = [g.to_screen(*p) for p in points]
        steps = _segment_durations(duration, len(mapped) - 1)
        previous = pyautogui.position()

        def validate():
            if self.is_pause or window.input_geometry() != g:
                raise userStopError("拖动中断，已释放鼠标")

        pyautogui.moveTo(*mapped[0])
        with held_mouse(pyautogui, validate):
            for (start, end), step in zip(zip(mapped, mapped[1:]), steps):
                start_time = monotonic()
                while True:
                    validate()
                    progress = min(1, (monotonic() - start_time) / max(0.05, step))
                    pyautogui.moveTo(
                        start[0] + (end[0] - start[0]) * progress,
                        start[1] + (end[1] - start[1]) * progress,
                        _pause=False,
                    )
                    if progress >= 1:
                        break
                    sleep(0.03)
            deadline = monotonic() + settle
            while monotonic() < deadline:
                validate()
                sleep(0.03)
        if move_back:
            pyautogui.moveTo(*previous)

    def mouse_drag(self, x, y, drag_time=0.1, dx=0, dy=0, move_back=True):
        self._drag([(x, y), (x + dx, y + dy)], drag_time, 0.5, move_back)

    def mouse_drag_map(self, x, y, drag_time=0.1, dx=0, dy=0, move_back=True):
        self.mouse_drag(x, y, drag_time, dx, dy, move_back)

    def mouse_swipe_for_scroll(self, x, y, duration=0.3, dx=0, dy=0, move_back=True):
        self._drag([(x, y), (x + dx, y + dy)], duration, 0, move_back)

    def mouse_swipe_for_team_scroll(self, x, y, duration=0.3, dx=0, dy=0, move_back=True):
        """滚动编队列表：末端减速并静止，消除松手惯性。

        列表要按行数精确定位队伍。匀速拖到底立刻松手时，Unity 会按松手速度
        继续惯性滚动，多滚的行数不可控。Windows 版由
        ``build_windows_scroll_swipe_plan`` 追加减速段和静止段。

        这里只取该路径的折点，仍交给 ``_drag`` 执行：后台模式的
        ``BackgroundInput`` 覆盖了 ``_drag``（走定向事件），若在此直接操作
        pyautogui 就会绕过后台投递，列表根本不动。
        """
        from module.automation.input_handlers.scroll_swipe import (
            WINDOWS_SCROLL_SETTLE_DURATION,
            build_windows_scroll_swipe_plan,
        )

        plan, settle_duration = build_windows_scroll_swipe_plan(x, y, dx, dy, duration)
        if len(plan) < 2:
            return
        points = [point for point, _ in plan]
        # plan 的第二个元素是「到达该点所需的耗时」，转成逐段时长交给 _drag。
        steps = [max(0.01, step) for _, step in plan[1:]]
        self._drag(points, steps, settle_duration or WINDOWS_SCROLL_SETTLE_DURATION, move_back)

    def mouse_drag_down(self, x, y, reverse=1, move_back=True):
        self.mouse_drag(x, y, 0.4, dy=300 * reverse, move_back=move_back)

    def mouse_drag_link(self, position, drag_time=0.1, move_back=False):
        if position:
            self._drag(position, drag_time, 0, move_back)

    def mouse_scroll(self, direction=-3):
        g = self._geometry()
        # 在标题栏上滚动不会传到游戏内容，因此先定位到画面中心。
        pyautogui.moveTo(*g.to_screen(960, 540))
        self._geometry()
        pyautogui.scroll(direction)
        return True

    def mouse_to_blank(self, coordinate=None, move_back=False):
        g = self._geometry()
        previous = pyautogui.position()
        if coordinate is None:
            left, top, right, bottom = g.content_rect
            if not (left <= previous[0] < right and top <= previous[1] < bottom):
                return
            # 用标题栏中间清掉悬停提示，避免反复把指针拉到角落。
            point = (
                (round(g.x + g.width / 2), round(g.y + g.titlebar / 2))
                if g.titlebar
                else g.to_screen(960, 8)
            )
        else:
            point = g.to_screen(*coordinate)
        pyautogui.moveTo(*point)
        if move_back:
            pyautogui.moveTo(*previous)

    def key_press(self, key):
        self._geometry()
        pyautogui.press(key)

    def input_text(self, text):
        self._geometry()
        previous = pyperclip.paste()
        try:
            pyperclip.copy(text)
            # 接收方是 CrossOver 里运行的 Windows 游戏，所以用 ctrl+v。
            pyautogui.hotkey("ctrl", "v")
            sleep(0.15)
        finally:
            pyperclip.copy(previous)
