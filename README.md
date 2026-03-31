# Android Spider

Windows 本地 Android 端采集与黑话分析桌面工作台。

当前项目以手机端采集方案为基础，使用 `adb + uiautomator2` 驱动模拟器或真机执行闲鱼、小红书采集，并通过本地 `FastAPI + Electron + React` 提供桌面控制台。  
在此基础上，项目已经迁入一套可运行的黑话分析闭环，包括：

- 黑话字典管理
- 黑话研判任务创建
- 研判结果浏览
- 本地文件管理

说明：

- 当前运行时项目是本仓库根目录的 `android-spider`
- 仓库中的 [xianyu](d:/CodeList/android-spider/xianyu) 目录仅作为旧项目迁移参考，不参与当前运行
- 旧项目里的网页端 cookie 爬虫、飞书上传链路不属于当前版本运行范围

## 1. 当前版本能力

### 1.1 采集能力

- 自动发现在线 Android 设备
- 执行 YAML 配置任务
- 支持闲鱼搜索结果采集
- 支持小红书笔记与一级评论采集
- 采集结果同时写入 MySQL 与本地 SQLite
- 保存运行日志、截图、页面层级、结构化结果

### 1.2 桌面端能力

当前 Electron 桌面端包含以下入口：

- `发起任务`
- `运行历史`
- `黑话字典`
- `黑话研判`
- `研判记录`
- `本地文件`
- `系统设置`

### 1.3 黑话分析能力

当前版本已迁入旧项目中的黑话业务链路，但只保留适用于手机端采集结构的部分：

- 黑话一级分类 / 二级分类 / 词条管理
- 从本地采集任务中选择数据源
- 对结构化记录执行 AI 黑话研判
- 保存研判任务状态、进度、命中数、失败信息
- 浏览单任务结果
- 按平台、任务、搜索词、是否命中过滤记录

当前研判范围：

- 闲鱼：只分析 `listing`
- 小红书：只分析 `note`

暂未纳入本轮研判的数据：

- 小红书 `comment`
- 旧网页端 cookie 爬虫数据

## 2. 技术栈

- Python 3.11
- `adb`
- `uiautomator2`
- `PyYAML`
- `mysql-connector-python`
- `sqlite3`
- `FastAPI`
- `uvicorn`
- `python-dotenv`
- `openai` SDK
- Electron
- React 19
- TypeScript

AI 研判使用 OpenAI-compatible 接口，默认按阿里云 DashScope Qwen 兼容模式配置。

## 3. 目录说明

```text
project_root/
  README.md
  .env.example
  main.py
  requirements.txt
  configs/
  scripts/
  src/
    adapters/
    api/
    core/
    models/
    services/
    storage/
    utils/
  desktop/
  data/
  artifacts/
  exports/
  logs/
  xianyu/
```

重点目录：

- `configs/`：采集任务 YAML
- `src/adapters/`：闲鱼、小红书等平台适配器
- `src/api/`：本地 FastAPI 服务
- `src/services/`：运行、设置、黑话字典、黑话研判、文件管理服务
- `src/storage/`：
  - [sqlite_store.py](d:/CodeList/android-spider/src/storage/sqlite_store.py)：运行历史与采集记录
  - [analysis_store.py](d:/CodeList/android-spider/src/storage/analysis_store.py)：黑话字典与研判任务/结果
- `desktop/`：Electron 桌面端
- `data/local_runs.sqlite3`：本地主数据源
- `xianyu/`：旧项目参考代码，不参与当前运行

## 4. 环境准备

### 4.1 Python

```powershell
py -3.11 --version
```

### 4.2 Android 设备

支持：

- Android Studio Emulator
- 其它可通过 `adb` 连接的模拟器
- 真机

确认设备在线：

```powershell
adb devices
```

### 4.3 安装依赖

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

桌面端依赖：

```powershell
Set-Location .\desktop
npm install
Set-Location ..
```

## 5. `.env` 配置

项目根目录新增 `.env` 后即可生效，`main.py` 启动时会自动加载。

示例：

