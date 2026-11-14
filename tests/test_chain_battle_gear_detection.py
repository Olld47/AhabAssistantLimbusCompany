"""回归测试：拉链战（技能连线）识别失败时的降级不应被误判。

线上问题：刷牢时第二回合之后技能槽变长，链接战失败并降级为 P+Enter。

实机现象：
  - 降级全部伴随 battle/gear_right.png 匹配度低于默认阈值，
    而 battle/gear_left.png 始终稳定在高位；
  - gear_right 的位置本身落在合理范围内，说明不是窗口或坐标问题，
    而是模板匹配本身失准；
  - 降级与技能槽数无对应关系（多种槽数都出现过）。

因此「拉链失败」的真实原因不是槽位变长导致坐标算错，而是右侧齿轮
没被识别到。测试锁定两点：
  1. gear_right 未达阈值时 _chain_battle 必须返回 False（不盲拉）；
  2. 只要齿轮都识别到，拉链路径必须走通（不得因槽位数变化而失败）。
"""

import sys

import pytest

from tasks.battle.battle import Battle

battle_module = sys.modules["tasks.battle.battle"]


class RecordingAuto:
    """记录 find_element / 拖拽调用的假 auto。"""

    def __init__(self, gear_left, gear_right):
        self.gear_left = gear_left
        self.gear_right = gear_right
        self.drag_calls = []
        self.key_calls = []

    def find_element(self, target, *args, **kwargs):
        if "gear_left" in str(target):
            return self.gear_left
        if "gear_right" in str(target):
            return self.gear_right
        return None

    def get_screenshot_crop(self, bbox):
        import numpy as np

        return np.zeros((20, max(1, int(bbox[2] - bbox[0])), 3), dtype=np.uint8)

    def mouse_drag_link(self, points):
        self.drag_calls.append(list(points))
        return True

    def mouse_to_blank(self, **kwargs):
        return None

    def key_press(self, key):
        self.key_calls.append(key)
        return None


@pytest.fixture
def patched(monkeypatch):
    """替换 battle 模块里的 auto / cfg / sleep，并固定槽位推导。"""
    state = {}

    def install(gear_left, gear_right, skill_nums=8):
        fake = RecordingAuto(gear_left, gear_right)
        monkeypatch.setattr(battle_module, "auto", fake, raising=False)
        monkeypatch.setattr(battle_module, "sleep", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(
            battle_module.Battle, "_get_lower_row_skill_indexes",
            staticmethod(lambda idx, nums, prio: set()), raising=False,
        )
        state["fake"] = fake
        state["skill_nums"] = skill_nums
        return fake

    return install


def test_chain_battle_falls_back_internally_when_gear_right_missing(patched):
    """右侧齿轮最终识别不到时，在 _chain_battle 内部直接 P+Enter 开战。

    不返回 False 交给上层再发一次键：那样会变成"拉链失败→上层降级"的
    二次操作，容易打乱已选好的技能状态。
    """
    fake = patched(gear_left=(400, 800), gear_right=None)

    result = Battle._chain_battle(prioritize_skill_3=False)

    assert result is True, "内部已接管本回合，应返回 True 阻止上层重复发键"
    assert fake.drag_calls == [], "识别失败时不得发起拖拽"
    assert fake.key_calls == ["p", "enter"], "应自行用 P+Enter 开战"


def test_chain_battle_falls_back_internally_when_gear_left_missing(patched):
    fake = patched(gear_left=None, gear_right=(1300, 800))

    result = Battle._chain_battle(prioritize_skill_3=False)

    assert result is True
    assert fake.drag_calls == []
    assert fake.key_calls == ["p", "enter"]


def test_chain_battle_succeeds_with_normal_gears(patched):
    """两侧齿轮都识别到时应正常拉链，槽位数变化不应导致失败。"""
    fake = patched(gear_left=(400, 800), gear_right=(1300, 800))

    result = Battle._chain_battle(prioritize_skill_3=False)

    assert result is True, "齿轮识别正常时拉链应成功"
    assert len(fake.drag_calls) == 1, "应发起一次拖拽"
    assert fake.key_calls == ["enter"], "拉链后应回车确认"


@pytest.mark.parametrize("skill_nums", [6, 8, 9, 10])
def test_chain_battle_handles_varying_slot_counts(patched, skill_nums):
    """技能槽数变化（第二回合后变长）本身不应导致拉链失败。

    槽位越多，技能点越靠外；只要齿轮识别稳定，路径长度变化是正常的，
    但必须仍然成功返回 True。
    """
    fake = patched(gear_left=(400, 800), gear_right=(1300, 800), skill_nums=skill_nums)

    result = Battle._chain_battle(prioritize_skill_3=False)

    assert result is True, f"槽位数 {skill_nums} 时拉链不应失败"
    points = fake.drag_calls[0]
    assert len(points) >= 3, "拉链路径至少包含起点、技能点、终点"
