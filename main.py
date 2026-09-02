"""
AstrBot 图文帮助菜单插件
使用 Playwright 本地渲染 HTML 生成精美的帮助菜单图片
添加 Native Page 可视化菜单面板，实现秒级修改保存即生效
"""

import errno
import re
import os
import json
import time
import uuid
import hashlib
import base64
import asyncio
from pathlib import Path
from typing import Dict, Any, List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api import logger
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.star_handler import star_handlers_registry
from quart import jsonify, request

from .renderer import HtmlRenderer


class MenuParser:
    """菜单配置解析器"""
    
    # Emoji自动匹配规则
    EMOJI_MAP = {
        '永久闭嘴': '🔇', '彩色幻影坦克': '🌈', '幻影坦克': '👻', '今日小猪': '🐷',
        'ba本周生日': '🎂', 'ba生日': '🎂', '蔚蓝': '🎓', '生日': '🎂', 'jm': '📚', '本子': '📚',
        'qq空间': '🌐', '说说': '💬', '投稿': '📝',
        'galgame': '🎮', '旮旯': '🎮', '作品': '🎬', '角色': '👤', '厂商': '🏢', '出处': '🔎',
        'steam': '🎮', '成就': '🏆', '监控': '📡', '账号': '🪪',
        '亚托莉': '🤖', '萝卜子': '🥕', '巡礼': '🗺️', '打工': '💼', '商店': '🛒', '背包': '🎒',
        '二次元老婆': '💞', '老婆': '💕', '后宫': '👑', '抽卡': '🎴', '结婚': '💍', '离婚': '💔', '许愿': '🌠',
        '集会码': '🏕️', '登记': '📝', '删除': '❌', '清空': '🧹',
        'ai': '🤖', 'gpt': '🤖', 'llm': '🧠', '画图': '🎨', '绘画': '🎨', '充值': '💰', '积分': '💎',
        '对话': '💬', '识图': '🔍', '智能': '🧠', '生图': '🖼️', '文生图': '🖌️', '图生图': '🖼️',
        '原神': '⭐', 'gs': '⭐', '鸣潮': '🌊', '王者': '👑', '三角': '🔫', 'sjz': '🔫',
        '帮助': '📖', 'help': '📖', '钓鱼': '🎣', '赛马': '🐎',
        '投胎': '👶', '轮盘': '🎲', '星期四': '🍗', 'meme': '😂', '表情': '😊',
        '游戏': '🎮', '娱乐': '🎉', '运势': '🔮', '日报': '📰',
        '签到': '✍️', '查询': '🔍', '设置': '⚙️', '管理': '⚙️', '群管': '⚙️',
        '点歌': '🎵', '音乐': '🎶', '视频': '📹', '解析': '🔗', '下载': '📥',
        '分析': '📊', '画像': '👤', '人工': '👨‍💼', '工具': '🔧', '文件': '📁',
        '集会': '🏕️', '祈福': '🙏', '赞': '👍', '简介': '📋',
        '盒': '📦', '坦克': '👻', '扫雷': '💣', '举报': '🚨',
        'cos': '📸', '帅哥': '🧑', '腿': '🦵', '辣妹': '👧', '猫': '🐱',
        '女': '👩', '玉足': '👣', '黑丝': '🖤', 'jk': '👗', '听歌': '🎧',
        '裁剪': '✂️', '转图': '🔄', '小猪': '🐷', '预设': '🎨',
        '闭嘴': '🤐', '说话': '🗣️', '醒醒': '⏰', '使用': '🎁', '搜索': '🔎'
    }
    
    @staticmethod
    def auto_match_emoji(cmd: str, desc: str) -> str:
        """自动匹配emoji图标"""
        text = (cmd + desc).lower()
        for keyword, emoji in MenuParser.EMOJI_MAP.items():
            if keyword in text:
                return emoji
        return '✨'  # 默认图标