```env
QWEN_API_KEY=your_qwen_api_key_here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

说明：

- `QWEN_API_KEY`：必填，用于黑话研判
- `QWEN_BASE_URL`：可选，默认是 DashScope 兼容端点
- `QWEN_MODEL`：可选，默认 `qwen-plus`

参考示例文件：[.env.example](d:/CodeList/android-spider/.env.example)

## 6. CLI 命令

### 6.1 环境检查

```powershell
.\.venv\Scripts\python.exe .\main.py doctor
```

如果当前终端无法识别 `adb`，可以显式指定：

```powershell
.\.venv\Scripts\python.exe .\main.py doctor --adb-path D:\adb\platform-tools\adb.exe
```

### 6.2 执行 YAML 任务

```powershell
.\.venv\Scripts\python.exe .\main.py run --config .\configs\xianyu_search_demo.yaml
```

或：

```powershell
.\.venv\Scripts\python.exe .\main.py run --config .\configs\xiaohongshu_search_demo.yaml
```

### 6.3 导出当前页面

```powershell
.\.venv\Scripts\python.exe .\main.py dump-page
```

### 6.4 单独启动本地 API

```powershell
.\.venv\Scripts\python.exe .\main.py serve --host 127.0.0.1 --port 8765
```

说明：

- 如果使用 Electron 桌面端，通常不需要手动执行 `serve`
- 桌面端启动时会自动拉起本地 Python 服务

## 7. 桌面端启动

```powershell
Set-Location .\desktop
npm run dev
```

桌面端会自动：

- 启动本地 Python API 服务
- 连接项目根目录 `.venv\Scripts\python.exe`，如果存在
- 通过 `http://127.0.0.1:8765` 调用后端

当前桌面端功能：

- 发起闲鱼 / 小红书采集任务
- 选择设备与运行模式
- 查看运行历史、日志、结构化记录、产物目录
- 管理黑话字典
- 创建黑话研判任务
- 浏览研判记录
- 管理本地输出文件

## 8. 本地 API

当前 API 由 [src/api/app.py](d:/CodeList/android-spider/src/api/app.py) 提供。

### 8.1 系统与任务模板

- `GET /api/health`
- `GET /api/system/doctor`
- `GET /api/system/devices`
- `GET /api/task-templates`
- `GET /api/settings`
- `PUT /api/settings`

### 8.2 采集任务

- `GET /api/runs`
- `POST /api/runs`
- `GET /api/runs/{run_id}`
- `POST /api/runs/{run_id}/cancel`
- `GET /api/runs/{run_id}/records`
- `GET /api/runs/{run_id}/logs`
- `GET /api/runs/{run_id}/artifacts`

### 8.3 黑话字典

- `GET /api/keyword-categories`
- `POST /api/keyword-categories`
- `PUT /api/keyword-categories/{category_id}`
- `DELETE /api/keyword-categories/{category_id}`
- `POST /api/keyword-categories/{category_id}/subcategories`
- `PUT /api/keyword-subcategories/{subcategory_id}`
- `DELETE /api/keyword-subcategories/{subcategory_id}`
- `POST /api/keyword-subcategories/{subcategory_id}/keywords`
- `PUT /api/keywords/{keyword_id}`
- `DELETE /api/keywords/{keyword_id}`

### 8.4 黑话研判

- `GET /api/jargon-analysis/sources`
- `POST /api/jargon-analysis/tasks`
- `GET /api/jargon-analysis/tasks`
- `GET /api/jargon-analysis/tasks/{task_id}`
- `GET /api/jargon-analysis/tasks/{task_id}/results`
- `GET /api/jargon-analysis/records`

### 8.5 本地文件管理

- `GET /api/files`
- `DELETE /api/files`

## 9. 数据存储与输出

### 9.1 本地 SQLite

默认文件：

- [data/local_runs.sqlite3](d:/CodeList/android-spider/data/local_runs.sqlite3)

当前承担的角色：

- 系统设置
- 运行历史
- 结构化采集记录
- 黑话字典
- 黑话研判任务
- 黑话研判结果

主要表：

