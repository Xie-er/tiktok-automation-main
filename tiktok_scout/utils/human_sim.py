import numpy as np
import random
import time
import math
from loguru import logger

def get_bezier_curve(control_points, num_points=100):
    """
    根据控制点生成贝塞尔曲线轨迹
    :param control_points: 控制点列表 [(x,y), (x,y)...]
    :param num_points: 生成的点数
    :return: 轨迹点列表 [(x,y), (x,y)...]
    """
    n = len(control_points) - 1
    t = np.linspace(0, 1, num_points)
    curve = np.zeros((num_points, 2))
    
    for i in range(num_points):
        point = np.zeros(2)
        for j in range(n + 1):
            # 伯恩斯坦基函数
            bernstein = (math.factorial(n) / 
                        (math.factorial(j) * math.factorial(n - j))) * \
                        (t[i] ** j) * ((1 - t[i]) ** (n - j))
            point += np.array(control_points[j]) * bernstein
        curve[i] = point
        
    return curve.astype(int).tolist()

def generate_human_scroll_trajectory(start_pos, end_pos, duration_ms=500):
    """
    生成拟人化的滑动轨迹
    :param start_pos: (x, y) 起点
    :param end_pos: (x, y) 终点
    :param duration_ms: 滑动耗时
    :return: 轨迹点列表和每个点的间隔时间
    """
    x1, y1 = start_pos
    x2, y2 = end_pos
    
    dist_x = x2 - x1
    dist_y = y2 - y1
    
    # 控制点1：靠近起点
    cx1 = x1 + dist_x * random.uniform(0.1, 0.4) + random.uniform(-50, 50)
    cy1 = y1 + dist_y * random.uniform(0.1, 0.4) + random.uniform(-50, 50)
    
    # 控制点2：靠近终点
    cx2 = x1 + dist_x * random.uniform(0.6, 0.9) + random.uniform(-50, 50)
    cy2 = y1 + dist_y * random.uniform(0.6, 0.9) + random.uniform(-50, 50)
    
    control_points = [(x1, y1), (cx1, cy1), (cx2, cy2), (x2, y2)]
    
    steps = int(duration_ms / 15)
    trajectory = get_bezier_curve(control_points, steps)
    
    return trajectory

def random_delay(min_sec=1.0, max_sec=3.0):
    """
    随机延迟
    """
    delay = random.uniform(min_sec, max_sec)
    if random.random() < 0.1:
        delay += random.uniform(0.5, 1.5)
    
    logger.debug(f"Sleeping for {delay:.2f}s")
    time.sleep(delay)

def get_random_point_in_bounds(bounds):
    """
    在 bounds 区域内生成符合高斯分布的随机点，模拟手指点击
    """
    if isinstance(bounds, dict):
        left, top, right, bottom = bounds['left'], bounds['top'], bounds['right'], bounds['bottom']
    else:
        left, top, right, bottom = bounds
        
    width = right - left
    height = bottom - top
    
    center_x = left + width / 2
    center_y = top + height / 2
    
    x = random.gauss(center_x, width / 6)
    y = random.gauss(center_y, height / 6)
    
    x = max(left, min(x, right))
    y = max(top, min(y, bottom))
    
    return int(x), int(y)
