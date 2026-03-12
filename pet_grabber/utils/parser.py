from lxml import etree
import re
from loguru import logger

class UIParser:
    def __init__(self, xml_content):
        try:
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            self.root = etree.fromstring(xml_content)
        except Exception as e:
            logger.error(f"Pet Grabber Failed to parse XML: {e}")
            self.root = None

    def extract_comments(self, ui_ids):
        """提取评论列表"""
        if self.root is None:
            return []

        comments = []
        content_id = ui_ids.get('comment_item_text')
        avatar_id = ui_ids.get('comment_item_user_avatar')
        
        if not content_id:
            return []

        content_nodes = self.root.xpath(f"//*[@resource-id='{content_id}']")
        for node in content_nodes:
            try:
                text = node.get("text", "")
                if not text:
                    continue
                
                parent = node.getparent()
                avatar_node = None
                
                # 策略: 直接通过 resource-id 查找当前评论节点附近的头像
                if avatar_id:
                    p = parent
                    best_candidate = None
                    min_dist = float('inf')
                    content_bounds = self._parse_bounds(node.get("bounds"))
                    
                    # 向上查找 3 层父节点，寻找 ID 匹配的头像
                    for _ in range(3):
                        if p is None: break
                        avatars = p.xpath(f".//*[@resource-id='{avatar_id}']")
                        for av in avatars:
                            av_bounds = self._parse_bounds(av.get("bounds"))
                            if not av_bounds or not content_bounds: continue
                            
                            # 选取与评论内容垂直中心最接近的头像
                            av_center_y = (av_bounds[1] + av_bounds[3]) / 2
                            content_center_y = (content_bounds[1] + content_bounds[3]) / 2
                            dist = abs(av_center_y - content_center_y)
                            
                            if dist < min_dist:
                                min_dist = dist
                                best_candidate = av
                                
                        if best_candidate is not None:
                            avatar_node = best_candidate
                            break
                        p = p.getparent()

                if avatar_node is not None:
                    avatar_bounds_str = avatar_node.get("bounds")
                    avatar_bounds = self._parse_bounds(avatar_bounds_str)
                    content_bounds_str = node.get("bounds")
                    content_bounds = self._parse_bounds(content_bounds_str)
                    
                    # 尝试提取作者名 (通常在内容节点的上方或同级)
                    author = "unknown"
                    p = parent
                    for _ in range(2):
                        if p is None: break
                        # 查找 TextView，且不是内容节点本身
                        text_nodes = p.xpath(".//android.widget.TextView")
                        for tn in text_nodes:
                            t = tn.get("text", "")
                            if t and t != text:
                                author = t
                                break
                        if author != "unknown": break
                        p = p.getparent()

                    comment_data = {
                        "content": text,
                        "author": author,
                        "avatar_bounds": avatar_bounds,
                        "content_bounds": content_bounds,
                        "raw_node": node
                    }
                    comments.append(comment_data)
            except Exception as e:
                logger.warning(f"Error parsing comment node: {e}")
                continue
                
        return comments

    def match_keywords(self, text, keywords):
        """关键词匹配"""
        if not text:
            return None
        for kw in keywords:
            if kw in text:
                return kw
        return None

    def _parse_bounds(self, bounds_str):
        try:
            matches = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
            if len(matches) == 2:
                x1, y1 = map(int, matches[0])
                x2, y2 = map(int, matches[1])
                return (x1, y1, x2, y2)
        except:
            return None
        return None
