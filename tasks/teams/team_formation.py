import re
from collections import Counter
from math import ceil
from statistics import median
from time import sleep

import numpy as np

from module.automation import auto
from module.automation.input_handlers.macos.playcover_control import PLAYCOVER_SIMULATOR_TYPE
from module.config import cfg
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log

NAMED_TEAM_PAGE_SWIPE_DISTANCE = 385
TEAM_LIST_RESET_BOTTOM_MARGIN = 60
ORDERED_TEAM_PAGE_SIZE = 5
ORDERED_TEAM_COUNT = 40
ORDERED_TEAM_VISIBLE_ROWS = 6
ORDERED_TEAM_ROW_HEIGHT = 72.5
SIMULATOR_ORDERED_TEAM_PAGE_SWIPE_DISTANCE = 375
PLAYCOVER_ORDERED_TEAM_PAGE_SWIPE_DISTANCE = 381
"""PlayCover(MaaTools) 触屏拖动的滚动传导约 0.96 且有固定损耗，按 5 行实测补偿的距离。"""
TEAM_LIST_VIEW_STABLE_THRESHOLD = 2.0
"""列表区域相邻两次下拉的灰度平均差低于该值时，判定已滚到顶部。"""

# 2026-11 实机标定（1920x1080 截图空间，CrossOver 后台模式）：
# - 行距实测 54.0-54.4px，与 ORDERED_TEAM_ROW_HEIGHT*scale(54.375) 一致；
# - 列表首行按钮中心在 y=467，而按 identify_assets 推算得到 479.75，
#   即点击点比真实行中心低约 12.8px（0.23 行），翻页越多越容易点错行；
# - 拖动距离只有约 0.8-0.9 传导成滚动（请求 5 行实际约 4 行），
#   因此按行距算出的距离需要放大，才能让"翻一页"真的前进一页。
ORDERED_TEAM_FIRST_ROW_Y = 467.0
"""列表第一行按钮中心在 1920x1080 截图中的 y。"""
ORDERED_TEAM_ROW_SCROLL_GAIN = 0.85
"""拖动距离传导成滚动的比例（实测 0.8-0.9，取中值偏保守）。"""
ORDERED_TEAM_LAST_PAGE_INDEX = (ORDERED_TEAM_COUNT - 1) // ORDERED_TEAM_PAGE_SIZE
ORDERED_TEAM_LAST_PAGE_START = ORDERED_TEAM_COUNT - ORDERED_TEAM_VISIBLE_ROWS + 1
ORDERED_TEAM_BOTTOM_PAGE_OFFSET = ORDERED_TEAM_ROW_HEIGHT / 2
ORDERED_TEAM_PAGE_SWIPE_DISTANCE = ORDERED_TEAM_ROW_HEIGHT * ORDERED_TEAM_PAGE_SIZE
ORDERED_TEAM_LAST_PAGE_SWIPE_DISTANCE = (
    (
        ORDERED_TEAM_LAST_PAGE_START
        - 1
        - (ORDERED_TEAM_LAST_PAGE_INDEX - 1) * ORDERED_TEAM_PAGE_SIZE
    )
    * ORDERED_TEAM_ROW_HEIGHT
    - ORDERED_TEAM_BOTTOM_PAGE_OFFSET
)


# 清队
def clean_team():
    scale = cfg.set_win_size / 1440
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.click_element("teams/clear_selection_confirm_assets.png"):
            break
        if (identify_position := auto.find_element("teams/identify_assets.png")) and auto.mouse_action_with_pos(
            [identify_position[0], identify_position[1] + 600 * scale]
        ):
            sleep(0.5)
            auto.take_screenshot()
            if auto.find_element("teams/clear_selection_confirm_assets.png") is None:
                break


@begin_and_finish_time_log(task_name="罪人编队")
# 编队
def team_formation(sinner_team):
    scale = cfg.set_win_size / 1440

    clean_team()
    while auto.take_screenshot() is None:
        continue
    if reset_team := auto.find_element("teams/identify_assets.png"):
        first_sinner = [reset_team[0] - 1800 * scale, reset_team[1] + 130 * scale]
    else:
        log.error("无法找到罪人编队的起始位置")
        return
    sleep(0.5)

    for i in range(1, 13):
        if i in sinner_team:
            sinner = sinner_team.index(i)
        else:
            return
        if sinner <= 5:
            auto.mouse_click(first_sinner[0] + 270 * sinner * scale, first_sinner[1])
        else:
            auto.mouse_click(
                first_sinner[0] + 270 * (sinner - 6) * scale,
                first_sinner[1] + 500 * scale,
            )
        sleep(cfg.mouse_action_interval)


