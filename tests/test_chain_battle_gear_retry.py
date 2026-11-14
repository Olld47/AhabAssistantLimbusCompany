"""右侧齿轮识别失败时应重试一次，仍失败才降级 P+Enter。

背景：
  - battle/gear_left.png 模板小，匹配度稳定在高位；
  - battle/gear_right.png 模板大且含较多背景，画面切换/动画期间匹配度
    容易跌到默认阈值之下，find_element 返回 None；
  - 此前一次识别失败就整场降级为 P+Enter，导致拉链战频繁失效。

修复后：识别失败时重新截图重试一次（GEAR_DETECT_RETRIES=2），
仍失败才返回 False 交给调用方降级。
"""

import sys

import pytest

from tasks.battle.battle import Battle

battle_module = sys.modules["tasks.battle.battle"]


class SequenceAuto:
    """按调用序列返回 gear 识别结果的假 auto。

    ``left_results`` / ``right_results`` 是按"第几次调用"给出的结果列表，
    用完后沿用最后一个值。
    """

    def __init__(self, left_results, right_results):
        self.left_results = list(left_results)
        self.right_results = list(right_results)
        self.left_calls = 0
        self.right_calls = 0
        self.screenshot_requests = 0

    def find_element(self, target, *args, **kwargs):
        name = str(target)
        if kwargs.get("take_screenshot"):
            self.screenshot_requests += 1
        if "gear_left" in name:
            i = min(self.left_calls, len(self.left_results) - 1)
            self.left_calls += 1
            return self.left_results[i]
        if "gear_right" in name:
            i = min(self.right_calls, len(self.right_results) - 1)
            self.right_calls += 1
            return self.right_results[i]
        return None


LEFT_OK = (400, 800)
RIGHT_OK = (1300, 800)


@pytest.fixture
def patched(monkeypatch):
    def install(fake):
        monkeypatch.setattr(battle_module, "auto", fake, raising=False)
        monkeypatch.setattr(battle_module, "sleep", lambda *a, **k: None, raising=False)
        return fake

    return install


def test_retries_once_when_gear_right_misses(patched):
    """第一次 gear_right 识别失败、第二次成功 -> 应重试并拿到结果。"""
    fake = patched(SequenceAuto([LEFT_OK], [None, RIGHT_OK]))

    gear_left, gear_right = Battle._find_battle_gears()

    assert gear_left == LEFT_OK
    assert gear_right == RIGHT_OK, "重试后应拿到右侧齿轮"
    assert fake.right_calls == 2, "应恰好尝试两次"
    assert fake.screenshot_requests >= 2, "重试前必须重新截图（画面可能已变化）"


def test_gives_up_after_all_retries_fail(patched):
    """两次都失败 -> 返回 (None, None)，由调用方降级。"""
    fake = patched(SequenceAuto([LEFT_OK], [None, None]))

    gear_left, gear_right = Battle._find_battle_gears()

    assert gear_left is None and gear_right is None
    assert fake.right_calls == Battle.GEAR_DETECT_RETRIES


def test_no_retry_needed_when_detection_succeeds_first_time(patched):
    """首次就成功时不应多跑一次（避免每回合多等一次截图）。"""
    fake = patched(SequenceAuto([LEFT_OK], [RIGHT_OK]))

    gear_left, gear_right = Battle._find_battle_gears()

    assert (gear_left, gear_right) == (LEFT_OK, RIGHT_OK)
    assert fake.right_calls == 1, "首次成功不应重试"


def test_retries_when_gear_left_misses(patched):
    """左侧齿轮缺失同样应触发重试。"""
    fake = patched(SequenceAuto([None, LEFT_OK], [RIGHT_OK, RIGHT_OK]))

    gear_left, gear_right = Battle._find_battle_gears()

    assert gear_left == LEFT_OK
    assert gear_right == RIGHT_OK
    assert fake.left_calls == 2


def test_chain_battle_falls_back_internally_after_all_retries(patched):
    """重试用尽后由 _chain_battle 自己 P+Enter，返回 True 阻止上层重复发键。"""
    fake = patched(SequenceAuto([LEFT_OK], [None, None]))
    fake.key_calls = []
    fake.key_press = lambda k: fake.key_calls.append(k)

    result = Battle._chain_battle(prioritize_skill_3=False)

    assert result is True, "内部已接管，不应让上层再发一次键"
    assert fake.key_calls == ["p", "enter"]
