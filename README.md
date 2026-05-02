本目录提供一个单容器的中转管理实例：

- 管理页：`http://127.0.0.1:18080`
- 对外代理端口：`11080-11120`
- 当前运行模式：
  - Docker `bridge` 网络
  - `xray` 单进程承载所有 `xray` 节点
  - `sing-box` 单进程承载所有 `sing-box` 节点

当前这套已经验证可用，不再使用 `host` 网络。

运行时生成的本地状态文件：

- `nodes.json`
- `settings.json`
- `xray-config.json`
- `singbox-config.json`
- `singbox.d/`

都已经加入忽略列表，不会提交到 Git 仓库。

**启动**
```bash
cd /home/liubai/docker/xray-relay
docker compose up -d --build
```

如果你希望先显式准备环境变量：

```bash
cd /home/liubai/docker/xray-relay
cp .env.example .env
docker compose up -d --build
```

当前 `docker-compose.yml` 自带默认值，所以不复制 `.env` 也能直接启动。

默认构建会锁定已经验证通过的 `xray` / `sing-box` 镜像 digest，保证可复现。

如果你想跟随上游更新，也可以在 `.env` 里改成 tag，例如：

```text
XRAY_IMAGE=ghcr.io/xtls/xray-core:latest
SINGBOX_IMAGE=ghcr.io/sagernet/sing-box:latest
```

更推荐的做法仍然是先在测试环境确认，再升级生产实例。

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

**当前支持协议**

- `vmess://`
- `vless://`
- `trojan://`
- `ss://`
- `hysteria2://`
- `tuic://`

页面里新增或编辑节点时，直接粘贴对应分享链接即可。

**内核建议**

- `vmess://`
  推荐：`sing-box`
  说明：当前已验证 `阿里-香港`、`769-香港` 都可在 `sing-box` 下正常工作。

- `vless://`
  推荐：`xray` 或 `sing-box`
  说明：两者都已接入；当前实验节点 `lab-vless` 已验证可用。

- `trojan://`
  推荐：`xray` 或 `sing-box`
  说明：两者都已接入；当前实验节点 `lab-trojan` 已验证可用。

- `ss://`
  推荐：普通节点优先 `xray`
  说明：无 plugin 的 `ss://` 在 `xray` / `sing-box` 都可用；带 plugin 的 `ss://` 目前限制为 `sing-box`。

- `hysteria2://`
  推荐：`sing-box`
  说明：当前实验节点 `lab-hy2` 已验证可用。

- `tuic://`
  推荐：`sing-box`
  说明：当前实验节点 `lab-tuic` 已验证可用。

**端口规划**

当前 `docker-compose.yml` 已经映射：

- 管理页：`18080`
- 代理端口范围：`11080-11120`

推荐分配方式：

- `11080`：正式节点
- `11081`：正式节点
- `11082-11120`：后续新增节点

如果后面端口不够，再把范围扩到更大区间即可，例如：

- `11080-11200`
- `11080-12000`

**环境变量**

示例文件：

- [.env.example](/home/liubai/docker/xray-relay/.env.example)

当前主要变量：

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

其中：

- `SINGBOX_MODE=single`
  表示当前使用“单个 sing-box 进程承载多个节点”的模式
- `SINGBOX_MODE=per_node`
  表示每个 sing-box 节点独立一个进程

当前已验证推荐使用：

```text
SINGBOX_MODE=single
```

**日志级别**

管理页已支持分别设置：

- `xray` 日志级别
- `sing-box` 日志级别

当前配置保存在：

- [settings.json](/home/liubai/docker/xray-relay/settings.json)

默认值：

- `xray_log_level = warning`
- `singbox_log_level = info`

如果你要看更细的请求细节，可以临时把：

- `xray` 调成 `debug`
- `sing-box` 调成 `trace`

再执行：

```bash
docker logs -f xray-relay
```

**数据文件**

核心数据与生成配置位于：

- [nodes.json](/home/liubai/docker/xray-relay/nodes.json)
- [xray-config.json](/home/liubai/docker/xray-relay/xray-config.json)
- [singbox-config.json](/home/liubai/docker/xray-relay/singbox-config.json)
- [settings.json](/home/liubai/docker/xray-relay/settings.json)

说明：

- `nodes.json`：管理页维护的节点数据
- `xray-config.json`：所有 `kernel=xray` 的节点汇总配置
- `singbox-config.json`：所有 `kernel=sing-box` 的节点汇总配置
- `settings.json`：日志等级等管理设置

这些文件都是运行态文件，已加入 `.gitignore`，不会被提交到仓库。

**和 daed 配合使用**

管理页导入节点后，会生成本地节点，例如：

- `socks5://127.0.0.1:11080#阿里-香港`
- `socks5://127.0.0.1:11081#769-香港`

然后把这些本地 `socks5://127.0.0.1:端口` 节点导入 `daed` 即可。

重要：

在把这些本地 `socks5` 节点放入 `daed` / `dae` 使用前，请确保 `dae` 的 `routing` 中保留：

```txt
pname(xray) -> must_direct
```

如果缺少这条规则，容易出现回环或嵌套代理问题。

**Git 仓库说明**

当前 Git 仓库只提交这些源码和部署文件：

- `.dockerignore`
- `.gitignore`
- `README.md`
- `docker-compose.yml`
- `single/`

不会提交：

- `nodes.json`
- `settings.json`
- `xray-config.json`
- `singbox-config.json`
- `singbox.d/`
