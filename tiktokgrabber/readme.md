# DouyinLeadMiner - 抖音垂类评论区截流机器人 (Android 真机版)

🚀 **本项目是为 Cursor/Trae 量身定制的系统开发指令集**

## 1. 项目愿景
本项目是一位资深的 Python 自动化开发工程师基于 **Android 真机 (Real Device) + ADB + uiautomator2** 构建的抖音自动化引流工具。

### 核心原则 (Core Principles)
- **纯物理模拟**：严禁使用 Web API 或抓包接口。所有操作必须通过 UI 控件定位和模拟点击完成。
- **高度拟人 (Human-Like)**：所有点击、滑动必须带有随机性（贝塞尔曲线轨迹、随机延迟、随机偏移），绝对禁止机械式操作，以规避抖音的风控系统。
- **模块解耦**：将“业务逻辑（脑）”与“底层驱动（手）”严格分离。UI 元素 ID 必须全部抽取到配置文件中，不能硬编码在代码里。
- **健壮性**：必须处理网络超时、APP 崩溃、弹窗广告等异常情况。

---

## 2. 业务流程 (Business Workflow)
1. **输入**：读取包含目标视频链接的列表。
2. **采集**：自动打开视频，打开评论区，滚动抓取评论。
3. **筛选**：基于正则表达式匹配关键词（如“怎么买”、“价格”、“求带”）。
4. **互动**：
    - 点击命中关键词的用户头像。
    - 进入其个人主页。
    - 随机浏览 3-5 秒。
    - 点击其第一个作品并点赞。
5. **回溯**：安全返回到原来的评论区位置，继续执行任务。

---

## 3. 技术栈 (Tech Stack)
- **语言**: Python 3.10+
- **设备控制**: `uiautomator2` (核心 UI 驱动), `adbutils` (ADB 连接管理)
- **图像/逻辑**: `lxml` (高效解析 UI 结构 XML), `numpy` (生成贝塞尔曲线算法)
- **数据存储**: `sqlite3` (轻量级本地去重), `SQLAlchemy` (可选)
- **配置管理**: `PyYAML` (管理 UI ID 和 策略配置)
- **日志系统**: `loguru` (结构化日志，自动切割)

---

## 4. 系统架构 (System Architecture)

### 4.1 目录结构
```text
DouyinLeadMiner/
├── config/
│   ├── settings.yaml      # 核心配置文件 (UI ID, 阈值, 延迟参数)
│   ├── target_videos.txt  # 任务队列：一行一个视频链接
│   └── device_config.yaml # 设备特定配置 (Serial No, 屏幕分辨率)
├── core/
│   ├── __init__.py
│   ├── driver_wrapper.py  # 【手】封装 uiautomator2，实现拟人化操作
│   ├── controller.py      # 【脑】业务状态机，控制整体流程
│   └── device_mgr.py      # 设备连接、健康检查、ADB 保活
├── data/
│   ├── __init__.py
│   ├── storage.py         # SQLite 数据库操作 (记录已互动的用户)
│   └── history.db         # (Auto-generated) 数据文件
├── utils/
│   ├── __init__.py
│   ├── human_sim.py       # 贝塞尔曲线生成、随机噪音算法
│   ├── parser.py          # XML 解析器 & 关键词正则匹配
│   └── logger.py          # 日志配置
├── main.py                # 程序入口
├── requirements.txt       # 依赖列表
└── README.md              # 说明文档
```

### 4.2 核心模块职责

#### `core/driver_wrapper.py` (执行器 - The Hand)
- `connect()`: 初始化 u2 连接。
- `human_click(element_id)`: 
    - 获取元素 `visible_bounds`。
    - 在范围内生成符合高斯分布的随机坐标 `(x, y)`。
    - 调用 `utils/human_sim` 检查轨迹，执行点击。
- `human_scroll(direction)`: 
    - 生成从 A 点到 B 点的贝塞尔曲线轨迹。
    - 注入微小的抖动 (jitter)。
    - 执行滑动操作。

#### `core/controller.py` (控制器 - The Brain)
- `start_task()`: 读取链接，分发任务。
- `navigate_to_video(url)`: 使用 `adb shell am start` 唤起抖音 Scheme。
- `process_comments()`: 循环抓取、去重、互动、滑动。
- `interact_user(user_element)`: 进入主页 -> 点赞 -> 返回。

#### `utils/human_sim.py` (拟人算法)
- `generate_bezier_trajectory()`: 生成非线性滑动轨迹。
- `random_delay()`: 生成带有长尾效应的随机等待时间。

---

## 5. 配置文件规范 (config/settings.yaml)

```yaml
app:
  package_name: "com.ss.android.ugc.aweme"
  activity: ".main.MainActivity"

# 风控与限制
limits:
  daily_likes: 50             # 每日最大点赞数
  video_process_limit: 30     # 每个视频最多处理多少条评论
  min_sleep: 2                # 最小操作间隔(秒)
  max_sleep: 8                # 最大操作间隔(秒)
  dry_run: false              # 如果为 true，只打印日志，不实际点赞

# 关键词策略
keywords:
  - "多少钱"
  - "怎么买"
  - "求链接"
  - "带带"
  - "价格"

# UI 元素 ID 定义
ui_ids:
  comment_button: "com.ss.android.ugc.aweme:id/gjv"
  comment_list_container: "com.ss.android.ugc.aweme:id/xyz"
  comment_item_user_avatar: "com.ss.android.ugc.aweme:id/user_avatar"
  comment_item_text: "com.ss.android.ugc.aweme:id/content"
  profile_page_works_tab: "text='作品'"
  profile_first_video_cover: "com.ss.android.ugc.aweme:id/cover_img"
  video_detail_like_btn: "com.ss.android.ugc.aweme:id/like_icon"
  video_detail_back_btn: "com.ss.android.ugc.aweme:id/back"
```

---

## 6. 开发路线图 (Development Roadmap)

- [ ] **Phase 1: 基础设施搭建**
    - 创建目录和虚拟环境配置。
    - 编写 `config/settings.yaml`。
    - 实现 `core/device_mgr.py`：设备连接与健康检查。
- [ ] **Phase 2: 驱动与拟人化 (难点)**
    - 实现 `utils/human_sim.py`：贝塞尔曲线算法。
    - 实现 `core/driver_wrapper.py`：封装安全操作。
- [ ] **Phase 3: 读取与解析**
    - 实现导航逻辑与 XML 解析。
    - 验证正则匹配准确性。
- [ ] **Phase 4: 互动业务逻辑**
    - 完成评论抓取与互动闭环。
    - 强化异常处理与回退机制。
- [ ] **Phase 5: 数据库与完善**
    - 接入 `sqlite3` 去重。
    - 全局异常捕获与日志记录。

---

## 7. 常见问题 (FAQ)

- **Q: 如何处理抖音的动态 ID?**
  - **A**: 优先使用 `resource-id`。如果混淆，使用 `description` 或 `text`。最后手段使用 XPath。
- **Q: 如何判断滑动到底部了?**
  - **A**: 比较滑动前后的页面 XML Hash 或最后一条评论内容，连续一致则视为到底。
- **Q: 遇到弹窗广告怎么办?**
  - **A**: 在 `driver_wrapper` 中实现检查器，操作前自动识别并关闭常见弹窗。
