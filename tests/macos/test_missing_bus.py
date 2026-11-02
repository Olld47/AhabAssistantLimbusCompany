"""找不到巴士时不要盲走，也不要把整次挂机直接结束。

历史行为：认不到巴士就 raise userStopError。由于顶层 my_script_task 会静默
吞掉 userStopError（只存进 self.exception，不写日志），结果是刷牢中途悄悄
退出、日志里没有任何错误提示。现在改为返回空路线，由上层重新截图后重试。
"""

from unittest.mock import patch

from module.automation import auto
from tasks.mirror.search_road import search_road_from_road_map


def test_lost_bus_after_drag_returns_empty_route_without_blind_navigation():
    with patch.object(auto, "click_element", return_value=False), patch.object(
        auto, "find_element", side_effect=[(704, 396), None, None]
    ), patch.object(auto, "get_restore_time", return_value=None), patch.object(
        auto, "mouse_drag_map"
    ) as drag, patch.object(auto, "mouse_to_blank"), patch(
        "tasks.mirror.search_road.sleep"
    ), patch("tasks.base.retry.check_times", return_value=False):
        route, nodes = search_road_from_road_map()

    # 返回空路线（而不是抛异常终止任务）。
    # 拖动只发生在"拖动前还看得到巴士"的居中步骤，属于正常流程；
    # 关键是拖动后丢失巴士时不再继续盲走、也不再抛错终止。
    assert route == []
    assert nodes == []
