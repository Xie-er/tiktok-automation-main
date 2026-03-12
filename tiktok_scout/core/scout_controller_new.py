import uiautomator2 as u2
import time
from loguru import logger

def start_full_search_flow():
    # 自动探测已连接的设备 (ATX/uiautomator2 核心)
    import adbutils
    devices = adbutils.adb.device_list()
    if not devices:
        logger.error("未发现任何 ADB 设备，请检查连接")
        return
    
    serial = devices[0].serial
    logger.info(f"正在通过 ATX 连接设备: {serial}")
    d = u2.connect(serial)
    
    # 1. 点击搜索图标 (使用 XPath 定位)
    search_xpath = '//*[@resource-id="com.ss.android.ugc.aweme:id/2px"]/android.widget.Button[1]/android.widget.FrameLayout[1]'
    logger.info("步骤1: 点击搜索按钮")
    search_btn = d.xpath(search_xpath)
    if search_btn.exists:
        search_btn.click()
        time.sleep(2)
    else:
        logger.error("未找到搜索按钮 XPath")
        return

    # 2. 在搜索框输入“猫”
    input_id = "com.ss.android.ugc.aweme:id/fl_intput_hint_container"
    logger.info("步骤2: 定位并输入关键词")
    search_input = d(resourceId=input_id)
    if search_input.exists(timeout=5):
        search_input.click() # 激活
        time.sleep(1)
        
        # 使用 ATX 提供的强制输入法模式 (FastInput)
        d.set_fastinput_ime(True)
        # 先清除可能存在的默认文字，再输入
        d.clear_text() 
        d.send_keys("猫")
        d.set_fastinput_ime(False)
        logger.success("输入成功")
        time.sleep(1)
    else:
        logger.error("未找到搜索框")
        return

    # 3. 点击最后的搜索确认按钮
    confirm_id = "com.ss.android.ugc.aweme:id/43u"
    logger.info("步骤3: 点击确认搜索")
    search_confirm_btn = d(resourceId=confirm_id)
    if search_confirm_btn.exists(timeout=3):
        search_confirm_btn.click()
        logger.success("成功点击确认搜索按钮")
        time.sleep(5) # 等待搜索结果加载
        
        # 4. 点击“视频”页签
        logger.info(f"步骤4: 正在定位视频页签 (使用 instance 索引)")
        # 方案 A: 使用 resourceId + instance(1) 索引 (0是综合, 1是视频, 2是用户...)
        video_tab = d(resourceId="com.ss.android.ugc.aweme:id/yvu", instance=1)
        
        if video_tab.exists(timeout=5):
            video_tab.click()
            logger.success("成功通过 instance 索引切换到视频页签")
        else:
            # 方案 B: 兜底使用层级 XPath
            logger.info("Instance 定位失败，尝试使用层级 XPath 匹配")
            video_xpath = '//*[@resource-id="com.ss.android.ugc.aweme:id/wlv"]//android.widget.LinearLayout[1]/*[2]'
            video_tab_xpath = d.xpath(video_xpath)
            if video_tab_xpath.exists:
                video_tab_xpath.click()
                logger.success("成功通过层级 XPath 切换到视频页签")
            else:
                # 方案 C: 终极兜底，直接找文本为“视频”的节点
                video_tab_text = d(text="视频")
                if video_tab_text.exists(timeout=3):
                    video_tab_text.click()
                    logger.success("成功通过文本点击视频页签")
                else:
                    logger.error("所有定位方案均失败")
        
        # 5. 点击筛选、选择最新发布、再次点击筛选退出
        filter_btn_id = "com.ss.android.ugc.aweme:id/iwu"
        latest_btn_id = "com.ss.android.ugc.aweme:id/vao"
        
        logger.info("步骤5: 开始筛选操作")
        
        # 5.1 点击筛选按钮
        filter_btn = d(resourceId=filter_btn_id)
        if filter_btn.exists(timeout=5):
            filter_btn.click()
            logger.success("成功点击筛选按钮")
            time.sleep(2)
            
            # 5.2 点击“最新发布”按钮
            logger.info("正在定位‘最新发布’按钮")
            latest_btn = d(text="最新发布")
            
            if not latest_btn.exists:
                latest_btn = d(resourceId=latest_btn_id, instance=1)
            
            if latest_btn.exists(timeout=5):
                latest_btn.click()
                logger.success("成功选择‘最新发布’")
                time.sleep(1)
                
                # 5.3 再次点击筛选按钮退出
                # 【优化】不再主动点击筛选按钮退出，而是点击屏幕下方的视频区域（或空白处）来强制关闭
                logger.info("尝试通过点击视频区域强制关闭筛选面板")
                d.click(0.5, 0.8) # 点击屏幕下方 80% 的位置，通常是视频列表区域
                time.sleep(2)
                
                # 再次检查，如果面板还在，尝试按返回键
                if d(text="筛选").exists or d(text="最新发布").exists:
                    logger.info("筛选面板仍未关闭，尝试发送返回键")
                    d.press("back")
                    time.sleep(2)
            else:
                logger.error(f"未找到‘最新发布’按钮")
        else:
            logger.error(f"未找到筛选按钮: {filter_btn_id}")
        
        # 6. 点击第一个视频
        video_item_id = "com.ss.android.ugc.aweme:id/db_"
        logger.info("步骤6: 正在点击第一个视频")
        
        # 使用 instance=0 明确指定点击第一个匹配到的视频
        first_video = d(resourceId=video_item_id, instance=0)
        if first_video.exists(timeout=5):
            first_video.click()
            logger.success("成功点击第一个视频")
            time.sleep(3) # 等待视频界面加载
            
            # 无限循环复制视频链接，支持 Ctrl+C 停止
            video_count = 0
            logger.info("进入无限循环模式，按 Ctrl+C 可停止程序")
            
            try:
                while True:
                    video_count += 1
                    logger.info(f"--- 正在处理第 {video_count} 个视频 ---")
                    
                    # 7. 点击分享按钮
                    share_btn_id = "com.ss.android.ugc.aweme:id/zop"
                    logger.info(f"步骤7: 正在点击分享按钮: {share_btn_id}")
                    share_btn = d(resourceId=share_btn_id)
                    
                    if share_btn.exists(timeout=5):
                        share_btn.click()
                        logger.success("成功点击分享按钮")
                        time.sleep(2) # 等待分享面板弹出
                        
                        # 8. 在分享容器中左划寻找并点击“复制链接”
                        container_id = "com.ss.android.ugc.aweme:id/function_container"
                        logger.info("步骤8: 正在分享容器中寻找‘复制链接’")
                        container = d(resourceId=container_id)
                        
                        if container.exists(timeout=5):
                            # 轻微左划
                            bounds = container.info['bounds']
                            left, top, right, bottom = bounds['left'], bounds['top'], bounds['right'], bounds['bottom']
                            center_y = (top + bottom) / 2
                            start_x = right - (right - left) * 0.2
                            end_x = right - (right - left) * 0.5
                            d.swipe(start_x, center_y, end_x, center_y, duration=0.2)
                            time.sleep(1)
                            
                            # 寻找“复制链接”
                            copy_link_btn = d(text="复制链接")
                            if not copy_link_btn.exists:
                                copy_link_btn = d(text="分享链接")
                                
                            if copy_link_btn.exists(timeout=5):
                                copy_link_btn.click()
                                logger.success(f"成功复制第 {video_count} 个视频链接")
                                time.sleep(2)
                                
                                # 复制成功后，明确执行一次返回操作，退出分享界面回到视频播放器
                                logger.info("正在退出分享界面...")
                                d.press("back")
                                time.sleep(1)
                            else:
                                logger.error("未找到‘复制链接’按钮")
                                # 如果没找到，尝试按返回键关闭分享面板
                                d.press("back")
                        else:
                            logger.error(f"未找到分享容器")
                            d.press("back")
                    else:
                        logger.error(f"未找到分享按钮")
                    
                    # 9. 准备处理下一个视频：向上划动进入下一个视频
                    # 再次检查分享面板是否还在（作为兜底）
                    container_id = "com.ss.android.ugc.aweme:id/function_container"
                    if d(resourceId=container_id).exists:
                        logger.info("分享面板仍未关闭，再次尝试手动退出")
                        d.press("back")
                        time.sleep(1)

                    logger.info("正在向上划动切换到下一个视频...")
                    # 确保在视频播放器界面进行滑动
                    d.swipe(0.5, 0.8, 0.5, 0.2, duration=0.2)
                    time.sleep(2) # 等待下一个视频加载
            
            except KeyboardInterrupt:
                logger.warning(f"\n程序被手动停止。本次任务共复制了 {video_count} 个视频链接。")
            except Exception as e:
                logger.error(f"程序运行出错: {e}")
        else:
            logger.error(f"未找到视频列表项: {video_item_id}")
            
    else:
        logger.warning("未找到确认按钮，尝试发送回车")
        d.send_action("search")

if __name__ == "__main__":
    start_full_search_flow()
