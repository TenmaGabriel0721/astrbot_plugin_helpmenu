"""
AstrBot 图文帮助菜单插件
使用 Playwright 本地渲染 HTML 生成精美的帮助菜单图片
添加 Native Page 可视化菜单面板，实现秒级修改保存即生效
"""

import re
import os
import json
import uuid
import base64
from pathlib import Path
from typing import Dict, Any, List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api import logger
from astrbot.core.star.filter.custom_filter import CustomFilter
from astrbot.core.star.filter.permission import PermissionType
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


class HelpMenuCommandFilter(CustomFilter):
    """按插件配置匹配帮助菜单触发命令和别名。"""

    def filter(self, event: AstrMessageEvent, cfg) -> bool:
        if not event.is_at_or_wake_command:
            return False

        plugin = getattr(self, "plugin", None)
        if plugin is None:
            return False

        message_str = re.sub(r"\s+", " ", event.get_message_str().strip())
        for command in plugin.get_configured_commands():
            if message_str == command:
                event.set_extra("helpmenu_message", None)
                return True
            if message_str.startswith(f"{command} "):
                event.set_extra(
                    "helpmenu_message",
                    message_str[len(command):].strip() or None,
                )
                return True
        return False


@register("astrbot_plugin_helpmenu", "gabriel0721", "HTML渲染帮助菜单插件", "1.0.0")
class HelpMenuPlugin(Star):
    """帮助菜单插件 - 使用 Playwright 本地渲染"""
    
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.command_name = (config.get('command_name', 'help') or 'help').strip() or 'help'
        self.command_aliases = self._parse_command_aliases(config.get('command_aliases', '菜单,帮助'))
        self.command_prefix = config.get('command_prefix', '')
        
        # 内存幽灵插件元数据自愈净化：在完全载入后，彻底移除多余同名幽灵，保留唯一的正统卡片
        try:
            from astrbot.core.star.star_manager import star_registry
            correct_star = None
            ghost_stars = []
            
            for s in star_registry:
                if s.name == "astrbot_plugin_helpmenu":
                    if getattr(s, "module_path", "").startswith("data.plugins."):
                        correct_star = s
                    else:
                        ghost_stars.append(s)
            
            # 如果两个都有，把没有 data.plugins 前缀的幽灵卡片彻底从注册表中移除
            if correct_star and ghost_stars:
                for ghost in ghost_stars:
                    if ghost in star_registry:
                        star_registry.remove(ghost)
                logger.info("✨ 成功净化清除多余的同名幽灵卡片，只保留唯一正统的帮助菜单卡片！")
        except Exception as cleanup_err:
            logger.error(f"净化幽灵卡片失败: {cleanup_err}")
        
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
        HelpMenuCommandFilter.plugin = self
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
        except Exception as e:
            logger.error(f"保存 menu.json 失败: {e}")
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
        except Exception as e:
            logger.error(f"保存页面设置失败: {e}")
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
                    return jsonify({"success": True, "path": ""})
                return jsonify({"success": False, "message": "保存页面设置失败"})

            result = await self._save_uploaded_image("header_logo")
            if not result.get("success"):
                return jsonify(result)

            settings = self._load_page_settings()
            settings["header_logo"] = result["path"]
            if not self._save_page_settings(settings):
                return jsonify({"success": False, "message": "保存页面设置失败"})
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
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "message": "写入 menu.json 失败"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    async def _save_uploaded_image(self, prefix: str = "icon") -> Dict[str, Any]:
        """保存上传图片到持久化图标目录。"""
        allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        max_size = 5 * 1024 * 1024
        filename = "icon.png"
        content = None

        files = await request.files
        upload = files.get("file") if files else None
        if upload:
            filename = upload.filename or filename
            content = upload.read()
        else:
            payload = await request.get_json(silent=True)
            if not isinstance(payload, dict):
                return {"success": False, "message": "未收到图片文件"}
            filename = payload.get("filename") or filename
            data_url = payload.get("data") or ""
            if "," in data_url:
                data_url = data_url.split(",", 1)[1]
            try:
                content = base64.b64decode(data_url, validate=True)
            except Exception:
                return {"success": False, "message": "图片数据无效"}

        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            return {"success": False, "message": "仅支持 png、jpg、jpeg、webp、gif 图片"}
        if not content:
            return {"success": False, "message": "图片内容为空"}
        if len(content) > max_size:
            return {"success": False, "message": "图片不能超过 5MB"}

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

    @filter.custom_filter(HelpMenuCommandFilter)
    async def menu_cmd(self, event: AstrMessageEvent, message: str = None):
        """生成图文菜单。用法：~help [分类名]"""
        image_path = None
        try:
            # 动态获得当前消息环境的指令前缀，优先匹配以提供精美展示
            event_prefix = self.command_prefix  # 优先使用配置的前缀

            # 如果配置为空，尝试从系统获取
            if not event_prefix:
                try:
                    event_prefix = self.context.config.command_prefix
                except:
                    event_prefix = "~"  # 最后的默认值
            
            # 解析菜单配置
            categories = self._parse_categories(event_prefix)
            
            if not categories:
                yield event.plain_result("未配置菜单内容。你可以在后台 Dashboard 的指令菜单管理中快捷创建它。")
                return
            
            # 处理分类筛选
            filter_cat = event.get_extra("helpmenu_message")
            if filter_cat is None:
                filter_cat = message.strip() if message else None
            
            # 准备渲染数据（支持从API获取背景图）
            render_config = dict(self.config)
            render_config["header_logo"] = self._load_page_settings().get("header_logo", "")
            data = await self.renderer.prepare_menu_data(categories, render_config, filter_cat)
            
            if filter_cat and not data['categories']:
                yield event.plain_result(f"未找到分类：{filter_cat}")
                return
            
            # 加载并渲染模板
            template_content = self.renderer.load_template("menu.html")
            html_content = self.renderer.render_template(template_content, data)
            
            # 使用 Playwright 渲染为图片
            image_path = await self.renderer.render_to_image(html_content)
            
            # 返回图片
            yield event.image_result(image_path)
            
        except FileNotFoundError as e:
            logger.error(f"模板文件不存在: {e}")
            yield event.plain_result("❌ 菜单模板文件不存在，请检查插件安装是否完整")
        except Exception as e:
            logger.error(f"生成菜单失败: {e}")
            import traceback
            traceback.print_exc()
            yield event.plain_result(f"❌ 生成菜单出错: {str(e)}")
        finally:
            # 清理临时图片文件
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.debug(f"已清理临时图片文件: {image_path}")
                except Exception as e:
                    logger.warning(f"清理临时图片文件失败: {e}")
    
    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("添加菜单项")
    async def add_menu_item(self, event: AstrMessageEvent, category: str, command: str, description: str):
        """添加菜单项。用法：~添加菜单项 <分类名> <指令名> <描述>"""
        menu_data = self._load_menu_data()
        
        # 剥离可能带的前缀，保持干净指令存储
        clean_cmd = command
        if clean_cmd.startswith("~") or clean_cmd.startswith("～") or clean_cmd.startswith("/"):
            clean_cmd = clean_cmd[1:]
            
        if category not in menu_data:
            menu_data[category] = {}
            
        if clean_cmd in menu_data[category] and menu_data[category][clean_cmd] == description:
            yield event.plain_result(f"菜单项 '{command}' 已经存在于分类 '{category}' 中。")
            return

        menu_data[category][clean_cmd] = description
        if self._save_menu_data(menu_data):
            yield event.plain_result(f"🎉 成功添加菜单项并保存：{category} :: {command} :: {description}。即时生效！")
        else:
            yield event.plain_result("❌ 写入配置失败，请检查文件权限。")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删除菜单项")
    async def del_menu_item(self, event: AstrMessageEvent, command_to_delete: str):
        """删除菜单项。用法：~删除菜单项 <指令名>"""
        menu_data = self._load_menu_data()
        
        clean_cmd = command_to_delete
        if clean_cmd.startswith("~") or clean_cmd.startswith("～") or clean_cmd.startswith("/"):
            clean_cmd = clean_cmd[1:]
            
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
                yield event.plain_result(f"🎉 成功删除菜单项 '{command_to_delete}'。即时生效！")
            else:
                yield event.plain_result("❌ 写入配置失败，请检查文件权限。")
        else:
            yield event.plain_result(f"未找到指令名为 '{command_to_delete}' 的菜单项。")
            
    async def terminate(self):
        """插件卸载时清理资源"""
        await self.renderer.close()
        logger.info("帮助菜单插件已卸载")