@register("astrbot_plugin_helpmenu", "gabriel0721", "HTML渲染帮助菜单插件", "1.0.0")
class HelpMenuPlugin(Star):
    """帮助菜单插件 - 使用 Playwright 本地渲染"""
    
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.command_name = (config.get('command_name', 'help') or 'help').strip() or 'help'
        self.command_aliases = self._parse_command_aliases(config.get('command_aliases', '菜单,帮助'))
        self.command_prefix = config.get('command_prefix', '')
        
        plugin_dir = Path(__file__).parent
        self.plugin_dir = plugin_dir
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_helpmenu")
        self.menu_json_path = self.data_dir / "menu.json"
        self.settings_path = self.data_dir / "settings.json"
        self.icon_dir = self.data_dir / "images" / "icons"
        self.cache_dir = self.data_dir / "cache"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        self.icon_dir.mkdir(parents=True, exist_ok=True)

        # 渲染串行锁：避免多张图同时渲染吃满CPU
        self._render_lock = asyncio.Lock()
        # 前台防连击标记：用户触发的渲染进行中时拦截重复发送
        self._foreground_rendering = False
        # 用户级冷却记录：{user_id: 上次出图时间戳}
        self._last_render_at: Dict[str, float] = {}
        # 菜单成品图缓存（背景确定时）：{缓存key: 图片路径}
        self._image_cache: Dict[str, str] = {}
        # 菜单预渲染池（背景随机时）：后台提前渲染好整张图，触发时秒发
        self._menu_pool: List[str] = []
        self._menu_pool_key: str = ""
        # 已发送的池图，延后到下次触发时才删除，避免与异步发图产生竞争
        self._used_pool_images: List[str] = []
        self._pool_refilling = False
        self._pool_task = None
        self._cleanup_stale_cache_files()
        self._migrate_legacy_data()
        self._migrate_legacy_logo_config()

        # 建立空菜单数据文件以防不存在
        if not self.menu_json_path.exists():
            with open(self.menu_json_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

        self.renderer = HtmlRenderer(str(plugin_dir), str(self.data_dir))
        
        # 注册 Quart 页面端点 API (提供给 WebUI Page 编辑器)
        self.context.register_web_api(
            "/astrbot_plugin_helpmenu/menu",
            self.api_get_menu,
            ["GET"],
            "获取当前全部帮助菜单数据"
        )
        self.context.register_web_api(
            "/astrbot_plugin_helpmenu/menu",
            self.api_save_menu,
            ["POST"],
            "保存全部帮助菜单数据"
        )
        self.context.register_web_api(
            "/astrbot_plugin_helpmenu/icon",
            self.api_upload_icon,
            ["POST"],
            "上传帮助菜单分类或指令Logo"
        )
        self.context.register_web_api(
            "/astrbot_plugin_helpmenu/icon/resolve",
            self.api_resolve_icon,
            ["POST"],
            "解析帮助菜单Logo为可预览数据"
        )
        self.context.register_web_api(
            "/astrbot_plugin_helpmenu/settings",
            self.api_get_settings,
            ["GET"],
            "获取帮助菜单页面设置"
        )
        self.context.register_web_api(
            "/astrbot_plugin_helpmenu/settings/logo",
            self.api_save_header_logo,
            ["POST"],
            "保存帮助菜单顶部Logo"
        )
        self._apply_configured_command()
        logger.info(
            f"帮助菜单触发命令已设置为: {self.command_name}; "
            f"别名: {', '.join(sorted(self.command_aliases)) or '无'}"
        )

        logger.info("帮助菜单插件增强版已加载 (支持 Native Page 可视化编辑 & 无感重载)")

    @staticmethod
    def _parse_command_aliases(raw_aliases) -> set[str]:
        """解析配置中的触发别名，支持逗号、中文逗号、分号、竖线和换行分隔。"""
        if isinstance(raw_aliases, (list, tuple, set)):
            values = raw_aliases
        else:
            values = re.split(r"[,，;；|\n\r]+", str(raw_aliases or ""))
        return {str(item).strip() for item in values if str(item).strip()}

    def get_configured_commands(self) -> List[str]:
        """返回去重后的帮助菜单触发命令列表。"""
        commands = [self.command_name, *sorted(self.command_aliases)]
        result = []
        seen = set()
        for command in commands:
            command = str(command).strip()
            if command and command not in seen:
                result.append(command)
                seen.add(command)
        return result

    def _apply_configured_command(self) -> None:
        """将配置中的主命令和别名同步到 AstrBot 框架指令过滤器。"""
        commands = self.get_configured_commands()
        if not commands:
            logger.warning("帮助菜单触发命令为空，跳过指令同步")
            return

        for handler in star_handlers_registry.get_handlers_by_module_name(self.__module__):
            if handler.handler_name != "menu_cmd":
                continue
            for event_filter in handler.event_filters:
                if isinstance(event_filter, CommandFilter):
                    event_filter.command_name = commands[0]
                    event_filter._original_command_name = commands[0]
                    event_filter.alias = set(commands[1:])
                    event_filter._cmpl_cmd_names = None
                    return
        logger.warning("未找到帮助菜单框架指令过滤器，无法同步触发命令配置")

    @staticmethod
    def _clean_command_prefix(command: str) -> str:
        """剥离菜单维护命令参数中可能携带的常见指令前缀。"""
        command = str(command or "").strip()
        return command[1:] if command.startswith(("~", "～", "/")) else command

    @staticmethod
    def _detect_image_ext(content: bytes) -> str:
        """根据文件签名识别上传图片类型。"""
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if content.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return ".webp"
        return ""

    def _migrate_legacy_data(self):
        """将旧版本保存在插件目录中的可变数据迁移到 data/plugin_data。"""
        legacy_menu = self.plugin_dir / "menu.json"
        default_menu = self.plugin_dir / "default_menu.json"
        if not self.menu_json_path.exists():
            source_menu = legacy_menu if legacy_menu.exists() else default_menu
            if source_menu.exists():
                try:
                    with open(source_menu, "r", encoding="utf-8-sig") as f:
                        menu_data = json.load(f)
                    with open(self.menu_json_path, "w", encoding="utf-8") as f:
                        json.dump(menu_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"已初始化帮助菜单数据到: {self.menu_json_path}")
                except Exception as e:
                    logger.error(f"初始化帮助菜单数据失败: {e}")

        legacy_icon_dir = self.plugin_dir / "images" / "icons"
        if legacy_icon_dir.exists():
            for source in legacy_icon_dir.iterdir():
                if source.name == ".gitkeep" or not source.is_file():
                    continue
                target = self.icon_dir / source.name
                if target.exists():
                    continue
                try:
                    target.write_bytes(source.read_bytes())
                except Exception as e:
                    logger.warning(f"迁移菜单图标失败 {source.name}: {e}")

    def _migrate_legacy_logo_config(self):
        """将旧配置中的 logo_path 迁移为 Native Page 管理的顶部 Logo。"""
        settings = self._load_page_settings()
        if settings.get("header_logo"):
            return
        legacy_logo = str(self.config.get("logo_path", "")).strip()
        if not legacy_logo:
            return
        settings["header_logo"] = legacy_logo
        if self._save_page_settings(settings):
            logger.info("已将旧版 logo_path 迁移为页面管理的顶部 Logo")

    def _data_icon_to_legacy_path(self, icon_path: str) -> str:
        """将 data/plugin_data 中的图标路径转换为兼容 menu.json 的相对路径。"""
        try:
            path = Path(icon_path)
            if path.is_absolute() and path.is_relative_to(self.icon_dir):
                return f"./images/icons/{path.name}"
        except Exception:
            pass
        return icon_path

    def _load_menu_data(self) -> Dict[str, Dict[str, str]]:
        """从 menu.json 实时加载当前菜单配置"""
        if not self.menu_json_path.exists():
            return {}
        try:
            with open(self.menu_json_path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取 menu.json 失败: {e}")
            return {}

    def _save_menu_data(self, data: Dict[str, Dict[str, str]]) -> bool:
        """实时保存当前配置到 menu.json"""
        try:
            with open(self.menu_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except PermissionError as e:
            logger.error(f"保存 menu.json 失败，权限不足: {e}")
            return False
        except OSError as e:
            if e.errno == errno.ENOSPC:
                logger.error(f"保存 menu.json 失败，磁盘空间不足: {e}")
            else:
                logger.error(f"保存 menu.json 失败，文件系统错误: {e}")
            return False

    def _load_page_settings(self) -> Dict[str, Any]:
        """读取通过 Native Page 管理的页面设置。"""
        if not self.settings_path.exists():
            return {"header_logo": ""}
        try:
            with open(self.settings_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"header_logo": ""}
        except Exception as e:
            logger.error(f"读取页面设置失败: {e}")
            return {"header_logo": ""}

    def _save_page_settings(self, data: Dict[str, Any]) -> bool:
        """保存通过 Native Page 管理的页面设置。"""
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except PermissionError as e:
            logger.error(f"保存页面设置失败，权限不足: {e}")
            return False
        except OSError as e:
            if e.errno == errno.ENOSPC:
                logger.error(f"保存页面设置失败，磁盘空间不足: {e}")
            else:
                logger.error(f"保存页面设置失败，文件系统错误: {e}")
            return False

    async def api_get_settings(self):
        """Quart API: 获取页面设置。"""
        try:
            settings = self._load_page_settings()
            logo = str(settings.get("header_logo", "")).strip()
            return jsonify({"success": True, "data": {"header_logo": logo}})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    async def api_save_header_logo(self):
        """Quart API: 上传或清空顶部圆形 Logo。"""
        try:
            payload = await request.get_json(silent=True) or {}
            if payload.get("clear"):
                settings = self._load_page_settings()
                settings["header_logo"] = ""
                if self._save_page_settings(settings):
                    self._invalidate_image_cache()
                    return jsonify({"success": True, "path": ""})
                return jsonify({"success": False, "message": "保存页面设置失败"})

            result = await self._save_uploaded_image("header_logo")
            if not result.get("success"):
                return jsonify(result)

            settings = self._load_page_settings()
            settings["header_logo"] = result["path"]
            if not self._save_page_settings(settings):
                return jsonify({"success": False, "message": "保存页面设置失败"})
            self._invalidate_image_cache()
            return jsonify({"success": True, "path": result["path"]})
        except Exception as e:
            logger.error(f"保存顶部Logo失败: {e}")
            return jsonify({"success": False, "message": str(e)})

    async def api_get_menu(self):
        """Quart API: 获取菜单"""
        try:
            data = self._load_menu_data()
            return jsonify(data)
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    async def api_save_menu(self):
        """Quart API: 覆盖保存菜单"""
        try:
            payload = await request.get_json()
            if not isinstance(payload, dict):
                return jsonify({"success": False, "message": "无效的数据结构，应为键值对"})

            success = self._save_menu_data(payload)
            if success:
                self._invalidate_image_cache()
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "message": "写入 menu.json 失败"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    async def _save_uploaded_image(self, prefix: str = "icon") -> Dict[str, Any]:
        """保存上传图片到持久化图标目录。"""
        max_size = 5 * 1024 * 1024
        content = None

        files = await request.files
        upload = files.get("file") if files else None
        if upload:
            content = upload.read()
        else:
            payload = await request.get_json(silent=True)
            if not isinstance(payload, dict):
                return {"success": False, "message": "未收到图片文件"}
            data_url = payload.get("data") or ""
            if "," in data_url:
                data_url = data_url.split(",", 1)[1]
            try:
                content = base64.b64decode(data_url, validate=True)
            except Exception:
                return {"success": False, "message": "图片数据无效"}

        if not content:
            return {"success": False, "message": "图片内容为空"}
        if len(content) > max_size:
            return {"success": False, "message": "图片不能超过 5MB"}

        ext = self._detect_image_ext(content)
        if not ext:
            return {"success": False, "message": "图片文件签名无效，仅支持 png、jpg、webp、gif 图片"}

        safe_name = f"{prefix}_{uuid.uuid4().hex}{ext}"
        target = self.icon_dir / safe_name
        with open(target, "wb") as f:
            f.write(content)

        return {"success": True, "path": f"./images/icons/{safe_name}"}

    async def api_upload_icon(self):
        """Quart API: 上传分类或指令Logo"""
        try:
            return jsonify(await self._save_uploaded_image("icon"))
        except Exception as e:
            logger.error(f"上传菜单Logo失败: {e}")
            return jsonify({"success": False, "message": str(e)})

    async def api_resolve_icon(self):
        """Quart API: 将图标路径解析成前端可预览的 data URL"""
        try:
            payload = await request.get_json(silent=True) or {}
            icon = str(payload.get("icon", "")).strip()
            if not icon:
                return jsonify({"success": False, "message": "图标路径为空"})
            resolved = self.resolve_icon_path(icon)
            if not resolved:
                return jsonify({"success": False, "message": "图标文件不存在"})
            return jsonify({"success": True, "url": resolved})
        except Exception as e:
            logger.error(f"解析菜单Logo失败: {e}")
            return jsonify({"success": False, "message": str(e)})

    def resolve_icon_path(self, icon_path: str) -> str:
        """解析并将本地或网络图标路径转换为渲染需要的格式（网络URL或Base64）"""
        if not icon_path:
            return ""
        icon_path = icon_path.strip()
        if icon_path.startswith("http://") or icon_path.startswith("https://") or icon_path.startswith("data:"):
            return icon_path
        
        # 尝试使用 html_renderer 提供的 get_logo_base64 转换本地路径
        try:
            b64 = self.renderer.get_logo_base64(icon_path)
            if b64:
                return b64
        except Exception as e:
            logger.error(f"转换本地Logo Base64失败: {e}")
        return icon_path

    def _parse_categories(self, event_prefix: str) -> List[Dict[str, Any]]:
        """实时解析当前 menu.json 并格式化为渲染器所需的数据列表 (支持自定义前缀和图标)"""
        menu_data = self._load_menu_data()
        categories = []

        for category_name, cmd_map in menu_data.items():
            commands = []

            # 1. 解析分类自身的图标
            raw_cat_icon = cmd_map.get("__icon__", "") if isinstance(cmd_map, dict) else ""
            cat_icon = self.resolve_icon_path(raw_cat_icon) if raw_cat_icon else ""

            for cmd_name, cmd_info in cmd_map.items():
                if cmd_name == "__icon__":
                    continue

                # 兼容旧版本纯描述字符串和新版本对象配置
                cmd_desc = ""
                custom_icon_raw = ""
                custom_prefix = None  # None 表示使用默认逻辑

                if isinstance(cmd_info, dict):
                    cmd_desc = cmd_info.get("desc", "")
                    custom_icon_raw = cmd_info.get("icon", "")
                    custom_prefix = cmd_info.get("prefix", None)  # 新增：自定义前缀
                else:
                    cmd_desc = str(cmd_info)

                # 处理前缀逻辑
                cmd_display = cmd_name

                # 如果指定了 prefix 字段
                if custom_prefix is not None:
                    # prefix 为空字符串 = 不要前缀
                    # prefix 为具体字符 = 使用该前缀
                    if custom_prefix:
                        cmd_display = f"{custom_prefix}{cmd_name}"
                    else:
                        cmd_display = cmd_name  # 无前缀
                else:
                    # 未指定 prefix 字段，使用原有逻辑：
                    # 若指令中原先无任何前缀，则自动拼上当前触发此事件的系统前缀
                    if not (cmd_display.startswith("~") or cmd_display.startswith("～") or cmd_display.startswith("/")):
                        cmd_display = f"{event_prefix}{cmd_display}"

                # 如果提供了自定义图标，解析它；否则，自动匹配 emoji 规则
                if custom_icon_raw:
                    icon = self.resolve_icon_path(custom_icon_raw)
                else:
                    icon = MenuParser.auto_match_emoji(cmd_name, cmd_desc)

                commands.append({
                    "cmd": cmd_display,
                    "desc": cmd_desc,
                    "icon": icon
                })

            categories.append({
                "name": category_name,
                "icon": cat_icon,
                "commands": commands
            })

        return categories

    def _render_cache_key(self, categories: List[Dict[str, Any]], filter_cat: str, event_prefix: str) -> str:
        """根据菜单内容与展示配置计算成品图缓存key。任一输入变化即失效。"""
        payload = {
            "menu": categories,
            "filter": filter_cat or "",
            "prefix": event_prefix,
            "title": self.config.get('header_title', ''),
            "subtitle": self.config.get('header_subtitle', ''),
            "footer": self.config.get('footer_text', ''),
            "theme": self.config.get('theme_color', ''),
            "blur": self.config.get('blur_radius', 0),
            "opacity": self.config.get('card_opacity', 10),
            "font": self.config.get('font_file', ''),
            "logo": self._load_page_settings().get("header_logo", ""),
            # 输出格式参与key：切换 png/jpeg 或调质量后旧缓存自动失效
            "fmt": self._image_format(),
            "q": int(self.config.get('image_quality', 90) or 90) if self._image_format() == 'jpeg' else 0,
            # 单文件本地背景是确定性的，可参与缓存；API/随机目录背景不缓存
            "bg": (
                {"single": str(self.config.get('background_image', ''))}
                if not self.config.get('use_api_background', True)
                and Path(str(self.config.get('background_image', ''))).suffix
                else None
            ),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _invalidate_image_cache(self):
        """菜单内容或设置变化后，清空成品图缓存与预渲染池。"""
        for path in self._image_cache.values():
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"清理菜单缓存图失败 {path}: {e}")
        self._image_cache.clear()
        self._drain_menu_pool()

    def _image_format(self) -> str:
        """输出图片格式：jpeg 编码更快、体积更小（默认）；png 无损但更慢。"""
        fmt = str(self.config.get('image_format', 'jpeg') or 'jpeg').lower()
        return 'png' if fmt == 'png' else 'jpeg'

    def _image_ext(self) -> str:
        return '.jpg' if self._image_format() == 'jpeg' else '.png'

    def _cleanup_stale_cache_files(self):
        """清理上次运行残留的池图与成品图缓存（进程重启后内存索引已丢失）。"""
        try:
            for prefix in ("pool_", "menu_"):
                for ext in (".png", ".jpg"):
                    for path in self.cache_dir.glob(f"{prefix}*{ext}"):
                        path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"清理历史菜单缓存失败: {e}")

    def _cleanup_used_pool_images(self):
        """删除上一轮已发送完毕的池图（延后清理，避开发图时序竞争）。"""
        for path in self._used_pool_images:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"清理已用池图失败 {path}: {e}")
        self._used_pool_images.clear()

    def _drain_menu_pool(self):
        """清空预渲染池（菜单内容变化时，池里的旧图已过期）。"""
        for path in self._menu_pool:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"清理预渲染菜单图失败 {path}: {e}")
        self._menu_pool.clear()
        self._menu_pool_key = ""

    async def _render_menu_image(self, categories, filter_cat, output_path=None) -> str:
        """渲染一张菜单图（串行执行，避免并发渲染抢CPU）。"""
        async with self._render_lock:
            render_config = dict(self.config)
            render_config["header_logo"] = self._load_page_settings().get("header_logo", "")
            data = await self.renderer.prepare_menu_data(categories, render_config, filter_cat)
            if filter_cat and not data['categories']:
                return ""
            template_content = self.renderer.load_template("menu.html")
            html_content = self.renderer.render_template(template_content, data)
            return await self.renderer.render_to_image(
                html_content,
                output_path=output_path,
                image_format=self._image_format(),
                quality=int(self.config.get('image_quality', 90) or 90),
            )

    async def _refill_menu_pool(self, cache_key: str, target: int):
        """后台把预渲染池补足到目标数量。整张菜单图提前渲染好，触发时直接秒发。"""
        if self._pool_refilling:
            return
        self._pool_refilling = True
        try:
            while len(self._menu_pool) < target:
                event_prefix = self._get_event_prefix()
                categories = self._parse_categories(event_prefix)
                if not categories:
                    return
                # 菜单在补仓期间被改动过，这批已过期，放弃
                if self._render_cache_key(categories, None, event_prefix) != cache_key:
                    logger.debug("菜单已变更，放弃本轮预渲染补仓")
                    return
                out = self.cache_dir / f"pool_{uuid.uuid4().hex}{self._image_ext()}"
                try:
                    path = await self._render_menu_image(categories, None, str(out))
                except Exception as e:
                    logger.warning(f"预渲染菜单图失败: {e}")
                    return
                if not path:
                    return
                # 渲染期间菜单又变了，丢弃这张
                if self._menu_pool_key and self._menu_pool_key != cache_key:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    return
                self._menu_pool.append(path)
                self._menu_pool_key = cache_key
                logger.debug(f"预渲染菜单图入池（当前{len(self._menu_pool)}张）")
        finally:
            self._pool_refilling = False

    def _schedule_menu_pool_refill(self, cache_key: str, target: int):
        """后台异步补仓预渲染池，不阻塞当前请求。"""
        if self._pool_task and not self._pool_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._pool_task = loop.create_task(self._refill_menu_pool(cache_key, target))

    def _get_event_prefix(self) -> str:
        """获取菜单中展示的指令前缀。"""
        event_prefix = self.command_prefix
        if not event_prefix:
            try:
                event_prefix = self.context.config.command_prefix
            except Exception:
                event_prefix = "~"
        return event_prefix

    @filter.command("help")
    async def menu_cmd(self, event: AstrMessageEvent, message: str = None):
        """生成图文菜单。用法：~help [分类名]"""
        # 用户级冷却检查
        now = time.monotonic()
        cooldown = max(0, int(self.config.get('cooldown_seconds', 60) or 0))
        try:
            user_id = event.get_sender_id() or event.unified_msg_origin
        except Exception:
            user_id = event.unified_msg_origin
        last = self._last_render_at.get(user_id)
        if cooldown > 0 and last is not None:
            remain = int(cooldown - (now - last))
            if remain > 0:
                yield event.plain_result(f"⏰ 帮助菜单冷却中，请 {remain} 秒后再试")
                return

        image_path = None
        keep_image = False
        try:
            event_prefix = self._get_event_prefix()
            categories = self._parse_categories(event_prefix)

            if not categories:
                yield event.plain_result("未配置菜单内容。你可以在后台 Dashboard 的指令菜单管理中快捷创建它。")
                return

            # 处理分类筛选
            filter_cat = event.get_extra("helpmenu_message")
            if filter_cat is None:
                filter_cat = message.strip() if message else None

            cache_key = self._render_cache_key(categories, filter_cat, event_prefix)

            # 1) 成品图缓存命中（背景确定时）：秒发
            cached_path = self._image_cache.get(cache_key)
            if cached_path and os.path.exists(cached_path):
                self._last_render_at[user_id] = time.monotonic()
                logger.debug("菜单成品图缓存命中，直接发送")
                yield event.image_result(cached_path)
                return

            # 2) 预渲染池命中（无分类筛选的完整菜单）：秒发、后台补仓
            pool_size = max(0, int(self.config.get('menu_pool_size', 1) or 0))
            use_pool = not filter_cat and pool_size > 0
            if use_pool:
                if self._menu_pool_key and self._menu_pool_key != cache_key:
                    self._drain_menu_pool()  # 菜单已变更，旧图作废
                while self._menu_pool:
                    candidate = self._menu_pool.pop(0)
                    if not os.path.exists(candidate):
                        continue
                    # 已用过的池图延后清理：避免在消息真正发出前删掉文件
                    self._cleanup_used_pool_images()
                    self._used_pool_images.append(candidate)
                    self._last_render_at[user_id] = time.monotonic()
                    self._schedule_menu_pool_refill(cache_key, pool_size)
                    logger.debug(f"预渲染池命中，秒发（剩余{len(self._menu_pool)}张）")
                    yield event.image_result(candidate)
                    return

            # 3) 池空/带筛选：现场渲染。此时才需要防连击拦截
            if self._foreground_rendering:
                yield event.plain_result("⏳ 帮助菜单正在生成中，请勿重复发送")
                return

            self._foreground_rendering = True
            try:
                image_path = await self._render_menu_image(categories, filter_cat)
                if not image_path:
                    yield event.plain_result(f"未找到分类：{filter_cat}")
                    return
            finally:
                self._foreground_rendering = False

            # 背景确定（本地单图）时缓存成品图，后续命中秒发
            if self._is_bg_deterministic():
                cached_file = self.cache_dir / f"menu_{cache_key[:16]}{self._image_ext()}"
                try:
                    os.replace(image_path, cached_file)
                    image_path = str(cached_file)
                    self._image_cache[cache_key] = str(cached_file)
                    while len(self._image_cache) > 8:
                        oldest_key = next(iter(self._image_cache))
                        oldest_path = self._image_cache.pop(oldest_key)
                        if oldest_path != image_path and os.path.exists(oldest_path):
                            try:
                                os.remove(oldest_path)
                            except OSError:
                                pass
                    keep_image = True
                except OSError as e:
                    logger.warning(f"保存菜单缓存图失败: {e}")

            # 记录冷却起点并预热池，让下一次触发能秒发
            self._last_render_at[user_id] = time.monotonic()
            if len(self._last_render_at) > 512:
                cutoff = time.monotonic() - cooldown - 60
                self._last_render_at = {
                    uid: ts for uid, ts in self._last_render_at.items() if ts > cutoff
                }
            if use_pool:
                self._schedule_menu_pool_refill(cache_key, pool_size)

            yield event.image_result(image_path)

        except FileNotFoundError as e:
            logger.error(f"模板文件不存在: {e}")
            yield event.plain_result("❌ 菜单模板文件不存在，请检查插件安装是否完整")
        except Exception as e:
            logger.exception(f"生成菜单失败: {e}")
            yield event.plain_result(f"❌ 生成菜单出错: {str(e)}")
        finally:
            # 清理临时图片（缓存图与池图保留复用）
            if image_path and not keep_image and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.debug(f"已清理临时图片文件: {image_path}")
                except Exception as e:
                    logger.warning(f"清理临时图片文件失败: {e}")

    def _is_bg_deterministic(self) -> bool:
        """背景是否确定（本地单张图片）。随机背景不参与成品图缓存。"""
        if self.config.get('use_api_background', True):
            return False
        bg = str(self.config.get('background_image', '') or '')
        return bool(Path(bg).suffix)
    
    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("添加菜单项")
    async def add_menu_item(self, event: AstrMessageEvent, category: str, command: str, description: str):
        """添加菜单项。用法：~添加菜单项 <分类名> <指令名> <描述>"""
        menu_data = self._load_menu_data()
        
        clean_cmd = self._clean_command_prefix(command)
            
        if category not in menu_data:
            menu_data[category] = {}
            
        if clean_cmd in menu_data[category] and menu_data[category][clean_cmd] == description:
            yield event.plain_result(f"菜单项 '{command}' 已经存在于分类 '{category}' 中。")
            return

        menu_data[category][clean_cmd] = description
        if self._save_menu_data(menu_data):
            self._invalidate_image_cache()
            yield event.plain_result(f"🎉 成功添加菜单项并保存：{category} :: {command} :: {description}。即时生效！")
        else:
            yield event.plain_result("❌ 写入配置失败，请检查文件权限。")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删除菜单项")
    async def del_menu_item(self, event: AstrMessageEvent, command_to_delete: str):
        """删除菜单项。用法：~删除菜单项 <指令名>"""
        menu_data = self._load_menu_data()
        
        clean_cmd = self._clean_command_prefix(command_to_delete)
            
        found = False
        for category_name, cmd_map in list(menu_data.items()):
            if clean_cmd in cmd_map:
                del cmd_map[clean_cmd]
                found = True
                # 若分类空了则移去整个分类
                if not cmd_map:
                    del menu_data[category_name]
                break

        if found:
            if self._save_menu_data(menu_data):
                self._invalidate_image_cache()
                yield event.plain_result(f"🎉 成功删除菜单项 '{command_to_delete}'。即时生效！")
            else:
                yield event.plain_result("❌ 写入配置失败，请检查文件权限。")
        else:
            yield event.plain_result(f"未找到指令名为 '{command_to_delete}' 的菜单项。")
            
    @filter.on_astrbot_loaded()
    async def prewarm_menu_pool(self):
        """框架加载完成后预热：后台先渲染好菜单图，让首次触发也能秒发。"""
        pool_size = max(0, int(self.config.get('menu_pool_size', 1) or 0))
        if pool_size <= 0:
            return
        try:
            event_prefix = self._get_event_prefix()
            categories = self._parse_categories(event_prefix)
            if not categories:
                return
            cache_key = self._render_cache_key(categories, None, event_prefix)
            self._schedule_menu_pool_refill(cache_key, pool_size)
            logger.info("帮助菜单预渲染池预热已启动")
        except Exception as e:
            logger.warning(f"帮助菜单预热失败: {e}")

    async def terminate(self):
        """插件卸载时清理资源"""
        if self._pool_task and not self._pool_task.done():
            self._pool_task.cancel()
            try:
                await self._pool_task
            except (asyncio.CancelledError, Exception):
                pass
            self._pool_task = None
        self._drain_menu_pool()
        self._cleanup_used_pool_images()
        await self.renderer.close()
        logger.info("帮助菜单插件已卸载")
