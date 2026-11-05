"""星光加成只设置一次，不能因确认按钮漏识别而重复点击。

线上现象：配置 #1/#3/#4/#7/#8 全是基础等级（opening_bonus 为 1），
实际却有卡片变成 ++，还有该选的没选中。

原因：卡片中心的点击是 toggle（选中/取消切换）。确认按钮
select_star_confirm_assets 偶发只有 0.40/0.45 相似度（低于 0.8 阈值），
click_element 返回 False 就不 break，while 循环再跑一轮，把已经选好的
卡片又点了一遍——全部翻转回未选中。实测日志里连续出现两轮完整的点击。

修复：用 bonus_applied 标记保证只执行一次；确认按钮加三次重试。
"""

from unittest.mock import patch

import pytest

from tasks.mirror.mirror import Mirror


def _make_mirror(bonus):
    """构造一个只用于测试 enter_mir_with_star 的 Mirror 实例。"""
    mirror = Mirror.__new__(Mirror)
    mirror.use_starlight = False
    mirror.opening_bonus = bonus
    return mirror


@pytest.fixture(autouse=True)
def _isolate():
    """隔离全局 auto/cfg，避免与其他测试的 patch 互相影响。"""
    import tasks.mirror.mirror as mm
    saved = (mm.auto, mm.cfg)
    saved_anchor = mm.find_grace_anchor
    yield
    mm.auto, mm.cfg = saved
    mm.find_grace_anchor = saved_anchor


def _run_starlight_loop(mirror, rounds):
    """用假交互跑 n 轮循环，返回每轮记录的点击坐标。"""
    clicks = []
    stats = {"screenshot": 0}

    def fake_find(target, *args, **kwargs):
        # 只在第一轮让确认按钮"漏识别"，模拟线上的偶发低分。
        if "select_star_confirm" in str(target):
            return False
        return False

    def fake_click(target, *a, **k):
        return False

    def fake_mouse_action(pos, *a, **k):
        clicks.append(tuple(pos))
        return True

    def fake_screenshot(*a, **k):
        stats["screenshot"] += 1
        # 跑够轮数后抛异常退出循环，避免真的进入下一阶段。
        if stats["screenshot"] > rounds * 3:
            raise RuntimeError("loop reached")
        return object()

    with patch("tasks.mirror.mirror.find_grace_anchor", return_value=(1675, 68)), \
         patch("tasks.mirror.mirror.auto") as fake_auto, \
         patch("tasks.mirror.mirror.cfg") as fake_cfg, \
         patch("tasks.mirror.mirror.sleep"), \
         patch("tasks.mirror.mirror.retry", return_value=True), \
         pytest.raises(RuntimeError, match="loop reached"):
        fake_auto.take_screenshot = fake_screenshot
        fake_auto.find_element = fake_find
        fake_auto.click_element = fake_click
        fake_auto.mouse_action_with_pos = fake_mouse_action
        fake_auto.mouse_to_blank = lambda *a, **k: None
        fake_auto.model = "clam"
        fake_cfg.set_win_size = 1080
        mirror.enter_mir_with_star()

    return clicks


def test_bonus_clicked_only_once_across_loop_iterations():
    """确认按钮漏识别导致循环多跑时，不能重复点击卡片。

    重复点击会 toggle 掉已选状态，表现为"配置是基础等级却出现 ++"。
    """
    bonus = [1, 0, 1, 1, 0, 0, 1, 1, 0, 0]  # #1/#3/#4/#7/#8，全是基础等级
    expected = 5  # 只有 5 个卡片需要点击
    clicks = _run_starlight_loop(_make_mirror(bonus), rounds=3)

    assert len(clicks) == expected, (
        f"应只点击 {expected} 次（每个选中项一次），实际 {len(clicks)} 次；"
        f"循环重复点击会把选择状态翻转掉"
    )


def test_bonus_never_clicks_plus_slot_for_basic_level():
    """opening_bonus 为 1 时不能点 + / ++ 按钮，否则会升级成 ++。"""
    bonus = [1, 0, 1, 1, 0, 0, 1, 1, 0, 0]
    clicks = _run_starlight_loop(_make_mirror(bonus), rounds=2)

    scale = 1080 / 1440
    first_x = 1675 - 1800 * scale
    base_y = 68 + 300 * scale
    # + 按钮在 y + 320*scale，卡片中心在 base_y 或 base_y + 480*scale
    card_ys = {round(base_y), round(base_y + 480 * scale)}
    for x, y in clicks:
        assert round(y) in card_ys, (
            f"点击 ({x}, {y}) 不在卡片中心行 {card_ys}，可能误点了 +/++ 升级按钮"
        )