def _ordered_team_page_swipe_distance(page_index=None):
    if not cfg.simulator:
        # 桌面端（Windows / macOS）：按行高换算一页的距离，再按实测传导率放大。
        # 拖动只有约 0.85 传导成滚动，若直接发"5 行"的距离，实际只前进约 4 行，
        # 翻页越多偏差越大（实测目标 #6 会落到相邻队伍）。
        if page_index == ORDERED_TEAM_LAST_PAGE_INDEX:
            # 末页只要滑到 #35 即可，不扣半行：半行补偿只用于触屏模拟器。
            raw = ORDERED_TEAM_LAST_PAGE_SWIPE_DISTANCE + ORDERED_TEAM_BOTTOM_PAGE_OFFSET
        else:
            raw = ORDERED_TEAM_PAGE_SWIPE_DISTANCE
        return raw / ORDERED_TEAM_ROW_SCROLL_GAIN
    simulator_type = getattr(cfg, "simulator_type", 10)
    if simulator_type == 0:
        if page_index == ORDERED_TEAM_LAST_PAGE_INDEX:
            return ORDERED_TEAM_LAST_PAGE_SWIPE_DISTANCE
        return ORDERED_TEAM_PAGE_SWIPE_DISTANCE
    if simulator_type == PLAYCOVER_SIMULATOR_TYPE:
        return PLAYCOVER_ORDERED_TEAM_PAGE_SWIPE_DISTANCE
    return SIMULATOR_ORDERED_TEAM_PAGE_SWIPE_DISTANCE


def _first_row_y_correction(position, scale):
    """返回首行点击点需要施加的 y 偏移（内容坐标）。

    代码按 identify_assets 推算出的首行位置（position[1] + 70*scale）比实测的
    行中心低约 12.8px。这里以 1080p 标定值为准，用当前窗口几何的推算值做差，
    避免把标定值写死成只对 1080p 有效。
    """
    assumed_1080 = 266 + 215 * (1080 / 1440) + 70 * (1080 / 1440)
    correction_1080 = ORDERED_TEAM_FIRST_ROW_Y - assumed_1080
    # 标定值基于 1080p 截图坐标；其他窗口尺寸按同一比例缩放。
    return correction_1080 * (cfg.set_win_size / 1080)


def _team_list_reset_swipe_distance(start_y, window_height, scale):
    """Return a downward reset distance whose endpoint stays inside the client."""
    return max(0, window_height - start_y - TEAM_LIST_RESET_BOTTOM_MARGIN * scale)


def _team_list_reset_swipe_count(reset_distance, scale):
    """Return enough reset swipes to cover all 40 rows from the bottom."""
    scroll_extent = (
        (ORDERED_TEAM_LAST_PAGE_START - 1) * ORDERED_TEAM_ROW_HEIGHT
        - ORDERED_TEAM_BOTTOM_PAGE_OFFSET
    ) * scale
    return ceil(scroll_extent / max(reset_distance, 1))


def _team_list_view_bbox(position, scale):
    """编队列表所在区域（x1, y1, x2, y2），用于判断列表是否已经滚到顶部。"""
    return (
        0,
        int(position[1]),
        int(position[0] + 130 * scale),
        int(position[1] + 600 * scale),
    )


def _team_list_view_unchanged(previous_view, current_view) -> bool:
    """两次下拉后列表可视内容是否不再变化（已在最顶端，下拉被夹住）。"""
    if previous_view is None or previous_view.shape != current_view.shape:
        return False
    return float(np.abs(previous_view - current_view).mean()) < TEAM_LIST_VIEW_STABLE_THRESHOLD


