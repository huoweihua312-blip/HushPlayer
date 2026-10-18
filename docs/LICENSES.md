# 第三方依赖与许可

HushPlayer 自身代码以 MIT 许可发布（见仓库根 `LICENSE`）。下表列出运行期实际随程序分发的第三方组件及其许可。
所有依赖均来自 PyPI、npm 官方源或项目官方发布渠道，未使用来源不明的安装脚本。

## 1. Python 运行时依赖

| 组件 | 版本 | 许可 | 用途 |
| --- | --- | --- | --- |
| [PySide6](https://pypi.org/project/PySide6/) / Qt 6 | 6.11.1 | LGPL-3.0（Qt 商业双许可） | 窗口、控件、绘图、多媒体（QtMultimedia 使用 FFmpeg 后端） |
| [mutagen](https://pypi.org/project/mutagen/) | 1.48.1 | GPL-2.0-or-later | 音频标签与封面读取 |
| [Pillow](https://pypi.org/project/Pillow/) | 12.3.0 | MIT-CMU | 封面缩放、品牌图标生成 |
| [requests](https://pypi.org/project/requests/) | 2.34.2 | Apache-2.0 | 在线音频下载、封面下载、LRCLIB 歌词、更新检查 |

Qt 以 LGPL 方式动态链接，允许在闭源/开源应用中分发；PyInstaller 打包时保留 Qt 的动态库与许可声明。若需商业分发并静态链接 Qt，需自行取得 Qt 商业许可。

## 2. 内置 Node 运行时

| 组件 | 版本 | 许可 | 说明 |
| --- | --- | --- | --- |
| [Node.js](https://nodejs.org/) `node.exe` | 22.22.3 | MIT | 仅作为在线音源插件的宿主进程，随安装包分发（86.9 MB） |

## 3. 在线音源插件依赖（`hushplayer/runtime/source_runtime/node_modules`）

| 组件 | 许可 |
| --- | --- |
| axios | MIT |
| big-integer | ISC |
| cheerio | MIT |
| crypto-js | MIT |
| dayjs | MIT |
| he | MIT |
| qs | BSD-3-Clause |
| undici（传递依赖） | MIT |

音源插件本体（`sources/*.js`）来自用户侧安装的 MusicFree 兼容插件，**不随本仓库源码声明版权**；HushPlayer 只提供宿主与协议，插件的行为、可用性与合法性由插件来源决定。仓库中保留的插件仅用于本机验证，正式分发时请遵守对应音乐服务的条款。

## 4. 开发期工具（不随程序分发）

| 工具 | 版本 | 许可 | 用途 |
| --- | --- | --- | --- |
| pytest | 9.1.1 | MIT | 测试 |
| pytest-timeout | 2.x | MIT | 测试超时保护 |
| PyInstaller | 6.22.3 | GPL-2.0-with-exception | 生成 Windows 可执行目录 |
| soundfile / libsndfile | 0.14（开发辅助） | BSD-3-Clause / LGPL-2.1 | 仅用于生成测试夹具音频 |

## 5. 内容与素材

- 应用图标、Logo、界面截图均由本项目生成，不含 Apple 或其他品牌的商标与专有素材。
- 测试夹具音频由 `tools/make_fixtures.py` 用合成波形生成，无人声、无版权音乐。
- 歌词数据来自用户本地文件、内嵌标签、在线音源或 [LRCLIB](https://lrclib.net/)（开放歌词库）；界面只做展示。

## 6. 合规说明

- 在线播放/下载仅调用插件提供的公开解析结果，不破解 DRM、不绕过付费墙。
- 当音源因版权、会员或地区限制无法提供资源时，界面给出明确错误提示，而不是伪造可用性。
- 用户应自行确保其使用的音源插件与下载行为符合当地法律与音乐服务条款。

## 内置字体

| 资源 | 许可 | 说明 |
| --- | --- | --- |
| MiSans Regular / Semibold / Bold（`assets/fonts/`） | 小米 MiSans 字体许可 | 仅作应用私有嵌入，不安装到系统、不修改、不单独分发；`MiSans-NOTICE.md` 与许可 PDF 随包提供 |

## 品牌素材

| 资源 | 来源 | 说明 |
| --- | --- | --- |
| `assets/brand/HushPlayer.ico`、`assets/brand/logo.png` | 用户提供 | 仅用于本应用；不得再自造替代标志 |
