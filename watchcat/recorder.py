"""事件录像: 维护滚动缓冲, 触发时保存事件前后的视频片段和快照."""

import logging
import time
from collections import deque
from pathlib import Path

import cv2

log = logging.getLogger("watchcat.recorder")


class EventRecorder:
    def __init__(self, out_dir="events", fps=15.0,
                 pre_seconds=8.0, post_seconds=5.0, enabled=True):
        self.out_dir = Path(out_dir)
        self.fps = max(1.0, fps)
        self.pre_seconds = pre_seconds
        self.post_seconds = post_seconds
        self.enabled = enabled
        self.buffer = deque()  # (t, frame)
        self._writer = None
        self._writer_end = 0.0

    def push(self, t, frame):
        if not self.enabled:
            return
        self.buffer.append((t, frame))
        cutoff = t - self.pre_seconds
        while self.buffer and self.buffer[0][0] < cutoff:
            self.buffer.popleft()

        if self._writer is not None:
            self._writer.write(frame)
            if t >= self._writer_end:
                self._writer.release()
                self._writer = None
                log.info("事件录像已保存")

    def trigger(self, t, frame):
        """触发事件: 保存快照, 并把缓冲里的画面写入新视频."""
        if not self.enabled:
            return None
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(t))
        event_dir = self.out_dir / stamp
        event_dir.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(event_dir / "snapshot.jpg"), frame)

        if self._writer is None and self.buffer:
            h, w = self.buffer[0][1].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(
                str(event_dir / "clip.mp4"), fourcc, self.fps, (w, h))
            for _, f in self.buffer:
                self._writer.write(f)
            self._writer_end = t + self.post_seconds
        else:
            # 已有录像在进行, 只是延长结束时间
            self._writer_end = t + self.post_seconds
        return event_dir

    def close(self):
        if self._writer is not None:
            self._writer.release()
            self._writer = None