def _reset_team_list_to_top(my_position, reset_distance, view_bbox):
    """反复下拉直到列表不再变化，保证后续按序号定位是从最上面第 1 队开始数。

    打开界面时游戏会把列表滚到当前所选队伍附近，只有先回到最顶端，"第 n 个队伍"才是
    从最上面数起的第 n 行。拖动距离只有一部分传导成滚动（比例随平台/手势变化），按几何
    距离算出的次数会不够，列表停在当前队伍附近，序号就被当成"从当前队伍数起"；多拉几次
    没有副作用（到顶部后会被夹住），所以以下拉后列表是否还在变化为准。
    """
    max_swipes = _team_list_reset_swipe_count(reset_distance, 1) * 3
    previous_view = None
    for _ in range(max_swipes):
        auto.mouse_swipe_for_team_scroll(my_position[0], my_position[1], dy=reset_distance, duration=0.3)
        sleep(0.4)
        while auto.take_screenshot() is None:
            continue
        current_view = np.asarray(auto.screenshot.convert("L").crop(view_bbox), dtype=np.int16)
        if _team_list_view_unchanged(previous_view, current_view):
            break
        previous_view = current_view
    sleep(0.35)


def _ordered_team_location(num):
    page_count = (num - 1) // ORDERED_TEAM_PAGE_SIZE
    logical_page_start = page_count * ORDERED_TEAM_PAGE_SIZE + 1
    visible_page_start = min(logical_page_start, ORDERED_TEAM_LAST_PAGE_START)
    return page_count, num - visible_page_start


def _ordered_team_click_offset(page_count, team_order):
    offset = ORDERED_TEAM_ROW_HEIGHT * team_order
    # 末页的滑动距离已经扣掉半行补偿；这里只在模拟器/触屏场景再加回，
    # 桌面端两处都加会引入 0.5 行取整抖动（#37/#39 会落到相邻行）。
    if page_count == ORDERED_TEAM_LAST_PAGE_INDEX and cfg.simulator:
        offset += ORDERED_TEAM_BOTTOM_PAGE_OFFSET
    return offset


_TEAM_ROW = re.compile(r"^(?:T[EF][AL]\w{0,2}S|编队)")


def locate_named_team(num, rows):
    """Find team `num` among OCR rows [(text, (x, y)), ...] of the team list.

    Substring matching clicked TEAMS#13 for team 1, and the selected row was
    read as just "TEAMS". Rows are numbered by position instead: the numbers
    OCR did read (tolerating "#"→"W"/missing) fix the list offset by majority,
    so the target row is found even if its own label was misread.

    Returns ("found", (x, y)), ("up", None), ("down", None) or ("unknown", None).
    """
    rows = sorted(((t.upper().replace(" ", ""), p) for t, p in rows
                   if _TEAM_ROW.match(t.upper().replace(" ", ""))), key=lambda r: r[1][1])
    if len(rows) < 2:
        return "unknown", None
    gaps = [b[1][1] - a[1][1] for a, b in zip(rows, rows[1:]) if b[1][1] - a[1][1] > 10]
    if not gaps:
        return "unknown", None
    spacing = median(gaps)
    top = rows[0][1][1]
    offsets = Counter()
    for text, (_, y) in rows:
        if m := re.search(r"(\d+)$", text):
            offsets[int(m.group(1)) - round((y - top) / spacing)] += 1
    if not offsets:
        return "unknown", None
    first, votes = offsets.most_common(1)[0]
    if votes < 2:
        return "unknown", None
    last = first + round((rows[-1][1][1] - top) / spacing)
    if num < first:
        return "up", None
    if num > last:
        return "down", None
    expected = top + (num - first) * spacing
    text, position = min(rows, key=lambda r: abs(r[1][1] - expected))
    if abs(position[1] - expected) > spacing / 3:
        return "unknown", None
    log.debug(f"队伍 #{num} 按行推算为 {text}，可见范围 #{first}-#{last}")
    return "found", position


