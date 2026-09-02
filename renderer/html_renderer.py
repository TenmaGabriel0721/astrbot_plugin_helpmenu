"""
HTML 渲染器模块
使用 Playwright 本地渲染 HTML 为图片
"""

import asyncio
import os
import base64
import random
import tempfile
import uuid
import aiohttp
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.request import pathname2url

from astrbot.api import logger


class HtmlRenderer:
    """HTML 渲染器 - 使用 Playwright 本地渲染"""
    
    # 默认背景图API
    DEFAULT_BG_API = "http://manyacg.top/setu"

    # 默认字体文件名（相对 fonts/std/）
    DEFAULT_FONT_FILE = "东京街角的小浪漫.ttf"

    def __init__(self, plugin_dir: str, data_dir: str = None):
        """
        初始化渲染器

        Args:
            plugin_dir: 插件目录路径
            data_dir: 插件持久化数据目录路径
        """
        self.plugin_dir = Path(plugin_dir)
        self.data_dir = Path(data_dir) if data_dir else self.plugin_dir
        self.static_dir = self.plugin_dir / "static"
        self.html_dir = self.static_dir / "html"
        self.css_dir = self.static_dir / "css"
        self.images_dir = self.plugin_dir / "images"
        self.data_images_dir = self.data_dir / "images"
        self.fonts_dir = self.plugin_dir / "fonts"

        # 背景图预取池：提前从API拉图缓存到本地，渲染时随机取用、用完即删
        self.bg_pool_dir = self.data_dir / "cache" / "bg_pool"
        self.bg_pool_dir.mkdir(parents=True, exist_ok=True)
        self._bg_refilling = False
        self._bg_refill_task: Optional[asyncio.Task] = None

        # 字体 file:// URL 缓存：{绝对路径: file_url}
        self._font_cache: Dict[str, str] = {}

        # HTTP会话
        self._session: Optional[aiohttp.ClientSession] = None
        self._playwright = None
        self._browser = None
        self._browser_lock = asyncio.Lock()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """关闭HTTP会话、后台补仓任务和浏览器资源"""
        if self._bg_refill_task and not self._bg_refill_task.done():
            self._bg_refill_task.cancel()
            try:
                await self._bg_refill_task
            except (asyncio.CancelledError, Exception):
                pass
            self._bg_refill_task = None
        if self._session and not self._session.closed:
            await self._session.close()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _get_browser(self):
        """获取或启动可复用的 Playwright Chromium 浏览器。"""
        async with self._browser_lock:
            if self._browser and self._browser.is_connected():
                return self._browser
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            logger.debug("启动Playwright浏览器...")
            self._browser = await self._playwright.chromium.launch(headless=True)
            return self._browser

    def _safe_relative_path(self, raw_path: str, base_dir: Path) -> Optional[Path]:
        """解析相对路径，并确保结果仍在指定目录内。"""
        if not raw_path or os.path.isabs(raw_path):
            return None
        candidate = (base_dir / raw_path.lstrip("./")).resolve()
        try:
            if candidate.is_relative_to(base_dir.resolve()):
                return candidate
        except ValueError:
            pass
        logger.warning(f"拒绝访问越界资源路径: {raw_path}")
        return None

    def _resolve_resource_path(self, raw_path: str, allow_plugin_fallback: bool = True) -> Optional[Path]:
        """优先从持久化目录解析资源，必要时回退到插件内置资源。"""
        if not raw_path:
            return None
        if os.path.isabs(raw_path):
            path = Path(raw_path).resolve()
            allowed_roots = [self.data_dir.resolve()]
            if allow_plugin_fallback:
                allowed_roots.append(self.plugin_dir.resolve())
            if any(path.is_relative_to(root) for root in allowed_roots):
                return path
            logger.warning(f"拒绝访问越界绝对路径: {raw_path}")
            return None

        data_path = self._safe_relative_path(raw_path, self.data_dir)
        if data_path and data_path.exists():
            return data_path
        if allow_plugin_fallback:
            plugin_path = self._safe_relative_path(raw_path, self.plugin_dir)
            if plugin_path:
                return plugin_path
        return data_path
    
    def load_template(self, template_name: str) -> str:
        """
        加载 HTML 模板
        
        Args:
            template_name: 模板文件名
        
        Returns:
            模板内容字符串
        """
        template_path = self.html_dir / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    async def _download_bg_to_pool(self, api_url: str) -> bool:
        """从API下载一张背景图存入本地预取池。"""
        try:
            session = await self._get_session()
            async with session.get(api_url) as response:
                response.raise_for_status()
                content = await response.read()

                content_type = response.headers.get('Content-Type', '')
                if 'png' in content_type:
                    ext = '.png'
                elif 'webp' in content_type:
                    ext = '.webp'
                elif 'gif' in content_type:
                    ext = '.gif'
                else:
                    ext = '.jpg'

                if len(content) < 1024:  # 过小的响应视为无效
                    logger.warning(f"背景API返回内容过小({len(content)}B)，跳过: {api_url}")
                    return False

                pool_file = self.bg_pool_dir / f"bg_{uuid.uuid4().hex}{ext}"
                with open(pool_file, "wb") as f:
                    f.write(content)
                logger.debug(f"背景图已预取到池: {pool_file.name} ({len(content)//1024}KB)")
                return True
        except Exception as e:
            logger.warning(f"预取背景图失败: {e}")
            return False

    def _bg_pool_files(self) -> List[Path]:
        """列出当前背景池中的图片文件。"""
        try:
            return [
                path for path in self.bg_pool_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
            ]
        except Exception:
            return []

    async def refill_bg_pool(self, api_url: str, target_size: int = 2):
        """将背景池补足到目标数量（带防重入，可被并发安全地反复调用）。"""
        if self._bg_refilling:
            return
        self._bg_refilling = True
        try:
            while len(self._bg_pool_files()) < target_size:
                if not await self._download_bg_to_pool(api_url):
                    break  # API不可用，等待下次再补
        finally:
            self._bg_refilling = False

    def _schedule_bg_refill(self, api_url: str, target_size: int = 2):
        """后台异步补仓，不阻塞当前渲染。"""
        if self._bg_refill_task and not self._bg_refill_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._bg_refill_task = loop.create_task(self.refill_bg_pool(api_url, target_size))

    def acquire_background(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """取一张背景图：优先消费本地预取池（随机取用、用完即删），池空回退本地图片。

        Returns:
            {"url": data_url或None, "cacheable": 背景是否确定（决定菜单成品图能否缓存）}
        """
        use_api = config.get('use_api_background', True)

        if use_api:
            api_url = config.get('background_api', '') or self.DEFAULT_BG_API
            pool_size = max(1, int(config.get('bg_pool_size', 2) or 2))
            # 池不足时后台补仓（含插件刚启动的首次预热）
            self._schedule_bg_refill(api_url, pool_size)

            pool_files = self._bg_pool_files()
            if pool_files:
                selected = random.choice(pool_files)
                encoded = self._encode_image(str(selected))
                if encoded:
                    try:
                        selected.unlink()  # 用完即删，保证下次背景不重复
                    except OSError as e:
                        logger.warning(f"删除已用背景图失败 {selected}: {e}")
                    logger.info(f"从预取池取用背景图: {selected.name}（剩余{len(pool_files)-1}张）")
                    return {"url": encoded, "cacheable": False}
                # 编码失败（文件损坏等）也删除该文件，避免反复选中坏图
                try:
                    selected.unlink()
                except OSError:
                    pass
                logger.warning(f"预取池背景图编码失败，已丢弃: {selected.name}")

            logger.warning("背景预取池为空，回退到本地图片")

        # 本地背景（单文件=确定性可缓存；目录随机=不可缓存）
        bg_path = config.get('background_image', './images')
        resolved = self._resolve_resource_path(bg_path, allow_plugin_fallback=True)
        if resolved and resolved.is_file():
            return {"url": self._encode_image(str(resolved)), "cacheable": True}
        url = self.get_random_background(bg_path)
        return {"url": url, "cacheable": False}

    def get_random_background(self, bg_path: str = None) -> Optional[str]:
        """
        获取随机本地背景图片的base64编码
        
        Args:
            bg_path: 背景图片路径或目录
        
        Returns:
            base64编码的图片数据URL，或None
        """
        if not bg_path:
            bg_path = str(self.images_dir)
        
        # 如果是相对路径，优先从持久化数据目录读取，再回退到插件目录内置资源
        resolved = self._resolve_resource_path(bg_path, allow_plugin_fallback=True)
        if not resolved:
            logger.warning(f"背景路径不存在或不允许访问: {bg_path}")
            return None
        bg_path = resolved

        if not bg_path.exists():
            logger.warning(f"背景路径不存在: {bg_path}")
            return None

        # 如果是文件，直接使用
        if bg_path.is_file():
            return self._encode_image(str(bg_path))

        # 如果是目录，随机选择一张图片
        if bg_path.is_dir():
            image_files = [
                path for path in bg_path.iterdir()
                if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}
            ]

            if image_files:
                selected = random.choice(image_files)
                logger.info(f"随机选择本地背景图: {selected}")
                return self._encode_image(str(selected))
        
        return None
    
    def _encode_image(self, image_path: str) -> Optional[str]:
        """
        将图片编码为base64数据URL
        
        Args:
            image_path: 图片路径
        
        Returns:
            base64数据URL
        """
        try:
            with open(image_path, 'rb') as f:
                data = f.read()
            
            # 根据扩展名确定MIME类型
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.gif': 'image/gif'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            encoded = base64.b64encode(data).decode('utf-8')
            return f"data:{mime_type};base64,{encoded}"
        except Exception as e:
            logger.error(f"编码图片失败: {e}")
            return None
    
    def get_logo_base64(self, logo_path: str) -> Optional[str]:
        """
        获取Logo的base64编码
        
        Args:
            logo_path: Logo路径
        
        Returns:
            base64数据URL
        """
        if not logo_path:
            return None
        
        # 如果是相对路径，优先从持久化数据目录读取，再回退到插件目录内置资源
        resolved = self._resolve_resource_path(logo_path, allow_plugin_fallback=True)
        if not resolved:
            logger.warning(f"Logo文件不存在或不允许访问: {logo_path}")
            return None
        logo_path = resolved

        if not logo_path.exists():
            logger.warning(f"Logo文件不存在: {logo_path}")
            return None

        return self._encode_image(str(logo_path))

    def get_font_data_url(self, font_path: Optional[str] = None) -> str:
        """
        解析字体文件并返回 file:// 本地直链，用于注入 @font-face。

        相比把数MB的字体转成Base64塞进HTML，file:// 直链让 Chromium 直接读本地文件，
        解析速度提升数倍。页面本身即通过 file:// 加载，同源可访问。

        查找顺序：
          1. 显式传入的路径（绝对或相对插件目录）
          2. fonts/std/<font_path 的文件名>
          3. fonts/std/DEFAULT_FONT_FILE
          4. fonts/std/ 下任意 .ttf/.otf/.woff/.woff2

        Args:
            font_path: 配置中指定的字体文件路径或文件名，可为空

        Returns:
            file:// URL 字符串；若无可用字体，返回空字符串（CSS 会回退到系统字体栈）
        """
        candidates: List[Path] = []
        std_dir = self.fonts_dir / "std"

        if font_path:
            p = Path(font_path)
            candidates.append(p if p.is_absolute() else self.plugin_dir / p)
            candidates.append(std_dir / p.name)

        candidates.append(std_dir / self.DEFAULT_FONT_FILE)

        if std_dir.is_dir():
            for ext in ("*.ttf", "*.otf", "*.woff2", "*.woff"):
                candidates.extend(sorted(std_dir.glob(ext)))

        seen = set()
        for cand in candidates:
            key = str(cand.resolve() if cand.exists() else cand)
            if key in seen:
                continue
            seen.add(key)
            if not cand.is_file():
                continue
            cached = self._font_cache.get(key)
            if cached:
                return cached
            try:
                font_url = f"file://{pathname2url(str(cand.resolve()))}"
                self._font_cache[key] = font_url
                logger.info(f"已加载菜单字体(file://直链): {cand.name}")
                return font_url
            except Exception as e:
                logger.warning(f"解析字体文件路径失败 {cand}: {e}")

        logger.warning("未找到可用字体文件，将回退到系统字体栈")
        return ""
    
    async def prepare_menu_data(
        self,
        categories: List[Dict[str, Any]],
        config: Dict[str, Any],
        filter_cat: str = None
    ) -> Dict[str, Any]:
        """
        准备菜单页面的渲染数据
        
        Args:
            categories: 菜单分类数据
            config: 插件配置
            filter_cat: 过滤的分类名
        
        Returns:
            渲染数据字典
        """
        # 筛选分类
        display_cats = []
        if filter_cat:
            for cat in categories:
                if filter_cat in cat['name']:
                    display_cats.append(cat)
        else:
            display_cats = categories
        
        # 获取背景图：优先消费本地预取池（后台异步补仓，无网络等待）
        bg = self.acquire_background(config)
        background_url = bg["url"]
        bg_cacheable = bg["cacheable"]
        
        # 获取Logo
            
        # 获取Logo
        logo_path = config.get('header_logo', '')
        logo_url = self.get_logo_base64(logo_path) if logo_path else None

        # 获取字体（动态嵌入到模板的 @font-face）
        font_choice = (config.get('font_file', '') or '').strip()
        if font_choice.lower() == 'none':
            font_data_url = ''
        else:
            font_arg = None if not font_choice or font_choice.lower() == 'auto' else font_choice
            font_data_url = self.get_font_data_url(font_arg)

        # 准备数据
        data = {
            'title': config.get('header_title', 'Bot Menu'),
            'subtitle': config.get('header_subtitle', ''),
            'footer': config.get('footer_text', ''),
            'theme_color': config.get('theme_color', '#667eea'),
            'background_url': background_url,
            'logo_url': logo_url,
            'font_data_url': font_data_url,
            'categories': display_cats,
            'blur_radius': config.get('blur_radius', 0),
            'card_opacity': config.get('card_opacity', 10),
            'bg_cacheable': bg_cacheable,
        }
        
        return data
    
    def render_template(self, template_content: str, data: Dict[str, Any]) -> str:
        """
        使用 Jinja2 渲染模板
        
        Args:
            template_content: 模板内容
            data: 渲染数据
        
        Returns:
            渲染后的HTML字符串
        """
        from jinja2 import Template
        template = Template(template_content)
        return template.render(**data)
    
    async def render_to_image(
        self,
        html_content: str,
        output_path: str = None,
        scale: float = 2.0,
        image_format: str = 'png',
        quality: int = 90,
    ) -> str:
        """
        使用 Playwright 将 HTML 渲染为图片

        Args:
            html_content: HTML内容
            output_path: 输出路径，如果为None则自动生成
            scale: 缩放比例，默认2.0以提高清晰度
            image_format: 输出格式，'png' 或 'jpeg'（jpeg 编码更快、体积更小）
            quality: JPEG 质量(1-100)，仅在 image_format='jpeg' 时生效

        Returns:
            图片文件路径
        """
        image_type = 'jpeg' if str(image_format).lower() in ('jpg', 'jpeg') else 'png'
        quality = min(100, max(1, int(quality or 90)))

        temp_html_path = None
        context = None
        try:
            # 创建安全的临时HTML文件，避免可预测文件名导致符号链接攻击
            fd, temp_html_path = tempfile.mkstemp(suffix=".html", prefix="helpmenu_", text=True)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(html_content)

            if output_path is None:
                ext = '.jpg' if image_type == 'jpeg' else '.png'
                output_path = temp_html_path.replace('.html', ext)

            browser = await self._get_browser()
            # 创建带有设备缩放的上下文，提高清晰度
            context = await browser.new_context(
                viewport={'width': 1360, 'height': 1280},
                device_scale_factor=scale  # 2倍分辨率
            )
            page = await context.new_page()

            # 加载HTML文件。用 load 替代 networkidle（页面资源均为本地/data URL，
            # networkidle 只会白等固定超时）；字体与图片就绪单独显式等待。
            file_url = f"file://{pathname2url(temp_html_path)}"
            await page.goto(file_url, wait_until='load')
            await page.evaluate(
                "async () => {"
                "  if (document.fonts && document.fonts.ready) await document.fonts.ready;"
                "  const imgs = Array.from(document.images);"
                "  await Promise.all(imgs.map(img => img.complete ? null :"
                "    new Promise(res => { img.onload = img.onerror = res; })));"
                "}"
            )

            # 背景层是 .container 的兄弟节点，对 .container 做元素截图会把背景排除在外，
            # 所以必须先把 viewport 撑到内容高度（背景层按文档高度铺满），再按坐标裁剪。
            rect_js = (
                "() => { const c = document.querySelector('.container');"
                "  if (!c) return null;"
                "  const r = c.getBoundingClientRect();"
                "  return {x: r.left + window.scrollX, y: r.top + window.scrollY,"
                "          w: r.width, h: r.height}; }"
            )
            box = await page.evaluate(rect_js)
            if box:
                await page.set_viewport_size({
                    'width': max(int(box['w']) + 48, 1360),
                    'height': max(int(box['h']) + 48, 800),
                })
                # viewport 变化后等两帧重排，背景层才会按新高度铺满
                await page.evaluate(
                    "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
                )
                box = await page.evaluate(rect_js) or box

            screenshot_kwargs = {'path': output_path, 'type': image_type}
            if box:
                screenshot_kwargs['full_page'] = False
                screenshot_kwargs['clip'] = {
                    'x': max(0, box['x'] - 12),
                    'y': max(0, box['y'] - 12),
                    'width': box['w'] + 24,
                    'height': box['h'] + 24,
                }
            else:
                screenshot_kwargs['full_page'] = True
            if image_type == 'jpeg':
                screenshot_kwargs['quality'] = quality
            await page.screenshot(**screenshot_kwargs)

            logger.info(f"菜单图片已生成: {output_path} (scale={scale}x, {image_type})")
            return output_path
                    
        except Exception as e:
            logger.error(f"Playwright渲染失败: {e}")
            raise
        finally:
            # 清理临时HTML文件
            if context:
                try:
                    await context.close()
                except Exception as e:
                    logger.warning(f"关闭Playwright上下文失败: {e}")
            if temp_html_path and os.path.exists(temp_html_path):
                try:
                    os.remove(temp_html_path)
                except Exception as e:
                    logger.warning(f"清理临时HTML文件失败: {e}")