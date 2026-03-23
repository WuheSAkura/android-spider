# Windows 本地 Android 模拟器自动化采集基础项目

## 1. 项目简介

这是一个面向 Windows 10/11 本机环境的 Android 模拟器自动化采集 MVP 项目，默认基于 `adb + uiautomator2` 与已启动的 Android 模拟器通信，优先兼容 Android Studio Emulator（AVD）。

当前版本重点是把最小闭环跑通：

- 自动发现在线模拟器
- 连接设备并启动 App
- 执行基础页面操作
- 导出当前页面截图、层级与可见文本
- 将运行状态写入 MySQL
- 失败时自动保留故障现场，并写入 SQLite 失败记录

项目默认提供一个无需第三方 App 的 `settings_demo`，用于直接验证整条链路。
同时提供一个基于闲鱼真实页面 dump 编写的 `xianyu_search_demo`，以及一个面向小红书图文/视频帖子的 `xiaohongshu_search_demo`，用于演示搜索结果采集。

## 2. 技术选型说明

- Python 3.11：主语言
- uiautomator2：Android UI 自动化
- adb / subprocess：设备发现与基础命令调用
- PyYAML：任务配置加载
- mysql-connector-python：写入 MySQL
- sqlite3：失败任务本地留痕
- FastAPI + uvicorn：本地桌面端 API 服务
- Electron + React + TypeScript：桌面可视化操作界面
- argparse：CLI 命令解析
- logging：控制台 + 文件日志
- pathlib / dataclasses / typing：提高可维护性

说明：

- 当前默认 driver 为 `AndroidDriver`，未来可替换为其他实现，例如 Appium，只要保持接口一致即可。
- 当前不包含 OCR、抓包、逆向、反检测等能力。

## 3. Windows 本地准备步骤

### 3.1 安装 Python

- 安装 Python 3.11
- 确认命令可用：`py -3.11 --version`

### 3.2 安装 Android Studio / AVD

- 安装 Android Studio
- 通过 Device Manager 创建一个 AVD
- 启动模拟器并保持运行

### 3.3 确保 adb 可用

- 确认 Android SDK Platform Tools 已安装
- 将 `platform-tools` 加入系统 PATH
- 验证：`adb version`
- 如果当前终端还没刷新到最新 PATH，可以直接在命令里追加 `--adb-path D:\adb\platform-tools\adb.exe`

### 3.4 启动模拟器

- 启动 AVD 后执行：`adb devices`
- 确认至少有一个设备状态为 `device`

## 4. 安装依赖

### 方式一：使用 PowerShell 脚本

```powershell
pwsh -File .\scripts\setup_windows.ps1
```

### 方式二：手动安装

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. 运行环境检查

```powershell
.\.venv\Scripts\python.exe .\main.py doctor
```

或显式指定 adb：

```powershell
.\.venv\Scripts\python.exe .\main.py doctor --adb-path D:\adb\platform-tools\adb.exe
```

`doctor` 会检查：

- `adb` 是否可用
- `yaml`、`uiautomator2`、`mysql.connector` 是否安装
- 是否存在在线设备
- 输出设备 `serial`、`state`、Android 版本、机型

## 6. 运行 settings_demo

先确认 MySQL 服务已启动，且可以使用 `configs/settings_demo.yaml` 中的账号连接。程序会自动创建数据库和表。

```powershell
.\.venv\Scripts\python.exe .\main.py run --config .\configs\settings_demo.yaml
```

如果 `adb` 已安装但当前终端找不到：

```powershell
.\.venv\Scripts\python.exe .\main.py run --config .\configs\settings_demo.yaml --adb-path D:\adb\platform-tools\adb.exe
```

也可以直接运行脚本：

```powershell
pwsh -File .\scripts\run_settings_demo.ps1
```

Demo 流程：

1. 自动选择第一个在线设备
2. 启动系统 Settings
3. 等待 Settings 页面出现
4. 向下滑动 1 次
5. 采集当前页面可见文本
6. 保存截图、层级、文本与结果文件
7. 写入 MySQL
8. 结束运行

## 6.1 运行闲鱼搜索采集 Demo

当前版本已增加 `xianyu_search` 适配器，用于验证这条链路：

1. 打开闲鱼
2. 点击首页搜索栏
3. 搜索关键词
4. 遍历搜索结果列表
5. 逐条进入详情页
6. 采集标题、价格、卖家名、卖家地区、想要人数、浏览数、详情页可见文本
7. 将结构化结果写入 `result.json`、`xianyu_items.json` 和 MySQL