@begin_and_finish_time_log(task_name="寻找队伍")
# 找队
def select_battle_team(num):
    scale = cfg.set_win_size / 1440
    my_position = [0, 150 * scale]
    find = False
    while auto.take_screenshot() is None:
        continue
    if auto.find_element("home/first_prompt_assets.png", model="clam") and auto.find_element(
        "home/back_assets.png", model="normal"
    ):
        auto.click_element("home/back_assets.png")
    if identify_position := auto.find_element("teams/identify_assets.png", take_screenshot=True):
        position = [identify_position[0] - 2150 * scale, identify_position[1] + 215 * scale]
        auto.mouse_click(1, 1)
        my_position[0] += position[0]
        my_position[1] += position[1]
        auto.mouse_click(my_position[0], my_position[1])
        sleep(0.5)
        reset_distance = _team_list_reset_swipe_distance(
            my_position[1], cfg.set_win_size, scale
        )
        _reset_team_list_to_top(my_position, reset_distance, _team_list_view_bbox(position, scale))
        # 首行点击点：按 identify_assets 推算会落在真实行中心下方约 0.23 行
        # （实机标定 y=479.75 对应真实中心 467），这里按标定值校正。
        first_position = [position[0], position[1] + 70 * scale + _first_row_y_correction(position, scale)]
        if cfg.select_team_by_order:
            team_range, team_order = _ordered_team_location(num)
            for page_index in range(1, team_range + 1):
                ordered_page_distance = _ordered_team_page_swipe_distance(page_index)
                auto.mouse_swipe_for_team_scroll(
                    first_position[0],
                    first_position[1] + 375 * scale,
                    dy=-ordered_page_distance * scale,
                    duration=0.3,
                )
                sleep(1)
            auto.mouse_click(
                first_position[0],
                first_position[1]
                + _ordered_team_click_offset(team_range, team_order) * scale,
            )
            log.info(f"成功找到队伍 # {num}")
            sleep(1)
            return True
        else:
            from module.ocr import ocr
            position_bbox = (0, 0, position[0] + 130 * scale, position[1] + 600 * scale)
            for i in range(10):
                while auto.take_screenshot() is None:
                    continue
                result = ocr.run(auto.screenshot.crop(position_bbox))
                rows = [(text, ((box[0][0] + box[2][0]) / 2, (box[0][1] + box[2][1]) / 2))
                        for text, box in zip(result.txts or [], result.boxes if result.boxes is not None else [])]
                where, team_position = locate_named_team(num, rows)
                if where == "found":
                    auto.mouse_click(team_position[0], team_position[1])
                    find = True
                    break
                # Scroll toward the team; unknown pages continue downward as before.
                direction = 1 if where == "up" else -1
                auto.mouse_swipe_for_team_scroll(
                    first_position[0],
                    first_position[1] + 375 * scale,
                    dy=direction * NAMED_TEAM_PAGE_SWIPE_DISTANCE * scale,
                    duration=0.3,
                )
                sleep(1)
                while auto.take_screenshot() is None:
                    continue
            if find:
                msg = f"成功找到队伍 # {num}"
                log.info(msg)
                sleep(1)
                return True
            else:
                msg = f"找不到队伍 # {num}"
                log.info(msg)
                return False


