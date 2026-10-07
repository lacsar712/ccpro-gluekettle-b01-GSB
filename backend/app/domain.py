"""熬锅出胶门槛：最近一次煮胶峰值温度须 ≥ 90℃；巷口熬煮中并存上限。"""

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


def assert_alley_has_room(alley: str, cap: int, used: int) -> None:
    """开关开着且该巷已顶格时，挡住再把锅拨成熬煮中。登峰值、标已出胶不读此限。"""
    if used >= cap:
        raise RuleError(f"{alley}熬煮中已达并存上限 {cap} 口（当前 {used} 口在熬），不能再拨")