运行命令：

```powershell
.\.venv\Scripts\python.exe .\main.py run --config .\configs\xianyu_search_demo.yaml --adb-path D:\adb\platform-tools\adb.exe
```

也可以直接运行脚本：

```powershell
pwsh -File .\scripts\run_xianyu_demo.ps1
```

默认配置：

- 搜索关键词：`iPhone15`
- 目标采集条数：`20`
- 最大翻页次数：`20`

如需调整，修改 [configs/xianyu_search_demo.yaml](d:\CodeList\android-spider\configs\xianyu_search_demo.yaml) 中的 `adapter_options` 即可。

## 6.2 运行小红书搜索采集 Demo

当前版本已增加 `xiaohongshu_search` 适配器，用于验证这条链路：

1. 打开小红书
2. 点击首页搜索入口
3. 搜索关键词
4. 遍历搜索结果列表
5. 逐条进入图文或视频帖子详情页
6. 采集正文、地点标签、博主昵称、IP 属地、点赞量、收藏量、评论量
7. 图文帖子继续下滑采集评论区一级评论；视频帖子点击评论浮层采集一级评论
8. 将结构化结果写入 `result.json`、`xiaohongshu_notes.json`、`xiaohongshu_comments.json` 和 MySQL

运行命令：

```powershell
.\.venv\Scripts\python.exe .\main.py run --config .\configs\xiaohongshu_search_demo.yaml --adb-path D:\adb\platform-tools\adb.exe
```

也可以直接运行脚本：

```powershell
pwsh -File .\scripts\run_xiaohongshu_demo.ps1
```

默认配置：

- 搜索关键词：`穿搭`
- 目标采集条数：`20`
- 每篇帖子最多评论数：`20`

如需调整，修改 [configs/xiaohongshu_search_demo.yaml](d:\CodeList\android-spider\configs\xiaohongshu_search_demo.yaml) 中的 `adapter_options` 即可。

## 7. 导出当前页面

```powershell
.\.venv\Scripts\python.exe .\main.py dump-page
```

也支持：

```powershell
.\.venv\Scripts\python.exe .\main.py dump-page --adb-path D:\adb\platform-tools\adb.exe
```

该命令会直接连接默认设备，并在 `artifacts/` 下生成一份当前页面导出结果。

## 7.1 启动本地桌面端 API

桌面端会通过本地 HTTP 接口调用现有 Python 采集能力，也可以单独启动服务进行调试：

```powershell
.\.venv\Scripts\python.exe .\main.py serve --host 127.0.0.1 --port 8765
```

可用接口包括：

- `GET /api/system/doctor`
- `GET /api/system/devices`
- `GET /api/task-templates`
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/runs`
- `POST /api/runs/{id}/cancel`
- `GET /api/runs`
- `GET /api/runs/{id}`
- `GET /api/runs/{id}/records`
- `GET /api/runs/{id}/logs`
- `GET /api/runs/{id}/artifacts`

说明：

- SQLite 现在不再只记失败，而是作为桌面端主数据源，保存设置、运行历史、结构化结果和取消状态
- MySQL 继续作为采集结果同步库
- 当前版本只支持单任务串行执行

## 7.2 启动 Electron 桌面端

```powershell
Set-Location .\desktop
npm install
npm run dev
```

桌面端能力：

- 选择小红书 / 闲鱼模板
- 选择目标设备
- 支持“轻量试跑”和“正式采集”
- 运行中轮询日志、结果与产物
- 支持协作式手动停止
- 查看本地历史记录与系统设置

## 8. 输出文件说明

每次运行都会生成独立目录，例如：

```text
artifacts/
  2026-03-16_220000_settings_demo/
    run.log
    settings_after_swipe_screenshot.png
    settings_after_swipe_hierarchy.xml
    settings_after_swipe_visible_texts.json
    result.json
```

闲鱼 Demo 会额外生成：

```text
artifacts/
  2026-03-16_220000_xianyu_search_demo/
    xianyu_items.json
    xianyu_final_screenshot.png
    xianyu_final_hierarchy.xml
    xianyu_final_visible_texts.json
    result.json
