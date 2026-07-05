"""标定工具: 在摄像头画面上用鼠标画出猫砂盆区域, 保存到 config.yaml.

用法:
    python tools/calibrate_zone.py --config config.yaml [--source 0]

操作:
    鼠标左键     添加多边形顶点
    回车 / n     完成当前多边形, 开始画下一个
    t            切换区域类型 (litter_box <-> ignore)
    u            撤销上一个点
    s            保存到配置文件并退出
    q            不保存退出
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--source", default=None)
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = {}
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    source = args.source
    if source is None:
        source = cfg.get("camera", {}).get("source", 0)
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    cap = cv2.VideoCapture(source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"无法从视频源读取画面: {source}")

    zones = {"litter_box": [], "ignore": []}
    current = []
    zone_type = ["litter_box"]

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            current.append([x, y])

    win = "calibrate (litter_box=orange, ignore=gray)"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)

    colors = {"litter_box": (0, 180, 255), "ignore": (180, 180, 180)}
    print(__doc__)
    while True:
        canvas = frame.copy()
        for zt, polys in zones.items():
            for poly in polys:
                pts = np.array(poly, dtype=np.int32)
                cv2.polylines(canvas, [pts], True, colors[zt], 2)
        if current:
            pts = np.array(current, dtype=np.int32)
            cv2.polylines(canvas, [pts], False, colors[zone_type[0]], 2)
            for p in current:
                cv2.circle(canvas, tuple(p), 4, colors[zone_type[0]], -1)
        cv2.putText(canvas, f"type: {zone_type[0]}  (t switch, s save, q quit)",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    colors[zone_type[0]], 2)
        cv2.imshow(win, canvas)
        key = cv2.waitKey(30) & 0xFF

        if key in (13, ord("n")):  # 回车或 n: 完成当前多边形
            if len(current) >= 3:
                zones[zone_type[0]].append(list(current))
            current.clear()
        elif key == ord("t"):
            zone_type[0] = ("ignore" if zone_type[0] == "litter_box"
                            else "litter_box")
        elif key == ord("u") and current:
            current.pop()
        elif key == ord("s"):
            if len(current) >= 3:
                zones[zone_type[0]].append(list(current))
            cfg.setdefault("zones", {})
            cfg["zones"]["litter_box"] = zones["litter_box"]
            cfg["zones"]["ignore"] = zones["ignore"]
            cfg_path.write_text(
                yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8")
            print(f"已保存 {len(zones['litter_box'])} 个猫砂盆区域, "
                  f"{len(zones['ignore'])} 个忽略区域 -> {cfg_path}")
            break
        elif key == ord("q"):
            print("未保存退出")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
