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
    with patch.object(cfg, "simulator", False):
        for page_index in range(1, page_count + 1):
            top += team_formation._ordered_team_page_swipe_distance(page_index) / row
        offset = team_formation._ordered_team_click_offset(page_count, order)
    return round(top + offset / row)


@pytest.mark.parametrize("num", range(1, team_formation.ORDERED_TEAM_COUNT + 1))
def test_ordered_selection_lands_on_requested_team(num):
    assert _selected_team(num) == num, f"目标 #{num} 实际会选中 #{_selected_team(num)}"


def test_desktop_page_swipe_covers_exactly_one_page():
    """桌面端一页滑动距离必须等于 5 行，否则偏差会逐页累积。"""
    row = team_formation.ORDERED_TEAM_ROW_HEIGHT
    page_size = team_formation.ORDERED_TEAM_PAGE_SIZE
    with patch.object(cfg, "simulator", False):
        first_page = team_formation._ordered_team_page_swipe_distance(1)
    assert first_page == pytest.approx(row * page_size)


def test_last_page_compensates_half_row_only_once():
    """末页的滑动距离与点击偏移不能各补一次半行。"""
    row = team_formation.ORDERED_TEAM_ROW_HEIGHT
    last_index = team_formation.ORDERED_TEAM_LAST_PAGE_INDEX
    with patch.object(cfg, "simulator", False):
        swipe = team_formation._ordered_team_page_swipe_distance(last_index)
        offset = team_formation._ordered_team_click_offset(last_index, 0)
    # 滑动到达的位置 + 点击偏移，正好落在末页第一行。
    assert swipe + offset == pytest.approx(
        team_formation.ORDERED_TEAM_LAST_PAGE_SWIPE_DISTANCE
        + team_formation.ORDERED_TEAM_BOTTOM_PAGE_OFFSET
        + row * 0
    )
