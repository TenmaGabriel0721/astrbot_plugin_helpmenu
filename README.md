# AstrBot 帮助菜单增强版

作者：gabriel

一个面向 AstrBot 的宽屏图文帮助菜单插件，支持 Native Page 可视化编辑、分类 Logo、指令 Logo、智能 emoji 回退和 HTML 图片渲染。

## 功能特性

- 宽屏图文菜单：更适合展示大量指令，指令卡片会根据内容长度自动换行排布。
- 显眼标题信息：副标题和页脚字体更大、更亮，适合放群号、说明或宣传语。
- 可视化管理：在 AstrBot 插件页面中直接管理分类、指令名、描述和 Logo。
- 分类 Logo：每个分类都可以上传单独 Logo。
- 指令 Logo：每条指令都可以上传单独 Logo。
- 智能回退：未设置 Logo 时自动按指令名和描述匹配 emoji。
- 分类筛选：支持 `/help 分类名` 模糊查看指定分类。
- 本地渲染：使用 Playwright 将 HTML 菜单渲染成图片。
- 旧数据兼容：兼容旧版 `menu.json` 的纯字符串描述格式。

## 安装

将插件放入 AstrBot 插件目录：

```bash
cd AstrBot/data/plugins
git clone https://github.com/TenmaGabriel0721/astrbot_plugin_helpmenu.git
```

安装依赖：

```bash
pip install -r astrbot_plugin_helpmenu/requirements.txt
```

如果服务器缺少 Playwright 浏览器环境，请根据 AstrBot 运行环境安装 Chromium：

```bash
playwright install chromium
```

Linux 环境建议安装中文字体和 emoji 字体：

```bash
sudo apt install fonts-noto-cjk fonts-noto-color-emoji
```

安装后重启 AstrBot，进入插件管理页启用插件。

## 使用方法

```text
/help              查看完整图文菜单
/help 常用         查看名称包含“常用”的分类
/help AI           查看名称包含“AI”的分类
```

管理员也可以用命令快速维护菜单：

```text
/添加菜单项 分类名 指令名 描述
/删除菜单项 指令名
```

实际前缀以 AstrBot 当前配置为准。

## Native Page 可视化管理

插件提供 `帮助菜单可视化管理` 页面，可在 AstrBot 后台直接操作：

1. 新建、删除分类。
2. 修改分类名称。
3. 为分类上传 Logo。
4. 添加、删除指令。
5. 修改指令名称和描述。
6. 为单条指令上传 Logo。
7. 清空 Logo 后自动恢复 emoji 匹配。
8. 保存后即时写入 `menu.json`。

上传的 Logo 会保存在：

```text
images/icons/
```

菜单渲染时会自动将本地图片转成 base64，方便 Playwright 渲染。

## 菜单数据格式

基础格式：

```json
{
  "常用": {
    "点歌": "如 ~点歌 歌名",
    "今日运势": "查看今日运势"
  }
}
```

分类 Logo：

```json
{
  "常用": {
    "__icon__": "./images/icons/category.png",
    "点歌": "如 ~点歌 歌名"
  }
}
```

指令 Logo：

```json
{
  "常用": {
    "点歌": {
      "desc": "如 ~点歌 歌名",
      "icon": "./images/icons/music.png"
    }
  }
}
```

没有 `icon` 时，插件会根据指令名和描述自动匹配 emoji。

## 配置项

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `command_name` | 帮助菜单触发命令配置项 | `help` |
| `header_title` | 菜单标题 | `月月菜单` |
| `header_subtitle` | 菜单副标题 | `System Menu` |
| `logo_path` | 顶部圆形 Logo 路径 | `./logo.jpg` |
| `footer_text` | 页脚文字 | `[参数]必选 <参数>可选 | 请注意参数之间的空格` |
| `theme_color` | 主题色 | `#667eea` |
| `use_api_background` | 是否使用背景图 API | `true` |
| `background_api` | 背景图 API 地址 | `http://manyacg.top/setu` |
| `background_image` | 本地背景图片或目录 | `./images` |
| `blur_radius` | 背景虚化程度 | `0` |
| `card_opacity` | 指令卡片透明度 | `10` |

## Logo 和 emoji 规则

优先级如下：

1. 指令自定义 Logo。
2. 自动 emoji 匹配。
3. 默认图标 `✨`。

分类 Logo 为空时不强制显示图片，分类名称仍正常显示。

当前 emoji 匹配覆盖常见 AI、绘图、游戏、Steam、Galgame、BA、QQ 空间、LLM、老婆抽卡、签到、下载、查询等关键词。

## 注意事项

- 上传 Logo 支持 `png`、`jpg`、`jpeg`、`webp`、`gif`。
- 单个 Logo 文件最大 5MB。
- 修改插件代码或新增 Web API 后，需要重启 AstrBot 或重载插件。
- 如果 Native Page 页面缓存旧资源，请刷新后台页面或重启 AstrBot。

## 开源协议

本项目遵循 AGPL-3.0 License。
