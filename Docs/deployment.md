# 部署与运维

- 适用版本：1.0.0
- 运行形态：本机单用户，默认只监听 `127.0.0.1`

## 1. 环境要求

- Windows 10/11 + PowerShell 5.1
- Python 3.11 及以上
- 无第三方数据库；存档为本地 SQLite

## 2. 一键启动

首次运行安装依赖：

```powershell
.\start.ps1 -Install
```

日常开发（默认离线模拟，不产生外部请求）：

```powershell
.\start.ps1
```

开发时临时启用在线 Provider：

```powershell
.\start.ps1 -Online
```

生产配置档（读取 `.env`，默认在线）：

```powershell
.\start.ps1 -Profile prod
```

生产环境强制离线：

```powershell
.\start.ps1 -Profile prod -Offline
```

也可以双击 `start.bat`，等价于以开发配置档启动。

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-Profile` | `dev` | `dev` 或 `prod` |
| `-Offline` | 关闭 | 强制本地模拟模型 |
| `-Online` | 关闭 | 开发档允许在线 Provider |
| `-Port` | `8000` | 本地端口 |
| `-DatabasePath` | `data/games.db` | 存档路径，支持绝对路径 |
| `-BindHost` | `127.0.0.1` | 监听地址 |
| `-Install` | 关闭 | 创建 `.venv` 并安装依赖 |
| `-OpenBrowser` | 关闭 | 启动后打开浏览器 |

## 3. 配置档

| 配置档 | 默认模型 | 日志级别 | 说明 |
| --- | --- | --- | --- |
| `dev` | 离线模拟 | DEBUG | 防止开发时意外请求外部服务 |
| `prod` | 按 `.env` | INFO | 需要在线模型时使用 |

命令行参数优先于配置档。`GREY_ZONE_OFFLINE=1` 会覆盖任何 Provider 配置。

## 4. 在线模型配置

复制 [.env.example](../.env.example) 为 `.env` 并填写：

- `AI_CURRENT_PROVIDER` / `AI_CURRENT_MODEL`
- `AI_PROVIDER_<n>_NAME` / `_BASE_URL` / `_API_KEY` / `_TIMEOUT_SECONDS` / `_MAX_RETRIES`
- `AI_MODEL_<n>_<m>_NAME`

要求 Provider 兼容 OpenAI Chat Completions。密钥只从环境变量读取，不写入存档、日志、健康接口或导出文件。

## 5. 存档备份与恢复

工具：

```powershell
.\.venv\Scripts\python.exe tools\save_tool.py --db data\games.db backup
```

默认输出到存档同目录 `backups\`，文件名带 UTC 微秒时间戳，备份后自动执行 `PRAGMA quick_check`。

恢复（必须先停止服务，工具会再备份当前库）：

```powershell
.\.venv\Scripts\python.exe tools\save_tool.py --db data\games.db restore data\backups\games-20261106-000000-000000.db --confirm
```

恢复属于破坏性操作：未带 `--confirm` 会拒绝执行。

## 6. 存档导出与导入

命令行：

```powershell
.\.venv\Scripts\python.exe tools\save_tool.py --db data\games.db export <game_id> --out export.json
.\.venv\Scripts\python.exe tools\save_tool.py --db data\games.db import export.json
```

接口：

- `GET /api/games/{game_id}/export`
- `POST /api/games/import`

导出内容包含案件机械历史、叙事文本与玩家假设，不含密钥或运行环境信息。导入通过确定性重放生成全新存档，失败时自动清理半成品。

## 7. 日志与健康检查

- 日志：`data/logs/app.jsonl`，逐行 JSON，单文件 5 MB，保留 3 份。
- 字段：`ts`、`level`、`logger`、`message`，异常时增加 `exception`。
- 健康接口：`GET /api/health`

健康接口只返回：

- `status`、`model`、`offline`
- `schema_version`、`database`
- `model_stats`（请求数、失败数、回退数、累计与最近耗时）
- 在线模式下的 Provider 名称与模型名

不返回密钥、Base URL、存档路径或请求内容。

## 8. 安全基线

- 默认只监听 `127.0.0.1`，不暴露公网。
- 开发档默认离线，CI 与验收使用临时数据库。
- 密钥不落日志、不写存档、不进导出文件。
- 恢复存档必须显式确认，且自动保留安全副本。
- 生产环境建议在 sandbox 与最小权限令牌下运行。

## 9. 数据目录

| 路径 | 用途 |
| --- | --- |
| `data/games.db` | 主存档 |
| `data/backups/` | 运行时备份 |
| `data/logs/` | 结构化日志 |

`data/`、`.env`、`.venv/` 不应提交到版本库。

## 10. 故障排查

- 缺少 `.venv`：运行 `.\start.ps1 -Install`。
- 端口占用：追加 `-Port 8010`。
- PowerShell 脚本乱码：`start.ps1` 必须保存为 UTF-8 BOM。
- 升级后首次启动：程序会自动迁移 schema，并在迁移前写入 `pre-v*` 备份。
