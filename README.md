本项目提供一个单容器的中转管理实例。

当前特性：

- 管理页端口：`18080`
- 代理端口范围：`11080-11120`
- Docker `bridge` 网络
- `xray` 单进程承载所有 `kernel=xray` 的节点
- `sing-box` 单进程承载所有 `kernel=sing-box` 的节点

当前支持导入的分享链接协议：

- `vmess://`
- `vless://`
- `trojan://`
- `ss://`
- `hysteria2://`
- `tuic://`

**启动**
```bash
docker compose up -d --build
```

如果你希望先准备环境变量：

```bash
cp .env.example .env
docker compose up -d --build
```

`docker-compose.yml` 自带默认值，不复制 `.env` 也能直接启动。

**状态**
```bash
docker compose ps
docker logs -f xray-relay
```

**管理页**
```text
http://127.0.0.1:18080
http://你的机器IP:18080
```

**内核建议**

- `vmess://`
  推荐：`sing-box`

- `vless://`
  推荐：`xray` 或 `sing-box`

- `trojan://`
  推荐：`xray` 或 `sing-box`

- `ss://`
  推荐：普通节点优先 `xray`
  说明：带 plugin 的 `ss://` 当前限制为 `sing-box`

- `hysteria2://`
  推荐：`sing-box`

- `tuic://`
  推荐：`sing-box`

**端口规划**

当前默认映射：

- 管理页：`18080`
- 代理端口：`11080-11120`

建议分配方式：

- `11080-11081`：长期正式节点
- `11082-11120`：后续新增节点

如果端口不够，可以扩大范围，例如：

- `11080-11200`
- `11080-12000`

**环境变量**

示例文件：`.env.example`

主要变量：

- `ADMIN_PORT`
- `PORT_RANGE_START`
- `PORT_RANGE_END`
- `TZ`
- `XRAY_IMAGE`
- `SINGBOX_IMAGE`
- `XRAY_BIN`
- `XRAY_CONFIG`
- `SINGBOX_BIN`
- `SINGBOX_CONFIG`
- `SINGBOX_MODE`

说明：

- `SINGBOX_MODE=single`
  表示使用“单个 sing-box 进程承载多个节点”的模式

- `SINGBOX_MODE=per_node`
  表示每个 sing-box 节点独立一个进程

当前推荐：

```text
SINGBOX_MODE=single
```

**镜像版本策略**

默认构建会锁定已经验证通过的 `xray` / `sing-box` 镜像 digest，保证可复现。

如果你希望跟随上游更新，可以在 `.env` 中改成 tag，例如：

```text
XRAY_IMAGE=ghcr.io/xtls/xray-core:latest
SINGBOX_IMAGE=ghcr.io/sagernet/sing-box:latest
```

更推荐先在测试环境验证，再升级正式实例。

**日志级别**

管理页已支持分别设置：

- `xray` 日志级别
- `sing-box` 日志级别

默认值：

- `xray_log_level = warning`
- `singbox_log_level = info`

如果需要更详细的请求日志，可以临时调整为：

- `xray = debug`
- `sing-box = trace`

然后执行：

```bash
docker logs -f xray-relay
```

**运行时文件**

以下文件属于运行态数据，不会提交到 Git 仓库：

- `data/nodes.json`
- `data/settings.json`
- `data/xray-config.json`
- `data/singbox-config.json`
- `data/singbox.d/`
- `bin/`

这些文件已经加入 `.gitignore`。

**与 daed / dae 配合使用**

管理页导入节点后，会生成本地节点，例如：

```text
socks5://127.0.0.1:11080#节点名
```

然后把这些本地 `socks5://127.0.0.1:端口` 节点导入到 `daed` 即可。

重要：

在把这些本地节点放入 `dae` 使用前，请确保 `routing` 中保留：

```txt
pname(xray) -> must_direct
```

否则可能出现回环或嵌套代理问题。

**Git 仓库说明**

Git 仓库只提交这些源码和部署文件：

- `.dockerignore`
- `.gitignore`
- `.env.example`
- `README.md`
- `docker-compose.yml`
- `single/`
