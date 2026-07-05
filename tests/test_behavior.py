"""行为状态机单元测试 (纯 Python, 不需要 opencv/YOLO)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchcat.behavior import BehaviorAnalyzer, State  # noqa: E402
from watchcat.geometry import bbox_anchor, point_in_polygon  # noqa: E402

DT = 0.1  # 模拟 10 fps


def make_analyzer(**kwargs):
    return BehaviorAnalyzer(
        stationary_window=2.0,
        scratch_min_seconds=1.5,
        squat_min_seconds=1.0,
        **kwargs,
    )


def feed_walking(analyzer, t0, seconds, ratio=1.5):
    """模拟猫走动: 中心持续移动, 运动量中等."""
    t = t0
    w, h = 200.0, 200.0 * ratio
    x = 0.0
    state = None
    for _ in range(int(seconds / DT)):
        bbox = (x, 100, x + w, 100 + h)
        state, triggered = analyzer.update(t, bbox, 6.0)
        assert not triggered, "走动中不应触发"
        x += 30  # 每帧移动 30px, 明显超过静止容差
        t += DT
    return t, state


def test_no_cat():
    a = make_analyzer()
    state, triggered = a.update(0.0, None, 0.0)
    assert state == State.NO_CAT
    assert not triggered


def test_walking_never_triggers():
    a = make_analyzer()
    _, state = feed_walking(a, 0.0, 5.0)
    assert state == State.MOVING


def test_scratching_triggers():
    """猫先走动, 然后原地不动 + 高运动量 (扒地) -> 触发."""
    a = make_analyzer(trigger_on="scratch")
    t, _ = feed_walking(a, 0.0, 3.0)

    bbox = (500, 300, 700, 600)  # 固定位置, h/w=1.5 保持正常姿态
    fired = False
    for _ in range(int(6.0 / DT)):
        state, triggered = a.update(t, bbox, 8.0)  # 高运动量
        if triggered:
            fired = True
            assert state == State.SCRATCHING
            break
        t += DT
    assert fired, "持续扒地应当触发警报"


def test_stationary_low_motion_no_trigger():
    """猫只是趴着睡觉 (静止 + 低运动量) -> 不触发."""
    a = make_analyzer(trigger_on="scratch")
    t, _ = feed_walking(a, 0.0, 3.0)

    bbox = (500, 300, 700, 600)  # h/w=1.5 正常姿态
    for _ in range(int(10.0 / DT)):
        state, triggered = a.update(t, bbox, 0.5)
        assert not triggered, "安静趴着不应触发"
        t += DT
    assert state == State.STATIONARY


def test_squat_triggers():
    """先走动建立姿态基线, 再静止蹲下 (高宽比骤降) -> squat 模式触发."""
    a = make_analyzer(trigger_on="squat")
    t, _ = feed_walking(a, 0.0, 5.0, ratio=1.5)  # 正常 h/w = 1.5

    squat_bbox = (500, 400, 740, 640)  # h/w = 1.0 < 0.75*1.5
    fired = False
    for _ in range(int(6.0 / DT)):
        state, triggered = a.update(t, squat_bbox, 1.0)
        if triggered:
            fired = True
            assert state == State.SQUATTING
            break
        t += DT
    assert fired, "蹲姿应当触发警报"


def test_both_mode_requires_scratch_then_squat():
    a = make_analyzer(trigger_on="both")
    t, _ = feed_walking(a, 0.0, 5.0, ratio=1.5)

    # 只蹲不扒: 不触发
    squat_bbox = (500, 400, 740, 640)
    for _ in range(int(4.0 / DT)):
        _, triggered = a.update(t, squat_bbox, 1.0)
        assert not triggered, "both 模式下只蹲不扒不应触发"
        t += DT

    # 扒地 (高运动量)
    for _ in range(int(3.0 / DT)):
        a.update(t, squat_bbox, 8.0)
        t += DT
    # 随后蹲下
    fired = False
    for _ in range(int(3.0 / DT)):
        _, triggered = a.update(t, squat_bbox, 1.0)
        if triggered:
            fired = True
            break
        t += DT
    assert fired, "先扒地后蹲下应当触发"


def test_cat_leaving_resets():
    a = make_analyzer()
    t, _ = feed_walking(a, 0.0, 3.0)
    a.update(t, None, 0.0)
    assert len(a.history) == 0


def test_point_in_polygon():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), square)
    assert not point_in_polygon((15, 5), square)
    assert not point_in_polygon((5, -1), square)
    assert not point_in_polygon((5, 5), [(0, 0), (10, 0)])  # 不足 3 点


def test_bbox_anchor_is_bottom_center():
    assert bbox_anchor((0, 0, 10, 20)) == (5.0, 20)
