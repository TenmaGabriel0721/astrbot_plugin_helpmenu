# AstrBot 帮助菜单

一个用于 AstrBot 的图文帮助菜单插件。插件会读取 `menu.json` 中的分类与指令配置，将帮助菜单渲染为图片发送；同时提供 AstrBot Native Page 后台管理页面，方便直接编辑分类、指令说明和 Logo。

## 功能特性

- 图文帮助菜单：发送 `/help` 即可生成图片版指令菜单。
- 分类筛选：支持 `/help 分类名` 查看指定分类。
- 后台可视化管理：在 AstrBot 插件页面中维护菜单分类、指令、描述和图标。
- 分类 Logo 与指令 Logo：支持为分类或单条指令上传自定义图标。
- emoji 自动回退：未配置图标时，会根据指令名称和描述自动匹配 emoji。
- 本地 HTML 渲染：使用 Playwright 将 HTML 模板渲染为菜单图片。
- 管理员快捷维护：支持通过指令添加或删除菜单项。

## 支持平台

当前仅声明支持：

- `aiocqhttp`

## 安装

在 AstrBot 插件目录中克隆本仓库：

```bash
cd AstrBot/data/plugins
git clone https://github.com/TenmaGabriel0721/astrbot_plugin_helpmenu.git
```

安装 Python 依赖：

```bash
pip install -r astrbot_plugin_helpmenu/requirements.txt
```

如果运行环境尚未安装 Playwright 浏览器，请安装 Chromium：

```bash
playwright install chromium
```

Linux 环境建议安装中文字体和 emoji 字体，以获得更好的渲染效果：

```bash
sudo apt install fonts-noto-cjk fonts-noto-color-emoji
```

安装完成后，在 AstrBot WebUI 中重载或重启 AstrBot，并启用本插件。

## 使用方法

> 以下示例使用 `/` 作为指令前缀；实际前缀以你的 AstrBot 配置为准。

```text
/help              查看完整帮助菜单
/help 常用         查看名称包含“常用”的分类
/help AI           查看名称包含“AI”的分类
```

管理员可使用以下指令快速维护菜单：

```text
/添加菜单项 分类名 指令名 描述
/删除菜单项 指令名
```

## 后台管理页面

插件提供 `帮助菜单管理` 页面，可在 AstrBot WebUI 的插件页面中打开。你可以在页面中：

1. 新增、重命名、删除分类。
2. 为分类上传 Logo。
3. 新增、修改、删除指令。
4. 修改指令描述。
5. 为单条指令上传 Logo。
6. 保存后写入 `menu.json` 并即时生效。

上传的图标默认保存在：

```text
images/icons/
```

## 菜单数据格式

基础格式：

```json
{
  "常用": {
    "点歌": "如 /点歌 歌名",
    "今日运势": "查看今日运势"
  }
}
```

分类 Logo：

```json
{
  "常用": {
    "__icon__": "./images/icons/category.png",
    "点歌": "如 /点歌 歌名"
  }
}
```

指令 Logo：

```json
{
  "常用": {
    "点歌": {
      "desc": "如 /点歌 歌名",
      "icon": "./images/icons/music.png"
    }
  }
}
```

单条指令也可以指定前缀：

```json
{
  "常用": {
    "点歌": {
      "desc": "如 /点歌 歌名",
      "icon": "./images/icons/music.png",
      "prefix": "/"
    }
  }
}
```

`prefix` 说明：

- 不填写：使用插件配置或 AstrBot 当前指令前缀。
- 填写具体字符：使用该字符作为展示前缀。
- 填写空字符串：展示时不添加前缀。

## 配置项

插件配置由 `_conf_schema.json` 定义，可在 AstrBot WebUI 中修改。

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `command_prefix` | 菜单中展示的指令前缀，留空则自动获取系统前缀 | 空 |
| `command_name` | 帮助菜单触发命令 | `help` |
| `header_title` | 菜单标题 | `月月菜单` |
| `header_subtitle` | 菜单副标题 | `System Menu` |
| `logo_path` | 顶部 Logo 路径，留空则不显示 | `./logo.jpg` |
| `footer_text` | 页脚提示文字 | `[参数]必选 <参数>可选 | 请注意参数之间的空格` |
| `theme_color` | 菜单主题色 | `#667eea` |
| `use_api_background` | 是否使用 API 获取背景图 | `true` |
| `background_api` | 背景图 API 地址 | `http://manyacg.top/setu` |
| `background_image` | 本地背景图片或图片目录 | `./images` |
| `blur_radius` | 背景虚化程度 | `0` |
| `card_opacity` | 指令卡片透明度 | `10` |
| `font_file` | 菜单字体文件 | `auto` |

## 文件说明

```text
astrbot_plugin_helpmenu/
├── main.py                 # 插件入口
├── metadata.yaml           # AstrBot 插件元数据
├── _conf_schema.json       # WebUI 配置项定义
├── menu.json               # 菜单数据
├── requirements.txt        # Python 依赖
├── logo.png                # 插件 Logo
├── renderer/               # HTML 渲染逻辑
├── static/html/menu.html   # 菜单 HTML 模板
├── pages/manage/           # Native Page 管理页面
└── images/                 # 默认背景和上传图标目录
```

## 注意事项

- 本插件版本号已按发布规范标记为 `1.0.0`。
- 插件 Logo 文件建议使用 1:1 比例，推荐尺寸 256×256。
- 上传图标支持 `png`、`jpg`、`jpeg`、`webp`、`gif`，单个文件最大 5MB。
- `menu.json` 会被后台管理页面直接写入，请在更新插件前自行备份重要菜单数据。
- 如果修改插件代码、页面或模板后未生效，请在 AstrBot WebUI 中重载插件，必要时重启 AstrBot。

## 开源协议

本项目使用 AGPL-3.0 License。
