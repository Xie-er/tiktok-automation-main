import os
import sys
import uiautomator2 as u2
import time
import re
import yaml
import argparse
import random

# 将项目根目录添加到 python 路径
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from shared_data.xhs_db import xhs_db
from xhs_scout.utils.logger import logger

def load_config():
    """加载采集配置"""
    config_path = os.path.join(os.path.dirname(__file__), "config", "scout_settings.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"keywords": ["宠物猫"]}

def run_scout(args):
    """单次采集任务逻辑"""
    config = load_config()
    keywords = config.get("keywords", ["宠物猫"])
    min_stay = config.get("min_stay", 15)
    max_stay = config.get("max_stay", 20)
    
    if not keywords:
        logger.warning("未配置关键词，使用默认关键词: 宠物猫")
        keywords = ["宠物猫"]
    
    logger.info(f"开始单次采集任务，关键词列表: {keywords}, 停留时间: {min_stay}-{max_stay}s")
    
    # 1. 连接设备
    try:
        if args.serial:
            d = u2.connect(args.serial)
        else:
            import adbutils
            devices = adbutils.adb.device_list()
            if not devices:
                logger.error("未检测到任何 ADB 设备")
                return False
            d = u2.connect(devices[0].serial)
        logger.info(f"已连接设备: {d.serial}")
    except Exception as e:
        logger.error(f"连接设备失败: {str(e)}")
        return False
    
    # 2. 启动小红书
    package_name = "com.xingin.xhs"
    logger.info(f"正在启动小红书: {package_name}")
    d.app_start(package_name, stop=True)
    time.sleep(5)
    
    # 3. 遍历关键词执行搜索和采集
    search_xpath = '//*[@content-desc="搜索"]'
    search_input_xpath = '//*[@text="搜索, "]'
    do_search_xpath = '//*[@text="搜索"]'
    
    window_size = d.window_size()
    center_x = window_size[0] / 2
    SAFE_TOP_BOUNDARY = 450
    SCROLL_COMPENSATION = 60

    for keyword in keywords:
        logger.info(f">>> 开始处理关键词: {keyword} <<<")
        
        # 4.1 进入搜索页并输入关键词
        if not d.xpath(search_input_xpath).exists:
            if d.xpath(search_xpath).exists:
                d.xpath(search_xpath).click()
                time.sleep(2)
        
        if d.xpath(search_input_xpath).exists:
            d.xpath(search_input_xpath).set_text(keyword)
            time.sleep(1)
            d.xpath(do_search_xpath).click()
            time.sleep(3)
        else:
            logger.error(f"无法定位搜索输入框，跳过关键词: {keyword}")
            continue

        # 4.2 筛选设置 (最新、图文、未看过)
        all_btn_xpath = '//*[@text="全部"]'
        if d.xpath(all_btn_xpath).exists:
            d.xpath(all_btn_xpath).click()
            time.sleep(2)
            
            # 筛选按钮 XPaths
            filter_latest = '//*[@resource-id="android:id/content"]/android.view.ViewGroup[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/androidx.recyclerview.widget.RecyclerView[1]/android.widget.LinearLayout[1]/android.view.ViewGroup[1]/android.widget.FrameLayout[2]'
            filter_pic = '//*[@resource-id="android:id/content"]/android.view.ViewGroup[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/androidx.recyclerview.widget.RecyclerView[1]/android.widget.LinearLayout[2]/android.view.ViewGroup[1]/android.widget.FrameLayout[3]'
            filter_not_seen = '//*[@resource-id="android:id/content"]/android.view.ViewGroup[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/androidx.recyclerview.widget.RecyclerView[1]/android.widget.LinearLayout[4]/android.view.ViewGroup[1]/android.widget.FrameLayout[3]'
            collapse_btn = '//*[@resource-id="android:id/content"]/android.view.ViewGroup[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.LinearLayout[2]'
            
            for xpath in [filter_latest, filter_pic, filter_not_seen]:
                el = d.xpath(xpath)
                if el.exists: el.click()
                time.sleep(0.5)
            
            d.xpath(collapse_btn).click()
            time.sleep(2)

        # 4.3 初始滑动
        d.drag(center_x, window_size[1] * 0.7, center_x, window_size[1] * 0.7 - 143, duration=0.5)
        time.sleep(1.5)

        # 4.4 循环采集该关键词下的笔记
        collected_count = 0
        MAX_COLLECT_PER_KEYWORD = 20
        keyword_start_time = time.time()
        MAX_KEYWORD_TIME = 15 * 60

        # 获取任务所属部门
        target_dept = args.dept if args.dept else "xhs_general"
        if not target_dept.startswith("xhs_") and target_dept != "general":
             # 自动补全前缀
             target_dept = f"xhs_{target_dept}"

        while collected_count < MAX_COLLECT_PER_KEYWORD:
            if time.time() - keyword_start_time > MAX_KEYWORD_TIME:
                logger.info(f"关键词 {keyword} 采集超时")
                break

            # A. 加载圈/干扰项检测
            is_loading = False
            loading_els = d.xpath('//androidx.recyclerview.widget.RecyclerView/android.widget.FrameLayout/android.widget.ImageView').all()
            for el in loading_els:
                l_bounds = el.info.get('bounds', {})
                if l_bounds.get('top', 0) > window_size[1] * 0.85:
                    is_loading = True; break
            
            if is_loading:
                d.swipe_points([(center_x, window_size[1]*0.5), (center_x, window_size[1]*0.7), (center_x, window_size[1]*0.5)], duration=0.1)
                time.sleep(2)

            # B. 扫描左侧笔记
            all_potential = d.xpath('//*[contains(@text, " ")]').all()
            left_notes = []
            for el in all_potential:
                info = el.info
                text = info.get('text', '')
                bounds = info.get('bounds', {})
                x = (bounds['left'] + bounds['right']) / 2
                if x < center_x and any('\u4e00' <= char <= '\u9fff' for char in text) and bounds['top'] > SAFE_TOP_BOUNDARY:
                    left_notes.append({'el': el, 'text': text, 'height': bounds['bottom'] - bounds['top'], 'top': bounds['top']})
            
            left_notes.sort(key=lambda x: x['top'])
            if not left_notes:
                d.swipe(center_x, window_size[1]*0.6, center_x, window_size[1]*0.3)
                time.sleep(2); continue

            # C. 采集第一条
            target = left_notes[0]
            logger.info(f"采集: {target['text'][:15]}")
            target['el'].click()
            
            # 随机停留
            stay_time = random.uniform(min_stay, max_stay)
            logger.info(f"详情页停留 {stay_time:.1f} 秒...")
            time.sleep(stay_time)

            # 提取链接
            share_btn = "com.xingin.xhs:id/moreOperateIV"
            if d(resourceId=share_btn).exists:
                d(resourceId=share_btn).click()
                time.sleep(2)
                copy_link = d.xpath('//*[@content-desc="复制链接"]')
                if copy_link.exists:
                    copy_link.click()
                    time.sleep(1)
                    link = re.search(r'https?://[^\s]+', d.clipboard)
                    if link:
                        xhs_db.add_task(url=link.group(0), category="scout_manual", dept=target_dept)
                        collected_count += 1
            
            d.press("back")
            time.sleep(2)

            # D. 步进滑动
            slide_dist = target['height']
            parent_el = d.xpath(f'//*[@text="{target["text"]}"]/parent::*')
            if parent_el.exists:
                p_b = parent_el.info.get('bounds', {})
                slide_dist = p_b['bottom'] - p_b['top']
            
            d.drag(center_x, window_size[1]*0.7, center_x, window_size[1]*0.7 - (slide_dist + SCROLL_COMPENSATION), duration=0.6)
            time.sleep(1.5)

    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial")
    parser.add_argument("--dept", default="xhs_general")
    args = parser.parse_args()

    while True:
        logger.info(">>> 启动新一轮采集周期 <<<")
        start_time = time.time()
        try:
            run_scout(args)
        except Exception as e:
            logger.error(f"采集异常: {e}")
        
        wait = max(0, 30 * 60 - (time.time() - start_time))
        logger.info(f"等待 {wait/60:.1f} 分钟...")
        time.sleep(wait)

if __name__ == "__main__":
    main()