```

小红书 Demo 会额外生成：

```text
artifacts/
  2026-03-16_220000_xiaohongshu_search_demo/
    xiaohongshu_notes.json
    xiaohongshu_comments.json
    xiaohongshu_final_screenshot.png
    xiaohongshu_final_hierarchy.xml
    xiaohongshu_final_visible_texts.json
    result.json
```

补充说明：

- 任务失败时还会额外生成 `failure_*` 文件
- 失败 traceback 会写入 `traceback.txt`
- SQLite 失败记录默认写入 `data/local_runs.sqlite3`
- 桌面端设置、任务历史、结构化结果同样默认写入 `data/local_runs.sqlite3`

## 9. MySQL 表结构

程序启动后会自动建库建表。

### task_runs

- `id`
- `task_name`
- `device_serial`
- `status`
- `started_at`
- `finished_at`
- `artifact_dir`
- `error_message`

### collected_items

- `id`
- `run_id`
- `page_name`
- `text_content`
- `created_at`

### collected_records

- `id`
- `run_id`
- `item_index`
- `platform`
- `record_type`
- `keyword`
- `title`
- `content_text`
- `author_name`
- `author_id`
- `location_text`
- `ip_location`
- `published_text`
- `metrics_json`
- `extra_json`
- `raw_visible_texts_json`
- `created_at`

## 10. 如何新增一个 App Adapter

推荐步骤：

1. 在 `src/adapters/` 下新增一个继承 `BaseAdapter` 的类
2. 在 `src/adapters/__init__.py` 中注册该 adapter
3. 在 `configs/` 下新增对应 YAML
4. 将页面选择器、步骤流程写入 YAML
5. 如有必要，在 Adapter 中增加配置校验或结果组装逻辑

目前页面逻辑主要通过两层扩展：

- YAML：页面步骤、选择器、输出开关
- Adapter：结果结构、配置校验、预留前后置逻辑

## 11. 当前限制与后续扩展建议

当前限制：

- 默认只选择第一个在线设备
- 桌面端已支持显式指定设备；CLI 仍默认选择第一个在线设备
- 暂未实现更复杂的页面状态机
- 未实现 OCR、图像识别、复杂控件语义解析
- 未实现多设备并发和任务队列
- 未实现 Appium 驱动，但接口已预留替换空间
- 当前仓库工作流限制下未生成测试代码文件
- 闲鱼 Demo 当前基于你提供的页面 dump 做选择器与字段解析；如果闲鱼 UI 变化，可能需要重新抓 dump 调整
- 小红书 Demo 当前优先兼容图文帖子详情页直出评论、以及视频帖子评论浮层；如果 UI 变化或出现更重的混排卡片，可能需要重新抓 dump 调整
- 闲鱼的“留言”字段目前只采当前详情页可见的留言相关文本；你这次提供的详情页 dump 中没有实际留言内容，所以该字段可能为空

后续建议：

- 增加更完整的 selector 能力，例如文本包含、索引定位
- 抽象 driver 接口，允许切换到 Appium
- 增加更细粒度的数据库日志表
- 增加任务重试与更丰富的异常分类
- 增加页面对象模型，便于复杂 App 维护
- 对闲鱼详情页补“滚动到留言区 / 进入留言页”的二阶段采集

## 12. 目录结构

```text
project_root/
  README.md
  requirements.txt
  .gitignore
  main.py
  configs/
    settings_demo.yaml
    xiaohongshu_search_demo.yaml
    xianyu_search_demo.yaml
    target_app_template.yaml
  src/
    api/
      app.py
      schemas.py
    core/
      adb_manager.py
      device_manager.py
      driver.py
      selectors.py
      actions.py
      task_runner.py
      artifacts.py
      ui_xml.py
    adapters/
      base_adapter.py
      settings_demo_adapter.py
      target_app_template_adapter.py
      xiaohongshu_adapter.py
      xiaohongshu_parser.py
      xianyu_adapter.py
      xianyu_parser.py
    storage/
      sqlite_store.py
      result_store.py
    services/
      cancellation_service.py
      run_service.py
      settings_service.py
      task_template_service.py
    models/
      collected_record.py
      task_models.py
    utils/
      config_loader.py
      logger.py
      time_utils.py
      exceptions.py
  scripts/
    setup_windows.ps1
    run_xiaohongshu_demo.ps1
    run_settings_demo.ps1
    run_xianyu_demo.ps1
  desktop/
    package.json
    electron.vite.config.ts
    src/
      main/
      preload/
      renderer/
  data/
  artifacts/
  logs/
  tests/
```
