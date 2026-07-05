"""纯 Python 几何工具, 不依赖 opencv, 方便单元测试."""


def point_in_polygon(point, polygon):
    """射线法判断点是否在多边形内.

    point: (x, y)
    polygon: [(x1, y1), (x2, y2), ...] 至少 3 个点
    """
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def bbox_anchor(bbox):
    """取包围框底边中点 (猫爪子接触地面的位置), bbox = (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, y2)


def bbox_center(bbox):
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
