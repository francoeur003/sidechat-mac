<p align="center"><img src="assets/sidechat-logo.png" width="112" alt="侧语 SideChat Logo"></p>
<h1 align="center">侧语 SideChat</h1>
<p align="center">贴在微信旁边的 Mac 聊天助手：读懂文字，给出可选择的回复。</p>

[下载 Mac 版](https://github.com/francoeur003/sidechat-mac/releases/latest) · [安装说明](docs/安装说明.txt) · [原项目与许可](NOTICE.md)

## 下载和安装

当前发行包：**macOS 14+ / Apple Silicon（M1 及更新芯片）**。

1. 在 Releases 下载 `SideChat-0.1.0-macOS-arm64.dmg`，将 SideChat 拖进 Applications。
2. 打开应用，在「设置」填写 **GPT / OpenAI** 或 **DeepSeek** 的 API Key，选一个使用即可。
3. 点击「测试连接」，勾选聊天文字处理授权，保存。
4. 按系统提示授予屏幕录制权限。需要「填入」时，再授予辅助功能权限。
5. 打开微信，在助手里「框选范围」，只框右侧聊天消息，不含会话列表、标题或输入框。

**已内置运行环境，无需 Python、uv、终端或下载本地大模型。**

此社区包使用 ad-hoc 签名，**尚无 Apple Developer ID 签名和公证**；macOS 首次打开可能阻止运行。确认下载来源及 `SHA256SUMS.txt` 后，由使用者自行在系统设置 → 隐私与安全性允许打开。不要关闭全局 Gatekeeper。Intel 版本未构建、未验收。

## 功能

- 240 点宽的原生侧边浮窗，等待状态收短窗口。
- 在本机截取指定微信窗口，用 Apple Vision OCR 识别校准区域里的文字气泡。
- 区分对方和自己的消息；切换聊天时隔离旧结果，自己发完消息后等待新消息。
- 通过所选 GPT / DeepSeek 接口分析意图、生成候选并排序；无需额外 Jev Key。
- 每种话术生成两条候选；更多话术在设置里选择，面板可展开更多候选。
- 「复制」和「填入」由用户操作；**不会自动发送微信消息**。
- GPT、DeepSeek Key 独立保存在 macOS Keychain，不存入项目或安装包。

默认模型是 `gpt-4.1-mini` / `deepseek-flash`。模型输入框可修改为该服务商支持的兼容 Chat Completions 模型；不同模型可能要求不同参数，其他模型未逐一验收。GPT 需要 OpenAI API 账户额度，ChatGPT 订阅不等同于 API 额度。

## 数据与费用

- 截图只在本机用于 OCR，临时文件随后清理。
- 开始使用前须授权：**识别出的聊天文字、近期上下文和候选回复会发送给你选中的服务商**。
- Key 只发送给对应官方服务商，不经本项目服务器。项目没有中转服务器。
- 测试连接、意图分析、生成和排序都会产生 API 请求，费用记在你自己的服务商账户。
- 群聊频繁更新时可能为被后续消息替代的内容产生请求；可用菜单栏「暂停读屏」停止新请求。
- 模型的意图、风险、适合度分数都是估计，不代表经过校准的概率，也不保证客观“最优”。请检查后再使用。

本地设置：`~/Library/Application Support/SideChat/`；运行日志：`~/Library/Logs/SideChat.log`。不读取原 Jev 助手的私人环境文件或 Key。

## 当前边界与验收

- 支持已校准的浅色微信桌面布局。窗口尺寸变化后需重新框选；不读取微信数据库。
- 图片、表情和语音暂不支持；最新消息不是文字时，可能等待下一条可读文字。
- 框选时请避开侧栏与输入框。识别不对时检查聊天标题及消息是否匹配，再重新框选。
- 已通过 21 项回归/接口隔离测试；DeepSeek 示例完成「意图 → 2 条回复 → 排序」真实调用。
- 已验证打包应用首次启动、两个 Key 设置入口、空 Key 提示、授权校验和紧凑等待窗。
- GPT 真实付费请求、不同 Mac、Intel、完整分发包微信权限及「填入」链路尚未重新验收。
- 作者抖音主页入口已预留；作者提供真实链接后启用，当前入口处于未配置状态。

## 从源码构建

原 Jev 入口保留，分发版使用独立入口 `src/sidechat_app.py`。

```sh
uv venv --python 3.12 build/distribution-venv
uv pip install --python build/distribution-venv/bin/python -r packaging/requirements-sidechat.txt
build/distribution-venv/bin/python -m unittest discover -s tests -v
./packaging/build_sidechat.sh
```

构建仅包含源码、公共元数据和运行依赖，不复制用户目录、Keychain、截图或本机配置。发布前核对输出文件及校验和。生成物位于 `dist/`。

作者链接配置：`src/sidechat_brand.py` 的 `DOUYIN_URL`，留空时不会打开猜测的链接。

## 致谢与许可

基于 [jev-chat/jev-chat-jarvis-mac](https://github.com/jev-chat/jev-chat-jarvis-mac) 修改，保留原作者 eatmoreduck 的版权及 MIT 许可。详见 [LICENSE](LICENSE)、[NOTICE.md](NOTICE.md) 与[上游说明](docs/UPSTREAM_README.md)。

这是独立社区项目，与微信、OpenAI、DeepSeek、Jev 官方无隶属关系。
