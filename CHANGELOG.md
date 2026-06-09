# 更新日志

本文件记录 `astrbot_plugin_helpmenu` 的主要变更。

## v1.0.0 - 2026-06-10

### 新增

- 新增图片版帮助菜单，支持通过配置的触发命令查看完整菜单。
- 新增分类筛选能力，支持在触发命令后追加分类名查看指定分类。
- 新增 Native Page 后台管理页面，可视化维护分类、指令、描述和 Logo。
- 新增分类 Logo、指令 Logo 与标题圆形 Logo 上传能力。
- 新增指令图标 emoji 自动回退规则，未配置 Logo 时根据指令名和描述自动匹配图标。
- 新增 `command_aliases` 配置项，支持为帮助菜单配置多个触发别名。
- 新增 `font_file` 配置项，支持选择内置字体或回退系统字体。

### 变更

- 插件版本重新整理为 `1.0.0`，按 AstrBot 官方插件格式规范化发布文件。
- 插件元数据改为标准 `metadata.yaml` 字段，支持平台仅声明 `aiocqhttp`。
- `README.md` 重写为面向插件市场发布的安装、使用、配置和数据说明文档。
- `menu.json` 改为持久化数据文件，不再作为插件目录中的可变文件维护。
- 插件目录中的默认菜单模板改名为 `default_menu.json`，仅用于首次初始化。
- HTML 渲染器读取相对资源时，优先从插件持久化数据目录查找，再回退到插件内置资源。
- 帮助菜单触发逻辑改为运行时按配置匹配主命令和别名，避免静态 `@filter.command("help")` 导致配置不生效。
- 标题旁边的圆形 Logo 改为通过 Native Page 上传和清空，不再通过配置项手写相对路径。

### 修复

- 修复 `command_name` 配置只被读取但不会影响实际触发命令的问题。
- 修复指令别名配置不生效的问题。
- 修复后台上传图标和菜单数据写入插件目录，更新或重装插件后可能丢失的问题。
- 修复默认 Logo 配置仍指向 `./logo.jpg`，但插件实际提供 `logo.png` 的问题。
- 移除 `logo_path` 配置项，避免用户在配置页手写插件目录相对路径。

### 数据迁移

- 菜单数据保存到 AstrBot 持久化目录：

  ```text
  data/plugin_data/astrbot_plugin_helpmenu/menu.json
  ```

- 后台上传的图标保存到：

  ```text
  data/plugin_data/astrbot_plugin_helpmenu/images/icons/
  ```

- 首次启动时，如果持久化目录中不存在菜单数据，会自动从插件目录中的 `default_menu.json` 初始化。
- 旧版本若仍在插件目录中存在 `menu.json` 或 `images/icons/`，插件加载时会尝试自动迁移到持久化目录。

### 依赖

- `playwright>=1.40.0`
- `jinja2>=3.0.0`
- `aiohttp>=3.8.0`

### 升级须知

- 修改 `command_name` 或 `command_aliases` 后，需要在 AstrBot WebUI 中重载插件后生效。
- 更新或重装插件前，请保留 `data/plugin_data/astrbot_plugin_helpmenu/` 目录，以免丢失自定义菜单和上传图标。
