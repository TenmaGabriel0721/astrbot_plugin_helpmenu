"""
HTML 渲染器模块
使用 Playwright 本地渲染 HTML 为图片
"""

import os
import base64
import random
import glob
import tempfile
import aiohttp
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.request import pathname2url

from astrbot.api import logger


class HtmlRenderer:
    """HTML 渲染器 - 使用 Playwright 本地渲染"""
    
    # 默认背景图API
    DEFAULT_BG_API = "http://manyacg.top/setu"
    
    def __init__(self, plugin_dir: str):
        """
        初始化渲染器
        
        Args:
            plugin_dir: 插件目录路径
        """
        self.plugin_dir = Path(plugin_dir)
        self.static_dir = self.plugin_dir / "static"
        self.html_dir = self.static_dir / "html"
        self.css_dir = self.static_dir / "css"
        self.images_dir = self.plugin_dir / "images"
        
        # HTTP会话
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()
    
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
    
    async def get_background_from_api(self, api_url: str = None) -> Optional[str]:
        """
        从API获取背景图片
        
        Args:
            api_url: API地址，为空则使用默认API
        
        Returns:
            base64编码的图片数据URL，或None
        """
        if not api_url:
            api_url = self.DEFAULT_BG_API
        
        try:
            session = await self._get_session()
            async with session.get(api_url) as response:
                response.raise_for_status()
                content = await response.read()
                
                # 根据Content-Type确定MIME类型
                content_type = response.headers.get('Content-Type', 'image/jpeg')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    mime_type = 'image/jpeg'
                elif 'png' in content_type:
                    mime_type = 'image/png'
                elif 'webp' in content_type:
                    mime_type = 'image/webp'
                elif 'gif' in content_type:
                    mime_type = 'image/gif'
                else:
                    mime_type = 'image/jpeg'
                
                encoded = base64.b64encode(content).decode('utf-8')
                logger.info(f"从API获取背景图成功: {api_url}")
                return f"data:{mime_type};base64,{encoded}"
                
        except aiohttp.ClientError as e:
            logger.error(f"从API获取背景图失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取背景图时出错: {e}")
            return None
    
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
        
        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(bg_path):
            bg_path = str(self.plugin_dir / bg_path.lstrip('./'))
        
        if not os.path.exists(bg_path):
            logger.warning(f"背景路径不存在: {bg_path}")
            return None
        
        # 如果是文件，直接使用
        if os.path.isfile(bg_path):
            return self._encode_image(bg_path)
        
        # 如果是目录，随机选择一张图片
        if os.path.isdir(bg_path):
            image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.webp']
            image_files = []
            for ext in image_extensions:
                image_files.extend(glob.glob(os.path.join(bg_path, ext)))
                image_files.extend(glob.glob(os.path.join(bg_path, ext.upper())))
            
            if image_files:
                selected = random.choice(image_files)
                logger.info(f"随机选择本地背景图: {selected}")
                return self._encode_image(selected)
        
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
        
        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(logo_path):
            logo_path = str(self.plugin_dir / logo_path.lstrip('./'))
        
        if not os.path.exists(logo_path):
            logger.warning(f"Logo文件不存在: {logo_path}")
            return None
        
        return self._encode_image(logo_path)
    
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
        
        # 获取背景图
        background_url = None
        use_api = config.get('use_api_background', True)
        
        if use_api:
            # 从API获取背景图
            api_url = config.get('background_api', '') or self.DEFAULT_BG_API
            background_url = await self.get_background_from_api(api_url)
            
            # 如果API失败，回退到本地图片
            if not background_url:
                logger.warning("API获取背景图失败，回退到本地图片")
                bg_path = config.get('background_image', './images')
                background_url = self.get_random_background(bg_path)
        else:
            # 使用本地图片
            bg_path = config.get('background_image', './images')
            background_url = self.get_random_background(bg_path)
        
        # 获取Logo
        logo_path = config.get('logo_path', '')
        logo_url = self.get_logo_base64(logo_path) if logo_path else None
        
        # 准备数据
        data = {
            'title': config.get('header_title', 'Bot Menu'),
            'subtitle': config.get('header_subtitle', ''),
            'footer': config.get('footer_text', ''),
            'theme_color': config.get('theme_color', '#667eea'),
            'background_url': background_url,
            'logo_url': logo_url,
            'categories': display_cats,
            'blur_radius': config.get('blur_radius', 0),
            'card_opacity': config.get('card_opacity', 10),
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
    
    async def render_to_image(self, html_content: str, output_path: str = None, scale: float = 2.0) -> str:
        """
        使用 Playwright 将 HTML 渲染为图片
        
        Args:
            html_content: HTML内容
            output_path: 输出路径，如果为None则自动生成
            scale: 缩放比例，默认2.0以提高清晰度
        
        Returns:
            图片文件路径
        """
        from playwright.async_api import async_playwright
        
        temp_html_path = None
        try:
            # 创建临时HTML文件
            temp_dir = tempfile.gettempdir()
            temp_html_path = os.path.join(
                temp_dir,
                f"helpmenu_{os.getpid()}_{hash(html_content) % 100000}.html"
            )
            with open(temp_html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            if output_path is None:
                output_path = temp_html_path.replace('.html', '.png')
            
            async with async_playwright() as p:
                logger.debug("启动Playwright浏览器...")
                browser = await p.chromium.launch(headless=True)
                try:
                    # 创建带有设备缩放的上下文，提高清晰度
                    context = await browser.new_context(
                        viewport={'width': 1360, 'height': 1280},
                        device_scale_factor=scale  # 2倍分辨率
                    )
                    page = await context.new_page()
                    
                    # 加载HTML文件
                    file_url = f"file://{pathname2url(temp_html_path)}"
                    await page.goto(file_url, wait_until='networkidle')
                    await page.wait_for_timeout(500)  # 等待渲染完成
                    
                    # 获取容器元素
                    container = await page.query_selector('.container')
                    if not container:
                        # 如果没有container，截取整个页面
                        await page.screenshot(path=output_path, full_page=True, type='png')
                    else:
                        # 获取容器的边界框
                        box = await container.bounding_box()
                        if box:
                            # 设置viewport以匹配内容
                            viewport_width = int(box['width']) + 48
                            viewport_height = int(box['height']) + 48
                            await page.set_viewport_size({
                                'width': max(viewport_width, 1360),
                                'height': max(viewport_height, 800)
                            })
                            
                            # 重新获取边界框（viewport改变后可能变化）
                            await page.wait_for_timeout(200)
                            box = await container.bounding_box()
                            
                            if box:
                                # 截取容器区域
                                await page.screenshot(
                                    path=output_path,
                                    full_page=False,
                                    type='png',
                                    clip={
                                        'x': max(0, box['x'] - 12),
                                        'y': max(0, box['y'] - 12),
                                        'width': box['width'] + 24,
                                        'height': box['height'] + 24
                                    }
                                )
                            else:
                                await page.screenshot(path=output_path, full_page=True, type='png')
                        else:
                            await page.screenshot(path=output_path, full_page=True, type='png')
                    
                    await context.close()
                    logger.info(f"菜单图片已生成: {output_path} (scale={scale}x)")
                    return output_path
                    
                finally:
                    await browser.close()
                    
        except Exception as e:
            logger.error(f"Playwright渲染失败: {e}")
            raise
        finally:
            # 清理临时HTML文件
            if temp_html_path and os.path.exists(temp_html_path):
                try:
                    os.remove(temp_html_path)
                except Exception as e:
                    logger.warning(f"清理临时HTML文件失败: {e}")