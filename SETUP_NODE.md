# 🔌 在你 Y7000 (XTXBDDX, Win11) 上装 OpenClaw 节点

**目标**: 让 dengxian 远程能在你电脑上跑命令、读文件、操作通达信。

**双方设备**:
- 服务端 (gateway): Mac Studio (PDT, 我跑这边)
- 节点 (你这边): XTXBDDX, Win11, 联想 Y7000 2019

---

## ⚠️ 网络层重大问题 (先看这个)

我刚检查 Mac Studio 上的 gateway:
- **绑定 127.0.0.1 (loopback)** — 只听本机
- **没有公网/Tailscale URL**
- 你 Y7000 在中国, **直接连不到** Mac Studio

**结论**: 必须先打通网络。两条路:

### 🅰️ 推荐: Tailscale (免费/加密/中国可用)
- 在 Mac Studio 装 Tailscale 加入 tailnet
- 在 Y7000 装 Tailscale 加入同一个 tailnet
- 两台机就互通了 (像在同一局域网)
- Tailscale 在中国大陆**直连有时不稳**, 退到 DERP 中继可以走通,只是慢一点

### 🅱️ 备选: SSH 隧道 (要 Mac Studio 有公网或 Tailscale)
- 你 Y7000 ssh 到 Mac Studio, 反向打洞
- 复杂,**不推荐除非你熟 SSH**

**今晚先选 Tailscale**。

---

## 📋 完整步骤 (按顺序执行)

### ✅ 阶段 1: Y7000 装 WSL2 (Win11 一键)

打开 **PowerShell (管理员)**, 跑:

```powershell
wsl --install -d Ubuntu-24.04
```

完成后**重启电脑**, WSL2 + Ubuntu 装完。重启后 Ubuntu 会自动启动让你设用户名密码。

> 💡 你可能已经装过 WSL,跑 `wsl --status` 检查。

---

### ✅ 阶段 2: WSL2 里装 Node.js + OpenClaw

进 Ubuntu (开始菜单搜 "Ubuntu"),跑:

```bash
# 装 Node 24
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs

# 验证
node -v
# 应该是 v24.x.x

# 装 OpenClaw
curl -fsSL https://openclaw.ai/install.sh | bash

# 验证
openclaw --version
# 应该是 OpenClaw 2026.4.x
```

---

### ✅ 阶段 3: Y7000 装 Tailscale

**在 Windows 端装** (不是 WSL2),打开 PowerShell 跑:

```powershell
winget install Tailscale.Tailscale
```

或者下载安装包: https://tailscale.com/download/windows

装好后启动 Tailscale,**用你常用的邮箱注册/登录**(Google/Microsoft/Github 账号都行)。

记住你的 **tailnet 名字** (邮箱前缀 + .ts.net),发给我。

---

### ✅ 阶段 4: 我这边 (Mac Studio) 也装 Tailscale

**等你完成阶段3后**, 告诉我:
1. 你的 tailnet 邮箱(我加入同一个 tailnet)
2. Y7000 在 tailnet 里的设备名 (Tailscale 控制台能看,通常就是电脑名 XTXBDDX)
3. Y7000 在 tailnet 里的 IP (100.x.x.x)

我会:
1. 在 Mac Studio 装 Tailscale
2. 加入你的 tailnet
3. 修改 gateway 绑定从 loopback 到 tailscale 接口

---

### ✅ 阶段 5: 配对 Y7000 节点到 Mac Studio gateway

**等阶段4网络通了**之后,在 Y7000 的 WSL2 Ubuntu 里跑:

```bash
# 给我的 Mac Studio 在 tailnet 里的地址 (我会告诉你)
export GATEWAY_HOST="100.x.x.x"  # Mac Studio tailnet IP
export GATEWAY_PORT="18789"

# 启动节点
openclaw node run --host $GATEWAY_HOST --port $GATEWAY_PORT --display-name "XTXBDDX-Y7000"
```

节点启动后会向 gateway **请求配对**,会显示一个 requestId。

**告诉我那个 requestId**,我在 Mac Studio 这边批准:

```bash
openclaw devices approve <requestId>
```

配对成功后,我能跑:

```bash
openclaw nodes invoke --node XTXBDDX-Y7000 --command system.which --params '{"name":"uname"}'
```

收到响应 = 全通!

---

### ✅ 阶段 6: 验证 + 通达信集成

**最简验证** (我跑命令测连通):
```bash
openclaw exec --host node --node XTXBDDX-Y7000 -- "echo hello && hostname"
```

**通达信文件读取** (假设你装在 C:\new_tdx\):
```bash
# 通过 WSL2 读 Windows 路径
ls /mnt/c/new_tdx/T0002/blocknew/
# 看到 .blk 自选股文件即成功
```

**未来扩展**:
- 我可以**写公式 .tne 文件**到你通达信目录
- 我可以**读取你通达信导出的选股结果**
- 进一步可以加 **AutoHotkey** 做 GUI 自动化

---

## 🎯 今晚最低目标 (验证可行)

只要做到下面 4 步就够,**不需要全部完成**:

1. ✅ 装 WSL2 (5分钟)
2. ✅ 装 Tailscale (5分钟)
3. ✅ 我这边也装 Tailscale 加入 tailnet (5分钟)
4. ✅ 验证 ping 互通

**网络通了 = 大局已定**,后面几步都是配置。

---

## 📍 你现在该做的

### 🟢 现在就开始 — 阶段1 (装 WSL2)

打开 PowerShell (管理员),跑:

```powershell
wsl --status
```

把**输出截图给我**,我看你 WSL2 是否已经装好 / 是否需要装。

如果出 "Default Version: 2",说明 WSL2 已就绪,可以跳到阶段2。

---

## 🆘 遇到问题

任何步骤报错,**截图给我**,我看到具体错误能帮你解。

不要硬扛,**网络问题 / 安装失败 95% 都是有解的**,但我得看到错误信息。

— dengxian 👨‍⚕️
