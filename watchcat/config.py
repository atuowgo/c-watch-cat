"""配置加载: YAML 文件 + 默认值深合并."""

import copy

import yaml

DEFAULTS = {
    "camera": {
        "source": 0,       # 摄像头索引 / RTSP 地址 / 视频文件路径
        "width": 1280,
        "height": 720,
    },
    "detection": {
        "model": "yolov8n.pt",
        "confidence": 0.4,
        "imgsz": 640,
        "interval": 5,        # 每 N 帧跑一次 YOLO (帧间沿用上次的框)
        "miss_timeout": 1.5,  # 连续多少秒检测不到猫就认为猫离开了
    },
    "behavior": {
        "stationary_window": 2.5,
        "stationary_tolerance": 0.30,
        "scratch_motion_threshold": 4.0,
        "scratch_min_seconds": 1.5,
        "squat_ratio_drop": 0.75,
        "squat_min_seconds": 1.0,
        "trigger_on": "scratch",  # scratch | squat | both
    },
    "alert": {
        "sound": "sounds/alert.wav",
        "cooldown": 45,
        "repeat": 2,
    },
    "zones": {
        "litter_box": [],  # 猫砂盆区域多边形 [[x, y], ...], 区域内不报警
        "ignore": [],      # 其他忽略区域 (如食盆旁, 猫会做埋食物动作)
    },
    "recording": {
        "enabled": True,
        "dir": "events",
        "pre_seconds": 8,
        "post_seconds": 5,
    },
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path=None):
    user_cfg = {}
    if path:
        with open(path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULTS, user_cfg)