def deal_with_spills():
    import cv2
    import numpy as np

    from module.ocr import ocr
    from utils.image_utils import ImageUtils

    scale = cfg.set_win_size / 1440
    sinner_nums_bbox = ImageUtils.get_bbox(ImageUtils.load_image("battle/normal_to_battle_assets.png"))
    sinner_nums_bbox = (
        sinner_nums_bbox[0],
        sinner_nums_bbox[1] - 115 * scale,
        sinner_nums_bbox[2],
        sinner_nums_bbox[3] - 115 * scale,
    )
    sc = ImageUtils.crop(np.array(auto.screenshot), sinner_nums_bbox)
    sc = cv2.bitwise_not(sc)
    mask = cv2.inRange(sc, 220, 255)
    mask = cv2.bitwise_not(mask)
    background = np.zeros((300, 300), dtype=np.uint8)
    h, w = mask.shape[:2]
    y_off = (300 - h) // 2
    x_off = (300 - w) // 2
    background[y_off : y_off + h, x_off : x_off + w] = mask
    try:
        result = ocr.run(background)
        ocr_result = [result.txts[i] for i in range(len(result.txts))]
        ocr_result = "".join(ocr_result)
        log.debug(f"对于配队人数OCR得到：{ocr_result}")
        if "/" in ocr_result:
            result = ocr_result.split("/")
            result = [i.strip() for i in result]
            import re

            now = int(re.sub(r"\D", "", result[-2]))
            max = int(re.sub(r"\D", "", result[-1]))
            if now > max:
                all_selected = auto.find_element("teams/selected.png", find_type="image_with_multiple_targets")
                kernel = np.ones((3, 3), np.uint8)
                for selected in all_selected:
                    try:
                        order_bbox = (
                            selected[0] - 40 * scale,
                            selected[1] - 120 * scale,
                            selected[0] + 40 * scale,
                            selected[1] - 30 * scale,
                        )
                        sc2 = ImageUtils.crop(np.array(auto.screenshot), order_bbox)
                        background2 = np.zeros((300, 300), dtype=np.uint8)
                        h, w = sc2.shape[:2]
                        y_off = (300 - h) // 2
                        x_off = (300 - w) // 2
                        background2[y_off : y_off + h, x_off : x_off + w] = sc2
                        result = ocr.run(background2)
                        ocr_result = [result.txts[i] for i in range(len(result.txts))]
                        ocr_result = "".join(ocr_result)
                        if ocr_result == "G":
                            ocr_result = "6"
                        if int(ocr_result) == 1:
                            # 再腐蚀 3 次
                            background2 = cv2.erode(background2, kernel, iterations=3)
                            # 再膨胀 2 次
                            background2 = cv2.dilate(background2, kernel, iterations=2)
                            result = ocr.run(background2)
                            ocr_result = [result.txts[i] for i in range(len(result.txts))]
                            ocr_result = "".join(ocr_result)
                        if int(ocr_result) > max:
                            auto.mouse_click(selected[0], selected[1])
                    except:
                        continue
    except:
        pass


@begin_and_finish_time_log(task_name="检查队伍剩余战斗力")
def check_team():
    # 至少还有5人可以战斗
    sinner_nums = [f"{a}/{b}" for b in range(5, 10) for a in range(5, b + 1)]
    if auto.find_element(sinner_nums, find_type="text"):
        return True
    else:
        return False


@begin_and_finish_time_log(task_name="加载编队码")
def load_team_code_in_game(team_code: str) -> bool:
    """在游戏中加载编队码

    依赖 `input_text` 向游戏内输入框输入文本，而触屏设备（PlayCover/MaaTools，见
    `module/automation/input_handlers/macos/playcover_control.py`）没有文本指令，
    该模式下本功能不可用，会返回 False，调用方按当前队伍配置继续（见
    `assets/doc/zh/How_to_use.md` 的 PlayCover 已知缺口）。

    Args:
        team_code: 编队码字符串

    Returns:
        成功返回 True，失败返回 False
    """
    # 验证当前在队伍选择界面
    if not auto.find_element("mirror/road_to_mir/select_team_confirm_assets.png"):
        log.warning("未在队伍选择界面，跳过编队码加载")
        return False

    # 最多重试3次
    max_retries = 3
    for _ in range(1, max_retries + 1):
        # 截图
        while auto.take_screenshot() is None:
            continue

        # 点击队伍代码按钮
        auto.click_element("teams/team_code_assets.png")
        sleep(1)

        # 查找并点击加载编队码按钮
        auto.click_element("teams/load_team_code_button_assets.png", take_screenshot=True)
        sleep(1)

        # 查找根据取消按钮判断输入框是否出现
        if not auto.find_element("teams/team_code_cancel_button_assets.png", take_screenshot=True):
            # 尝试点击取消按钮返回
            auto.mouse_click_blank()
            sleep(1)
            continue

        # 使用 input_text(text) 直接输入编队码
        auto.input_text(team_code)
        sleep(0.5)  # 等待输入完成

        # 点击确认按钮，最多重试 3 次
        for _ in range(3):
            if auto.click_element("teams/team_code_confirm_button_assets.png", take_screenshot=True):
                sleep(1)
            else:
                break

        # 验证返回队伍选择界面
        if auto.find_element("teams/team_code_assets.png", take_screenshot=True):
            return True
        else:
            auto.click_element("teams/team_code_cancel_button_assets.png")
            sleep(1)

    auto.mouse_click(100, 100)  # 点击左上角关闭
    log.warning(f"加载编队码失败，已重试{max_retries}次: {team_code}")
    return False
