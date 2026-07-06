"""标定工具: 在摄像头画面上用鼠标画出猫砂盆区域, 保存到 config.yaml.

用法:
    # 单摄像头 (一期)
    python tools/calibrate_zone.py --config config.yaml

    # 多摄像头组网 (二期): 指定要标定哪个房间的摄像头
    python tools/calibrate_zone.py --config config.yaml --camera living_room

操作:
    鼠标左键     添加多边形顶点
    回车 / n     完成当前多边形, 开始画下一个
    t            切换区域类型 (litter_box <-> ignore)
    u            撤销上一个点
    s            保存到配置文件并退出
    q            不保存退出
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
import yaml


def pick_camera(cfg, camera_name):
    """返回 (视频源, 写回 zones 的回调). 兼容单/多摄像头两种配置写法."""
    cams = cfg.get("cameras") or []
    if cams:
        names = [c.get("name", f"cam{i}") for i, c in enumerate(cams)]
        if camera_name is None:
            if len(cams) == 1:
                idx = 0
            else:
                raise SystemExit(
                    f"配置里有多个摄像头, 请用 --camera 指定一个: {names}")
        else:
            if camera_name not in names:
                raise SystemExit(f"找不到摄像头 '{camera_name}', 可选: {names}")
            idx = names.index(camera_name)

        def save(zones):
            cams[idx]["zones"] = zones
        return cams[idx].get("source", 0), save

    # 单摄像头写法: 顶层 camera + zones
    def save(zones):
        cfg["zones"] = zones
    return cfg.get("camera", {}).get("source", 0), save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--camera", default=None,
                        help="多摄像头配置时, 要标定的摄像头 name")
    parser.add_argument("--source", default=None,
                        help="覆盖视频源 (调试用)")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = {}
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    source, save_zones = pick_camera(cfg, args.camera)
    if args.source is not None:
        source = args.source
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
            save_zones(zones)
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
