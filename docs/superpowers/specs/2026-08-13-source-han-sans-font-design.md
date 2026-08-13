# Source Han Sans UI 字体替换设计

## 背景

当前界面已经提高了普通文字的 QSS 字重，但用户实际观察到中文仍然偏细。原因是正文主要依赖 Noto Sans SC 可变字体，Windows/Qt 对可变字体中间字重的视觉差异不够明显。

## 方案

- 使用 Adobe 官方 Source Han Sans 简体中文字体的静态 Medium 和 Bold 字体文件。
- 应用字体族统一优先使用 `Source Han Sans SC`，保持现有字体回退链。
- Medium 用于普通正文、导航、元数据和自绘列表文字；Bold 用于标题和当前播放等高层级文字。
- 保留现有 Noto Sans SC 作为注册后的兼容回退字体，不修改用户设置或数据文件。
- 将 Source Han Sans 的 SIL Open Font License 1.1 文本随资源打包。

## 资源与许可

字体来自 Adobe 官方 `adobe-fonts/source-han-sans` 的简体中文发布包。项目只纳入运行所需的 Medium、Bold 字体和许可证文本，下载压缩包不纳入项目资源和提交。

## 风险与回退

- 字体资源会增加安装包体积，预计增加约 33 MB。
- 如果某个字体文件无法加载，Qt 继续使用 Noto Sans SC 或系统字体回退链。
- 不改变字号、颜色、播放逻辑、数据结构和用户设置。

## 验收标准

- Qt 能识别 `Source Han Sans SC` 的 Medium（500）和 Bold（700）字重。
- 主题字体回归测试通过。
- 主窗口、浏览页、在线搜索和响应式布局回归测试通过。
- Windows 源码版和打包配置都能读取字体资源。
