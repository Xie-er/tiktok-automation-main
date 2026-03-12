from lxml import etree
import re
from loguru import logger

class UIParser:
    def __init__(self, xml_content):
        try:
            # 移除 xml 声明，防止 encoding 问题
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            self.root = etree.fromstring(xml_content)
        except Exception as e:
            logger.error(f"Failed to parse XML: {e}")
            self.root = None

    def extract_comments(self, ui_ids):
        """
        提取评论列表
        :param ui_ids: 配置中的 ui_ids 字典
        :return: list of dict [{'user': '...', 'content': '...', 'bounds': '...'}, ...]
        """
        if self.root is None:
            return []

        comments = []
        
        # 获取配置的 ID
        content_id = ui_ids.get('comment_item_text')
        avatar_id = ui_ids.get('comment_item_user_avatar')
        
        if not content_id:
            logger.warning("comment_item_text ID not configured")
            return []

        # 查找所有的评论内容节点
        # resource-id 通常是全名，如 com.ss.android.ugc.aweme:id/content
        # lxml xpath 使用 @resource-id
        
        # 注意：Android dump 的 XML 属性通常是 resource-id
        # 我们构建 xpath
        content_nodes = self.root.xpath(f"//*[@resource-id='{content_id}']")
        
        for node in content_nodes:
            try:
                text = node.get("text", "")
                if not text:
                    continue
                
                # 获取该评论的容器（通常是父节点或父节点的父节点）
                # 为了简单，我们假设 avatar 和 content 是兄弟节点或者在同一个容器下
                # 我们尝试在同级或上级寻找 avatar
                
                # 策略：向上找父节点，然后在父节点下找 avatar
                parent = node.getparent()
                avatar_node = None
                
                # 尝试向上查找 3 层
                for _ in range(3):
                    if parent is None:
                        break
                    # 在当前 parent 下查找 avatar
                    avatars = parent.xpath(f".//*[@resource-id='{avatar_id}']")
                    if avatars:
                        avatar_node = avatars[0]
                        break
                    parent = parent.getparent()
                
                if avatar_node is not None:
                    # 获取 avatar 的 bounds，用于点击
                    avatar_bounds_str = avatar_node.get("bounds")
                    avatar_bounds = self._parse_bounds(avatar_bounds_str)
                    
                    # 同时获取 content 节点的 bounds
                    content_bounds_str = node.get("bounds")
                    content_bounds = self._parse_bounds(content_bounds_str)
                    
                    comment_data = {
                        "content": text,
                        "avatar_bounds": avatar_bounds,
                        "content_bounds": content_bounds,
                        "raw_node": node
                    }
                    comments.append(comment_data)
            except Exception as e:
                logger.warning(f"Error parsing comment node: {e}")
                continue
                
        return comments

    def _parse_bounds(self, bounds_str):
        """
        解析 "[x1,y1][x2,y2]" 格式的坐标
        return: (left, top, right, bottom)
        """
        try:
            matches = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
            if len(matches) == 2:
                x1, y1 = map(int, matches[0])
                x2, y2 = map(int, matches[1])
                return (x1, y1, x2, y2)
        except:
            pass
        return None

    def match_keywords(self, text, keywords):
        """
        检查文本是否包含关键词
        """
        for kw in keywords:
            if kw in text:
                return kw
        return None
