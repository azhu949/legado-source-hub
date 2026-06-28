# 📚 聚合书源管理系统

在阅读应用（Legado / 阅读3.0）生态中统一管理多个第三方书源的中间代理层。对外暴露**一个虚拟聚合书源**供阅读 APP 导入，内部并发请求多个子书源，自动去重、择优、聚合。

同时提供 **Web 管理后台**，支持书源增删改查、规则实时测试、健康监控、操作日志等。

## ✨ 核心特性

- **多源聚合搜索**：异步并发请求所有子书源，按指纹 + 相似度去重，按权重排序
- **规则引擎**：支持 JsonPath / XPath / CSS 选择器 / 正则四种提取规则
- **Web 管理后台**：React + shadcn/ui，书源 CRUD、批量导入/导出
- **规则测试工具**：实时抓取源站，展示原始响应与提取结果
- **健康监控**：定时探测子书源可用性，记录趋势，异常高亮
- **操作日志**：所有管理操作留痕，支持筛选与导出
- **缓存加速**：Redis 缓存搜索/详情/目录，降低重复请求

## 🏗 技术栈

| 端   | 技术                                                                               |
| :--- | :--------------------------------------------------------------------------------- |
| 后端 | FastAPI · aiohttp · lxml · BeautifulSoup · jsonpath-ng · Redis · SQLite            |
| 前端 | React 18 · TypeScript · Vite · Tailwind CSS · shadcn/ui · Zustand · TanStack Table |
| 部署 | Docker Compose · Nginx                                                             |

## 🚀 快速开始

### Docker 一键部署（推荐）

```bash
# 1. 克隆项目
git clone <repo-url> && cd book-aggregator

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，修改 ADMIN_PASS 和 SECRET_KEY

# 3. 一键启动
docker compose up -d

# 4. 访问
#    管理后台:  http://localhost:8080/admin
#    聚合书源:  登录后台后在「聚合书源」页创建访问用户并复制导入地址
```

默认管理员账号：`admin` / `admin123`（请务必在 `.env` 中修改）。

Docker 部署默认使用 `novl_backend_data` 持久化后端数据，避免 Windows 盘符路径在 bind mount 中被错误解析。备份数据可执行：

```bash
docker cp novl-backend-1:/app/data ./backup-data
```

### 本地开发

**后端**：

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  
# Windows:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

**前端**：

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173/admin
```

## 📖 使用说明

### 1. 导入聚合书源到阅读 APP

在管理后台左侧进入「聚合书源」，为阅读设备创建访问用户并复制该用户的导入地址。搜索时，系统会自动并发所有已配置的子书源并聚合返回。

### 2. 管理后台

- **仪表盘**：查看书源总数、搜索量、异常数、平均延迟
- **聚合书源**：为不同阅读设备或使用者生成独立导入地址，可单独禁用、删除、重置口令，并查看对应 JSON
- **书源管理**：新增 / 编辑 / 启禁用 / 删除子书源，支持批量导入（粘贴JSON / 上传文件 / 远程URL）
- **规则测试**：填入 URL 和规则，实时查看源站响应与提取结果
- **健康监控**：查看各书源可用性与响应延迟趋势
- **操作日志**：所有管理操作记录

### 3. 子书源格式

子书源采用标准 Legado 书源 JSON 格式，保存在 `backend/data/sources/` 目录，每个文件一个源。

## 📂 项目结构

```
book-aggregator/
├── backend/                 # 后端 (FastAPI)
│   ├── app/
│   │   ├── api/             # API 路由（对外 + 管理）
│   │   ├── core/            # 核心模块（规则引擎/聚合器/缓存等）
│   │   ├── models/          # 数据模型
│   │   └── utils/           # 工具函数
│   ├── data/                # 运行数据（书源JSON + SQLite）
│   └── tests/               # 单元测试
├── frontend/                # 前端 (React + Vite)
│   ├── src/
│   │   ├── api/             # API 层
│   │   ├── components/      # 组件
│   │   ├── pages/           # 页面
│   │   ├── stores/          # 状态管理
│   │   └── types/           # 类型定义
│   └── nginx.conf           # Nginx 配置
├── docker-compose.yml       # 容器编排
├── aggregate_source.json    # 对外聚合书源定义
└── .env.example             # 环境变量示例
```

## 🔧 配置项

| 变量                    | 说明               | 默认值                  |
| :---------------------- | :----------------- | :---------------------- |
| `ADMIN_USER`            | 管理员用户名       | `admin`                 |
| `ADMIN_PASS`            | 管理员密码         | `admin123`              |
| `SECRET_KEY`            | JWT 签名密钥       | (生产必须修改)          |
| `PUBLIC_URL`            | 对外访问地址（留空自动按当前访问域名生成） | 空 |
| `HEALTH_CHECK_INTERVAL` | 健康检查间隔(分钟) | `30`                    |
| `LOG_LEVEL`             | 日志级别           | `INFO`                  |

## 🧪 运行测试

```bash
cd backend
pip install pytest
pytest tests/public -v
```

含真实站点的验证用例只放本地 `backend/tests/private/`，该目录已被 Git 忽略。

## 🔒 安全建议

1. 生产环境务必修改 `ADMIN_PASS` 和 `SECRET_KEY`
2. 公网部署建议在后台创建访问用户，只把带用户 key 的导入地址发给自己的阅读 APP；泄露后重置或禁用该用户即可失效
3. Nginx 层配置 HTTPS（Let's Encrypt）
4. 管理后台路径可加 IP 白名单
5. Redis 建议配置密码认证
6. 定期备份 Docker 部署数据（如 `docker cp novl-backend-1:/app/data ./backup-data`）

## 📄 License

MIT
