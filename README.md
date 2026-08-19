# PDFCut

一款开源、无损的 PDF 删页工具。基于 `pypdf` 做结构化重组，删除页面后文字、矢量图形、书签等内容**原样保留**，复制与搜索能力不变 —— 不会把页面转成图片。

界面使用 **PySide6 + PyQt-Fluent-Widgets** 构建，简洁现代。

## 功能特性

- 📄 **缩略图网格预览**：打开 PDF 后逐页显示缩略图
- ✅ **勾选删页**：每页可单独勾选「保留 / 删除」
- 🔘 **批量操作**：全选保留 / 全选删除 / 反选
- 🔢 **页码范围批量删除**：输入如 `3-5,8` 一次性标记删除多页
- 🖱️ **拖拽重排**：在网格中拖动页面卡片调整顺序，导出按新顺序输出
- ℹ️ **关于页面**：开发者信息、社区链接、开源协议
- 🎨 **无损导出**：输出 PDF 文字可复制、可搜索，体积小

## 安装与运行（源码）

```bash
pip install -r requirements.txt
python pdf_cut.py
```

依赖：

- `pyside6`
- `pyside6-fluent-widgets`
- `pypdf`
- `pymupdf`
- `pillow`

## 使用 EXE（Windows）

直接双击 `dist/PDFCut.exe` 即可运行，无需安装 Python。

操作：

1. 点击「打开 PDF」选择文件
2. 在缩略图网格中勾选要删除的页面（或填写范围、拖拽重排）
3. 点击「导出 PDF」选择保存位置

## 关于页面

- 开发者：**OsDepK**
- 欢迎访问：深度Os社区（点击自动打开 http://osdepk.cn）
- 协议：本应用遵循 MIT 开源协议

## 打包为 EXE

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name PDFCut ^
    --icon "assets/PDFCut_logo.ico" --add-data "assets;assets" pdf_cut.py
```

生成的 `dist/PDFCut.exe` 为单文件可执行程序。

## 开源协议

本项目基于 [MIT 协议](LICENSE) 开源。

Copyright (c) 2026 OsDepK
