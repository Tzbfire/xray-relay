# 路由配置

本文档为 `dae` 官方路由配置示例的中文整理版，主要用于说明常见路由规则的写法与含义。

路由规则的基本格式如下：

```shell
匹配条件 -> 出口
```

其中，`fallback` 用于定义默认出口，即当所有规则均未命中时流量的去向。

## 配置示例

```shell
### 内置出口：`block`、`direct`、`must_rules`

# `must_rules` 表示：不将 DNS 流量重定向到 dae，而是继续向下匹配规则。
# 对单条规则而言，`direct` 与 `must_direct` 的区别在于：
# `direct` 仍会劫持并处理 DNS 请求（用于流量分流），
# 而 `must_direct` 不会。
# 当 DNS 请求存在流量回环时，`must_direct` 会更有用。
# `must_direct` 也可以写作 `direct(must)`。
# 同理，也支持 `must_groupname`，表示不劫持和处理 DNS 流量，
# 等价于 `groupname(must)`。

### `fallback` 默认出口
# 当没有任何规则命中时，流量将通过 `fallback` 指定的出口。
fallback: my_group

### 域名规则
domain(suffix: v2raya.org) -> my_group  # 等价于 domain(v2raya.org) -> my_group
domain(full: dns.google) -> my_group
domain(keyword: facebook) -> my_group
domain(regex: '\.goo.*\.com$') -> my_group
domain(geosite:category-ads) -> block
domain(geosite:cn)->direct

### 目标 IP 规则
dip(8.8.8.8) -> direct
dip(101.97.0.0/16) -> direct
dip(geoip:private) -> direct

### 源 IP 规则
sip(192.168.0.0/24) -> my_group
sip(192.168.50.0/24) -> direct

### 目标端口规则
dport(80) -> direct
dport(10080-30000) -> direct

### 源端口规则
sport(38563) -> direct
sport(10080-30000) -> direct

### 四层协议规则
l4proto(tcp) -> my_group
l4proto(udp) -> direct

### IP 版本规则
ipversion(4) -> block
ipversion(6) -> ipv6_group

### 源 MAC 规则
mac('02:42:ac:11:00:02') -> direct

### 进程名规则（仅在绑定 WAN 时支持本机进程）
pname(curl) -> direct

### DSCP 规则（匹配 DSCP，适用于 BT 绕过等场景）
### 参考：https://github.com/daeuniverse/dae/discussions/295
dscp(0x4) -> direct

### 多域名规则
domain(keyword: google, suffix: www.twitter.com, suffix: v2raya.org) -> my_group

### 多 IP 规则
dip(geoip:cn, geoip:private) -> direct
dip(9.9.9.9, 223.5.5.5) -> direct
sip(192.168.0.6, 192.168.0.10, 192.168.0.15) -> direct

### “与（AND）”规则
dip(geoip:cn) && dport(80) -> direct
dip(8.8.8.8) && l4proto(tcp) && dport(1-1023, 8443) -> my_group
dip(1.1.1.1) && sip(10.0.0.1, 172.20.0.0/16) -> direct

### “非（NOT）”规则
!domain(geosite:google-scholar,
        geosite:category-scholar-!cn,
        geosite:category-scholar-cn
    ) -> my_group

### 稍复杂的组合规则
domain(geosite:geolocation-!cn) &&
    !domain(geosite:google-scholar,
            geosite:category-scholar-!cn,
            geosite:category-scholar-cn
        ) -> my_group

### 自定义 DAT 文件
domain(ext:"yourdatfile.dat:yourtag")->direct
dip(ext:"yourdatfile.dat:yourtag")->direct

### 设置 fwmark
# 当你希望将流量重定向到特定接口（例如 WireGuard），
# 或者用于其他高级路由场景时，`mark` 会很有帮助。

# 下面给出一个将 Disney 流量重定向到 `wg0` 的示例。
# 你需要按以下步骤设置 `ip rule` 和 `ip route`：
# 1. 让所有带有 `0x800/0x800` 标记的流量使用路由表 `1145`：
# >> ip rule add fwmark 0x800/0x800 table 1145
# >> ip -6 rule add fwmark 0x800/0x800 table 1145
# 2. 为路由表 `1145` 设置默认路由：
# >> ip route add default dev wg0 scope global table 1145
# >> ip -6 route add default dev wg0 scope global table 1145
# 注意：接口 `wg0`、标记 `0x800`、路由表 `1145` 均可自行调整，
# 但它们之间不能冲突。
# 3. 在 dae 配置文件中编写如下路由规则。
domain(geosite:disney) -> direct(mark: 0x800)

### Must rules
# 对于下面这组规则，除 `mosdns` 之外的 DNS 请求都会被强制重定向到 dae。
# 与 `must_direct` / `must_my_group` 不同，来自 `mosdns` 的流量仍会继续匹配后续规则。
pname(mosdns) -> must_rules
ip(geoip:cn) -> direct
domain(geosite:cn) -> direct
fallback: my_group
```
