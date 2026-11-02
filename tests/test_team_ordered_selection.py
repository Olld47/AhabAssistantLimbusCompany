"""按序号选队：翻页距离必须与行高一致，且末页只补偿一次。

线上问题：目标 #6 实际选中 #11。两个原因叠加——
1. 桌面端每页固定滑 400 单位，而一页只有 5 行（5 × 72.5 = 362.5），
   每页多滑约 0.52 行，翻页越多偏差越大；
2. 末页滑动距离扣了半行、点击偏移又加了半行，两次补偿让 #37/#39
   落在相邻行上。

这里不依赖真实截图，直接按"滑动距离 ÷ 行高 = 前进行数"的几何关系
还原每次点击会落到哪一行，锁定 1..40 全部正确。
"""

from unittest.mock import patch

import pytest

from module.config import cfg
from tasks.teams import team_formation


def _selected_team(num: int) -> int:
    """按现有常量推算：滑到第几页 + 页内第几行 = 实际选中的队伍号。"""
    row = team_formation.ORDERED_TEAM_ROW_HEIGHT
    page_count, order = team_formation._ordered_team_location(num)
    top = 1.0  # 列表已重置到最顶端，第一行是 1 号队
    gain = team_formation.ORDERED_TEAM_ROW_SCROLL_GAIN
    with patch.object(cfg, "simulator", False):
        for page_index in range(1, page_count + 1):
            # 拖动距离只有 gain 比例传导成滚动（实机标定 0.85）。
            top += team_formation._ordered_team_page_swipe_distance(page_index) / row * gain
        offset = team_formation._ordered_team_click_offset(page_count, order)
    return round(top + offset / row)


@pytest.mark.parametrize("num", range(1, team_formation.ORDERED_TEAM_COUNT + 1))
def test_ordered_selection_lands_on_requested_team(num):
    assert _selected_team(num) == num, f"目标 #{num} 实际会选中 #{_selected_team(num)}"


def test_desktop_page_swipe_advances_exactly_one_page():
    """桌面端一页滑动"实际滚动"必须等于 5 行，否则偏差会逐页累积。

    拖动距离不等于滚动距离：只有 ORDERED_TEAM_ROW_SCROLL_GAIN 的比例传导，
    所以发出去的拖动距离要按该比例放大。
    """
    row = team_formation.ORDERED_TEAM_ROW_HEIGHT
    page_size = team_formation.ORDERED_TEAM_PAGE_SIZE
    gain = team_formation.ORDERED_TEAM_ROW_SCROLL_GAIN
    with patch.object(cfg, "simulator", False):
        swipe = team_formation._ordered_team_page_swipe_distance(1)
    assert swipe / row * gain == pytest.approx(page_size)


def test_last_page_compensates_half_row_only_once():
    """末页的滑动距离与点击偏移不能各补一次半行。"""
    row = team_formation.ORDERED_TEAM_ROW_HEIGHT
    last_index = team_formation.ORDERED_TEAM_LAST_PAGE_INDEX
    gain = team_formation.ORDERED_TEAM_ROW_SCROLL_GAIN
    with patch.object(cfg, "simulator", False):
        swipe = team_formation._ordered_team_page_swipe_distance(last_index)
        offset = team_formation._ordered_team_click_offset(last_index, 0)
    # 末页实际滚动的距离 + 点击偏移，正好落在末页第一行（#35）。
    assert swipe * gain + offset == pytest.approx(
        team_formation.ORDERED_TEAM_LAST_PAGE_SWIPE_DISTANCE
        + team_formation.ORDERED_TEAM_BOTTOM_PAGE_OFFSET
    )


def test_team_scroll_goes_through_drag_so_background_mode_works():
    """前台列表滚动必须经由 _drag（前台实现里 _drag 才负责按下/释放）。"""
    from module.automation.input_handlers.macos.foreground_input import Input

    driver = object.__new__(Input)  # 不建立真实连接
    recorded = {}
    driver._drag = lambda points, duration, settle, move_back: recorded.update(
        points=points, duration=duration, settle=settle
    )

    driver.mouse_swipe_for_team_scroll(100, 700, duration=0.3, dy=-300)

    assert recorded, "鼠标滚动必须通过 _drag 执行"
    points = recorded["points"]
    assert points[-1][1] - points[0][1] == pytest.approx(-300)
    # 逐段时长：起步快、末段慢，松手前再静止，避免惯性多滚。
    assert isinstance(recorded["duration"], list)
    assert recorded["duration"][-1] > recorded["duration"][0]
    assert recorded["settle"] > 0


def test_background_team_scroll_borrows_the_cursor():
    """后台模式列表滚动必须借用真实光标，纯定向事件不会让列表滚动。

    实测日志 "列表位移 -0.02 行"：点击能生效，但纯 PID 拖拽对列表无效，
    只有把系统光标沿路径移动过去才会真正滚动（与地图相机同理）。
    """
    from module.automation.input_handlers.macos.background_input import BackgroundInput

    driver = object.__new__(BackgroundInput)
    recorded = {}
    driver._drag_borrowing_cursor = lambda points, duration, settle: recorded.update(
        points=points, duration=duration, settle=settle
    )

    driver.mouse_swipe_for_team_scroll(100, 700, duration=0.3, dy=-300)

    assert recorded, "后台列表滚动必须借用光标，否则列表位移为 0"
    assert recorded["points"][-1][1] - recorded["points"][0][1] == pytest.approx(-300)
    assert isinstance(recorded["duration"], list)
    assert recorded["settle"] > 0


def test_first_row_click_point_matches_measured_center():
    """首行点击点必须落在实机测得的按钮中心，而不是推算值。

    实机标定（1080p）：按 identify_assets 推算得 y=479.75，而按钮真实中心
    在 y=467，偏下 12.8px（约 0.23 行）。点偏下会让翻页后的点击落到相邻行。
    """
    scale = 1080 / 1440
    position = [1800 - 2150 * scale, 266 + 215 * scale]
    with patch.object(cfg, "set_win_size", 1080):
        correction = team_formation._first_row_y_correction(position, scale)
    click_y = position[1] + 70 * scale + correction
    assert click_y == pytest.approx(team_formation.ORDERED_TEAM_FIRST_ROW_Y, abs=0.5)


def test_scroll_gain_is_within_measured_range():
    """传导率必须是实机测得的量级（0.8-0.9），否则翻页会少滚或多滚。"""
    assert 0.8 <= team_formation.ORDERED_TEAM_ROW_SCROLL_GAIN <= 0.9
