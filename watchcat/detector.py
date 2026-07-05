"""基于 YOLO 预训练模型的猫检测 (COCO 数据集自带 cat 类别, 无需自己训练)."""

import logging

log = logging.getLogger("watchcat.detector")

CAT_CLASS_ID = 15  # COCO 类别表中 cat 的编号


class CatDetector:
    def __init__(self, model_path="yolov8n.pt", confidence=0.4, imgsz=640):
        from ultralytics import YOLO  # 延迟导入, 让单元测试不依赖它

        self.model = YOLO(model_path)
        self.confidence = confidence
        self.imgsz = imgsz
        log.info("YOLO 模型已加载: %s", model_path)

    def detect(self, frame):
        """返回置信度最高的猫包围框 (x1, y1, x2, y2), 没有猫则返回 None."""
        results = self.model.predict(
            frame, conf=self.confidence, imgsz=self.imgsz,
            classes=[CAT_CLASS_ID], verbose=False)
        best, best_conf = None, 0.0
        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                if conf > best_conf:
                    best_conf = conf
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    best = (x1, y1, x2, y2)
        return best
