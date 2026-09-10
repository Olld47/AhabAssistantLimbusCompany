"""回归测试：「第一回合全员防御」在键盘无效的设备上不得无限重复。

PlayCover（MaaTools）等触摸端的 `key_press` 是空实现，游戏回合无法靠 P+Enter 开始，
若守备分支只按 P+Enter，主循环会停留在技能选择界面反复执行同一套守备操作。
测试用假设备复现该场景，要求守备只执行一次且回合能正常开始。
"""

import sys

import numpy as np
import pytest

from tasks.battle.battle import Battle

battle_module = sys.modules["tasks.battle.battle"]

GEAR_LEFT = (399, 812)
GEAR_RIGHT = (1372, 819)
MORE_INFORMATION = (1595, 59)
PAUSE = (1760, 61)
WIN_RATE_CARD = (764, 723)
LEGEND = (1822, 175)


class LoopDetected(RuntimeError):
    """技能选择界面被反复处理，说明回合一直没能开始。"""


class FakeDevice:
    """模拟一台游戏设备：技能选择 -> 交战播片 -> 战斗结束。"""

    MAX_SELECTION_ITERATIONS = 10
    PAUSE_HITS_BEFORE_FINISH = 3

    def __init__(self, keyboard_works: bool, mouse_click_rate: bool):
        self.keyboard_works = keyboard_works
        self.model = "clam"
        self.screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # 状态统计
        self.state = "selection"
        self.defense_runs = 0
        self.selection_iterations = 0
        self.pause_hits = 0
        self.gear_right_clicks = 0
        self.win_rate_card_finds = 0
        self.start_battle = Battle(is_tool=True)
        self.start_battle.mouse_click_rate = mouse_click_rate

    # --- 图像识别 ---
    def find_element(
        self,
        target,
        find_type="image",
        threshold=0.8,
        max_retries=1,
        take_screenshot=False,
        model=None,
        my_crop=None,
        min_dist=10,
        additional_stack=0,
    ):
        if target == "battle/gear_left.png" and threshold != 0.9:
            # _defense_this_round 内部的定位，说明真的执行了一轮守备
            self.defense_runs += 1
        if self.state == "selection":
            if target == "battle/more_information_assets.png":
                self.selection_iterations += 1
                if self.selection_iterations > self.MAX_SELECTION_ITERATIONS:
                    raise LoopDetected("技能选择界面未推进，守备被反复执行")
                return MORE_INFORMATION
            if target == "battle/gear_left.png":
                return GEAR_LEFT
            if target == "battle/gear_right.png":
                return GEAR_RIGHT
            if target == "battle/win_rate_card.png":
                self.win_rate_card_finds += 1
                return WIN_RATE_CARD
            return None
        if self.state == "battle":
            if target == "battle/pause_assets.png":
                self.pause_hits += 1
                if self.pause_hits >= self.PAUSE_HITS_BEFORE_FINISH:
                    self.state = "finished"
                return PAUSE
            return None
        if target == "mirror/road_in_mir/legend_assets.png":
            return LEGEND
        return None

    def find_language_text(self, *args, **kwargs):
        return False

    def find_text_element(self, *args, **kwargs):
        return False

    def click_element(self, target, *args, **kwargs):
        if target == "battle/gear_right.png" and self.state == "selection":
            self.gear_right_clicks += 1
            self.state = "battle"
            return True
        return False

    # --- 输入 ---
    def key_press(self, key):
        if self.keyboard_works and key == "enter" and self.state == "selection":
            self.state = "battle"

    def mouse_click(self, x, y, times=1, move_back=False):
        return True

    def mouse_click_blank(self, coordinate=(1, 1), times=1, move_back=False):
        return True

    def mouse_to_blank(self, coordinate=(1, 1), move_back=False) -> None:
        return None

    def mouse_drag_link(self, position, drag_time=0.1, move_back=False) -> None:
        return None

    # --- 截图 ---
    def take_screenshot(self, save=False):
        return self.screenshot

    def get_restore_time(self):
        return None


@pytest.fixture
def run_fight(monkeypatch):
    monkeypatch.setattr(battle_module, "sleep", lambda *args: None)
    monkeypatch.setattr(battle_module, "retry", lambda *args, **kwargs: True)
    monkeypatch.setattr("tasks.base.retry.check_times", lambda *args, **kwargs: False)

    def _run(keyboard_works: bool, mouse_click_rate: bool):
        device = FakeDevice(keyboard_works=keyboard_works, mouse_click_rate=mouse_click_rate)
        monkeypatch.setattr(battle_module, "auto", device)
        device.start_battle.fight(defense_first_round=True)
        return device

    return _run


def test_defense_starts_round_on_keyboardless_device(run_fight):
    """键盘无效时用鼠标开始回合，守备只执行一次。"""
    device = run_fight(keyboard_works=False, mouse_click_rate=True)

    assert device.defense_runs == 1
    assert device.state == "finished"


def test_defense_keeps_selection_on_keyboardless_device(run_fight):
    """键盘无效且尚未发现鼠标兜底时，仍用开始按钮确认守备，不用胜率自动选择覆盖。"""
    device = run_fight(keyboard_works=False, mouse_click_rate=False)

    assert device.defense_runs == 1
    assert device.win_rate_card_finds == 0
    assert device.state == "finished"


def test_defense_uses_keyboard_when_available(run_fight):
    """键盘可用时保持原有 P+Enter 流程，不额外点击鼠标。"""
    device = run_fight(keyboard_works=True, mouse_click_rate=False)

    assert device.defense_runs == 1
    assert device.gear_right_clicks == 0
    assert device.win_rate_card_finds == 0
    assert device.start_battle.mouse_click_rate is False
    assert device.state == "finished"
