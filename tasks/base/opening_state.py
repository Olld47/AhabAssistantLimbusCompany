"""Recognition shared by mirror opening transitions."""
from module.automation import auto


def find_grace_anchor(*, model: str | None = None):
    """定位「星光」页的硬币锚点。

    默认用 ``retina`` 模型：阈值保持 0.90，只抑制 Retina 渲染带来的
    亚像素差异，不改变搜索范围。需要扩大搜索范围时由调用方显式传
    ``model="normal"``。
    """
    return auto.find_element(
        "mirror/road_to_mir/dreaming_star/coins_assets.png",
        model=model or "retina",
        threshold=0.90,
    )
