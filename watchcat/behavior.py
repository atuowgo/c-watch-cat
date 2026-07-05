"""行为识别状态机.

核心思路: 猫在地板上拉屎之前, 会先原地不动地用两只前爪扒拉地板, 然后蹲下.
对应到画面上就是:

1. 猫的包围框中心几乎不移动 (身体没有走动)          -> "静止"
2. 但包围框内部的帧间差分运动量却很高 (前爪在扒地)    -> "扒地"
3. 包围框的高/宽比相对正常姿态明显下降 (蹲下)         -> "蹲姿"

本模块是纯 Python 实现 (不依赖 opencv / numpy), 每帧接收
(时间戳, 猫包围框, 框内运动量) 三个输入, 输出当前状态和是否触发警报.
"""

import statistics
from collections import deque
from enum import Enum


class State(str, Enum):
    NO_CAT = "no_cat"          # 画面里没有猫
    MOVING = "moving"          # 猫在走动, 正常
    STATIONARY = "stationary"  # 猫原地不动, 开始留意
    SCRATCHING = "scratching"  # 身体不动 + 前爪扒地, 高度可疑
    SQUATTING = "squatting"    # 蹲下了, 马上要拉!


class BehaviorAnalyzer:
    def __init__(
        self,
        stationary_window=2.5,       # 判断"静止"需要观察的时长 (秒)
        stationary_tolerance=0.30,   # 中心位移小于 该比例*框宽 视为静止
        scratch_motion_threshold=4.0,  # 框内运动量阈值 (0-255 灰度差均值)
        scratch_min_seconds=1.5,     # 扒地持续多久才确认
        squat_ratio_drop=0.75,       # 高宽比降到正常值的该比例以下视为蹲姿
        squat_min_seconds=1.0,       # 蹲姿持续多久才确认
        trigger_on="scratch",        # scratch | squat | both
        scratch_memory=20.0,         # both 模式下, 扒地之后多少秒内蹲下算连贯
        max_history=600,
    ):
        self.stationary_window = stationary_window
        self.stationary_tolerance = stationary_tolerance
        self.scratch_motion_threshold = scratch_motion_threshold
        self.scratch_min_seconds = scratch_min_seconds
        self.squat_ratio_drop = squat_ratio_drop
        self.squat_min_seconds = squat_min_seconds
        self.trigger_on = trigger_on
        self.scratch_memory = scratch_memory

        # (t, cx, cy, w, h, motion)
        self.history = deque(maxlen=max_history)
        # 猫走动时的 h/w 比例样本, 作为"正常姿态"基线
        self.ratio_baseline = deque(maxlen=300)
        self.last_scratch_time = None

    def reset(self):
        self.history.clear()
        self.last_scratch_time = None

    # ------------------------------------------------------------------

    def update(self, t, bbox, motion):
        """输入一帧观测, 返回 (State, triggered).

        bbox: (x1, y1, x2, y2) 或 None (没检测到猫)
        motion: 框内帧间差分的灰度均值 (0-255), 没有猫时忽略
        """
        if bbox is None:
            self.history.clear()
            return State.NO_CAT, False

        x1, y1, x2, y2 = bbox
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        self.history.append((t, cx, cy, w, h, motion))

        if not self._is_stationary(t, cx, cy, w):
            # 走动中的姿态记入基线, 用于之后对比蹲姿
            self.ratio_baseline.append(h / w)
            return State.MOVING, False

        scratching = self._is_scratching(t)
        squatting = self._is_squatting(t)
        if scratching:
            self.last_scratch_time = t

        if self.trigger_on == "scratch":
            triggered = scratching
        elif self.trigger_on == "squat":
            triggered = squatting
        else:  # both: 先扒地、随后 scratch_memory 秒内蹲下
            recent_scratch = (
                self.last_scratch_time is not None
                and t - self.last_scratch_time <= self.scratch_memory
            )
            triggered = squatting and recent_scratch

        if squatting:
            return State.SQUATTING, triggered
        if scratching:
            return State.SCRATCHING, triggered
        return State.STATIONARY, triggered

    # ------------------------------------------------------------------

    def _samples_within(self, t, seconds):
        return [s for s in self.history if t - s[0] <= seconds]

    def _is_stationary(self, t, cx, cy, w):
        samples = self._samples_within(t, self.stationary_window)
        if len(samples) < 3:
            return False
        # 观测时间跨度要基本覆盖窗口, 避免刚出现的猫被误判为静止
        span = t - samples[0][0]
        if span < 0.8 * self.stationary_window:
            return False
        limit = self.stationary_tolerance * w
        for _, sx, sy, _, _, _ in samples:
            if abs(sx - cx) > limit or abs(sy - cy) > limit:
                return False
        return True

    def _is_scratching(self, t):
        samples = self._samples_within(t, self.scratch_min_seconds)
        if len(samples) < 3:
            return False
        span = t - samples[0][0]
        if span < 0.8 * self.scratch_min_seconds:
            return False
        motions = [s[5] for s in samples]
        # 大部分时间运动量都超过阈值 -> 前爪在持续扒地
        above = sum(1 for m in motions if m >= self.scratch_motion_threshold)
        return above / len(motions) >= 0.6

    def _is_squatting(self, t):
        if len(self.ratio_baseline) < 10:
            return False  # 还没学到这只猫的正常体型
        baseline = statistics.median(self.ratio_baseline)
        samples = self._samples_within(t, self.squat_min_seconds)
        if len(samples) < 3:
            return False
        span = t - samples[0][0]
        if span < 0.8 * self.squat_min_seconds:
            return False
        limit = self.squat_ratio_drop * baseline
        below = sum(1 for s in samples if (s[4] / s[3]) <= limit)
        return below / len(samples) >= 0.7
