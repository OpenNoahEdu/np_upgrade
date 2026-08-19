# Noah-Get 工具集

本工具集用于从 Noah 官方服务器抓取、解析和下载学习机的固件升级包和相关资源。

## 工具列表

- **`noah-get.py`**: 负责从接口递归获取资源目录树，并生成完整的 YAML 结构元数据。
- **`noah-md.py`**: 读取 YAML 数据，渲染生成易于阅读的 Markdown 文档列表。
- **`noah-sync.py`**: 读取 YAML 数据，并将所有资源下载到本地，支持断点续传和自动构建与线上一致的目录结构。

## 使用示例

### 1. 生成 Markdown 文档
使用管道将 YAML 数据传给渲染脚本：
```bash
./scripts/noah-get.py NP1100 | ./scripts/noah-md.py > list.md
```

### 2. 批量同步下载资源
拉取型号的所有数据，并直接下载到本地：
```bash
./scripts/noah-get.py NP1100 | ./scripts/noah-sync.py --verify-md5
```

## 资源下载列表

本仓库通过 GitHub Actions 定期自动拉取最新升级包，详细下载地址清单请查看：
👉 [upgrade.md](./upgrade.md)
