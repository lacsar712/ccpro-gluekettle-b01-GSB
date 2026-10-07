"""熬锅出胶门槛：最近一次煮胶峰值温度须 ≥ 90℃。

入煮门槛：每巷「熬煮中」并存数受巷口配置上限约束（仅冷锅 → 熬煮中时核对）。
登峰值、标已出胶均不读巷上限；邻巷互不影响。
"""

from app.models import Kettle

MIN_PEAK = 90.0


class RuleError(ValueError):
    pass


def latest_peak(kettle: Kettle) -> float | None:
    if not kettle.cooks:
        return None
    latest = max(kettle.cooks, key=lambda c: c.taken_at)
    return latest.peak_temp_c


def assert_can_set_status(kettle: Kettle, new_status: str) -> None:
    allowed = {Kettle.STATUS_COLD, Kettle.STATUS_BOILING, Kettle.STATUS_DRAWN}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status != Kettle.STATUS_DRAWN:
        return
    peak = latest_peak(kettle)
    if peak is None:
        raise RuleError("该锅尚无煮胶峰值，不能出胶")
    if peak < MIN_PEAK:
        raise RuleError(f"最近峰值 {peak}℃ 低于 {MIN_PEAK:.0f}℃，不能出胶")


def assert_can_enter_boiling(
    kettle: Kettle, *, alley_name: str, enabled: bool, cap: int, boiling_count: int
) -> None:
    """冷锅拨成熬煮中时的巷口并存门槛。

    - 仅在冷锅 → 熬煮中时调用（其余流转不读巷上限）；
    - 开关关闭时放行；
    - 开关开启且该巷已达上限，中文挡住。
    """
    if not enabled:
        return
    if boiling_count >= cap:
        raise RuleError(f"{alley_name}熬煮中已达上限（{cap} 口），不能再入煮")