- `settings`
- `task_runs`
- `collected_records`
- `keyword_categories`
- `keyword_subcategories`
- `keywords`
- `jargon_analysis_tasks`
- `jargon_analysis_results`

### 9.2 MySQL

MySQL 继续用于采集结果同步存储，和本地 SQLite 并行存在。

### 9.3 输出目录

每次运行会生成独立产物目录，通常位于：

- `artifacts/`
- `exports/`

常见产物：

- `run.log`
- `result.json`
- `*_screenshot.png`
- `*_hierarchy.xml`
- `*_visible_texts.json`
- `xianyu_items.json`
- `xiaohongshu_notes.json`
- `xiaohongshu_comments.json`

本地文件管理页只允许操作 `artifacts/` 和 `exports/` 下的文件。

## 10. 黑话研判链路

当前黑话研判的数据流如下：

1. 手机端采集任务写入 `task_runs + collected_records`
2. 黑话字典页维护 `分类 -> 二级分类 -> 黑话词条`
3. 黑话研判页从本地采集任务中选择一个数据源
4. 选择一个黑话词条后创建研判任务
5. 后端按批次读取结构化记录
6. [ai_text_service.py](d:/CodeList/android-spider/src/services/ai_text_service.py) 调用 Qwen 兼容接口执行判定
7. 结果写入 `jargon_analysis_tasks + jargon_analysis_results`
8. 研判结果页与研判记录页展示命中情况

当前字段适配原则：

- 旧项目黑话逻辑保留
- 旧网页端爬虫字段不直接复用
- 先做结构化字段映射，再接入手机端数据

## 11. 现有 Demo 配置

可直接运行的配置文件：

- [configs/settings_demo.yaml](d:/CodeList/android-spider/configs/settings_demo.yaml)
- [configs/xianyu_search_demo.yaml](d:/CodeList/android-spider/configs/xianyu_search_demo.yaml)
- [configs/xiaohongshu_search_demo.yaml](d:/CodeList/android-spider/configs/xiaohongshu_search_demo.yaml)

辅助脚本：

- [scripts/setup_windows.ps1](d:/CodeList/android-spider/scripts/setup_windows.ps1)
- [scripts/run_settings_demo.ps1](d:/CodeList/android-spider/scripts/run_settings_demo.ps1)
- [scripts/run_xianyu_demo.ps1](d:/CodeList/android-spider/scripts/run_xianyu_demo.ps1)
- [scripts/run_xiaohongshu_demo.ps1](d:/CodeList/android-spider/scripts/run_xiaohongshu_demo.ps1)

## 12. 当前边界与限制

- 当前仍以单任务串行为主
- CLI 默认仍按“第一个在线设备”执行，桌面端支持显式选设备
- 黑话研判只覆盖闲鱼 `listing` 与小红书 `note`
- 小红书评论已采集，但本轮没有接入黑话研判主链
- 当前历史采集记录里如果没有稳定落库 `image_url` / 原始链接，黑话结果展示会以文本和指标为主
- 不包含旧网页端 cookie 爬虫
- 不包含飞书上传
- 不包含 OCR、图像识别、抓包、逆向、反检测
- 如果目标 App UI 变化较大，需要重新抓 dump 并调整适配器或选择器

## 13. 开发校验

Python 侧：

```powershell
.\.venv\Scripts\python.exe -m compileall src main.py
```

桌面端类型检查：

```powershell
Set-Location .\desktop
npm run typecheck
```

## 14. 新增平台或功能时的建议

新增采集平台：

1. 在 `src/adapters/` 下新增适配器
2. 在 `configs/` 下新增 YAML
3. 保持结构化记录输出到 `CollectedRecord`
4. 如需接入黑话研判，优先补齐字段映射，不要直接复制旧逻辑

新增黑话相关能力：

1. 优先复用 [analysis_store.py](d:/CodeList/android-spider/src/storage/analysis_store.py)
2. 优先复用现有 `/api/jargon-analysis/*` 链路
3. 避免把旧项目网页端强耦合逻辑直接迁入当前架构
