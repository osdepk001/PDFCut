"""
PDF Cut —— 无损删页工具 (开源)
UI: PySide6 + PyQt-Fluent-Widgets
核心: pypdf (结构化无损编辑) + PyMuPDF (缩略图)

功能:
  - 打开 PDF, 网格缩略图预览
  - 勾选保留/删除
  - 全选保留 / 全选删除 / 反选
  - 页码范围批量删除 (如 "3-5,8")
  - 拖拽重排页面顺序
  - 一键导出无损 PDF (文字/矢量原样保留, 可复制)

依赖:
  pip install pyside6 pyside6-fluent-widgets pypdf pymupdf pillow
"""

import os
import re
import sys
import webbrowser
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QWidget,
                               QHBoxLayout, QVBoxLayout, QLabel, QFileDialog,
                               QMessageBox, QLineEdit)
import pymupdf as fitz
from pypdf import PdfReader, PdfWriter
from qfluentwidgets import (FluentWindow, FluentIcon, PushButton, CheckBox,
                            InfoBar, InfoBarPosition, BodyLabel, LineEdit,
                            CardWidget, setTheme, Theme, HyperlinkLabel,
                            StrongBodyLabel)

THUMB_W = 160
THUMB_H = 210


def logo_path():
    """返回 logo 路径, 兼容开发环境与 PyInstaller 单文件打包环境。"""
    if getattr(sys, "frozen", False):
        # 打包后资源在 _MEIPASS 临时目录
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", "PDFCut_logo.png")


# ---------------- 单个页面卡片 ----------------
class PageCard(CardWidget):
    """缩略图 + 保留勾选，承载在一行 list item 中。"""
    def __init__(self, index, pixmap, keep=True, parent=None):
        super().__init__(parent)
        self.index = index  # 当前在列表中的逻辑序号 (0基)
        self.setFixedSize(THUMB_W + 24, THUMB_H + 56)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.img_label = QLabel()
        self.img_label.setPixmap(pixmap.scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))
        self.img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.img_label)

        self.title = BodyLabel(f"第 {index + 1} 页")
        self.title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title)

        self.chk = CheckBox("保留")
        self.chk.setChecked(keep)
        layout.addWidget(self.chk, alignment=Qt.AlignCenter)

    def set_index(self, i):
        self.index = i
        self.title.setText(f"第 {i + 1} 页")


# ---------------- 主窗口 ----------------
class PDFCutWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Cut —— 无损删页工具")
        self.resize(1100, 720)

        # 设置软件 logo
        lp = logo_path()
        if os.path.exists(lp):
            self.setWindowIcon(QIcon(lp))

        # 隐藏 FluentWindow 左上角返回箭头
        self.navigationInterface.setReturnButtonVisible(False)

        self.pdf_path = None
        self.doc = None
        self.order = []        # 逻辑页序: order[list_pos] = pdf_page_index
        self.keep = {}         # pdf_page_index -> bool (保留?)

        self._init_ui()

    # ---------- UI ----------
    def _init_ui(self):
        # 子页面
        self.page = QWidget()
        self.page.setObjectName("editPage")
        self.addSubInterface(self.page, FluentIcon.DOCUMENT, "编辑")
        self.setMinimumWidth(900)

        # 关于页面
        self._init_about_page()

        root = QVBoxLayout(self.page)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 顶部工具栏
        bar = QHBoxLayout()
        self.btn_open = PushButton(FluentIcon.FOLDER, "打开 PDF")
        self.btn_open.clicked.connect(self.open_pdf)
        self.btn_export = PushButton(FluentIcon.SAVE, "导出 PDF")
        self.btn_export.clicked.connect(self.export_pdf)
        self.btn_keep_all = PushButton(FluentIcon.ACCEPT, "全选保留")
        self.btn_keep_all.clicked.connect(lambda: self._set_all(True))
        self.btn_del_all = PushButton(FluentIcon.DELETE, "全选删除")
        self.btn_del_all.clicked.connect(lambda: self._set_all(False))
        self.btn_inv = PushButton(FluentIcon.SYNC, "反选")
        self.btn_inv.clicked.connect(self._invert)

        self.range_edit = LineEdit()
        self.range_edit.setPlaceholderText('范围删除, 如 "3-5,8"')
        self.range_edit.setFixedWidth(180)
        self.btn_range = PushButton(FluentIcon.FILTER, "应用范围")
        self.btn_range.clicked.connect(self.apply_range)

        self.info = BodyLabel("未打开文件")
        self.info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        for w in (self.btn_open, self.btn_export, self.btn_keep_all,
                  self.btn_del_all, self.btn_inv, self.range_edit,
                  self.btn_range):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.info)
        root.addLayout(bar)

        # 缩略图列表 (可拖拽重排)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setMovement(QListWidget.Snap)
        self.list.setSpacing(10)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setWordWrap(True)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDropIndicatorShown(True)
        root.addWidget(self.list)

    # ---------- 关于页面 ----------
    def _init_about_page(self):
        self.about_page = QWidget()
        self.about_page.setObjectName("aboutPage")
        self.addSubInterface(self.about_page, FluentIcon.INFO, "关于")

        root = QVBoxLayout(self.about_page)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignTop)

        # 标题
        title = StrongBodyLabel("PDF Cut · 无损删页工具")
        title.setStyleSheet("font-size: 22px;")
        root.addWidget(title)

        # 开发者
        dev = BodyLabel()
        dev.setText("开发者：OsDepK")
        dev.setStyleSheet("font-size: 15px;")
        root.addWidget(dev)

        # 社区链接 (点击打开浏览器 http://osdepk.cn)
        comm = BodyLabel()
        comm.setText("欢迎访问：")
        comm.setStyleSheet("font-size: 15px;")
        link = HyperlinkLabel()
        link.setText("深度Os社区")
        link.setUrl("http://osdepk.cn")
        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(2)
        hbox.addWidget(comm)
        hbox.addWidget(link)
        hbox.addStretch(1)
        root.addLayout(hbox)

        # 协议
        lic = BodyLabel()
        lic.setText("协议：本应用遵循 MIT 开源协议")
        lic.setStyleSheet("font-size: 15px;")
        root.addWidget(lic)

        root.addStretch(1)

    # ---------- 打开 ----------
    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF 文件 (*.pdf)")
        if not path:
            return
        try:
            doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))
            return

        if self.doc is not None:
            self.doc.close()
        self.pdf_path = path
        self.doc = doc
        n = doc.page_count
        self.order = list(range(n))
        self.keep = {i: True for i in range(n)}

        self.list.clear()
        for i in range(n):
            self._add_card(i)
        self.info.setText(f"{os.path.basename(path)}  |  共 {n} 页")
        InfoBar.success("已打开", f"共 {n} 页", parent=self)

    def _add_card(self, pdf_index):
        page = self.doc[pdf_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img)

        card = PageCard(pdf_index, pixmap, keep=self.keep[pdf_index])
        item = QListWidgetItem(self.list)
        item.setSizeHint(card.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, card)

    # ---------- 批量操作 ----------
    def _set_all(self, val):
        if self.doc is None:
            return
        for i in range(self.list.count()):
            card = self.list.itemWidget(self.list.item(i))
            card.chk.setChecked(val)
            self.keep[card.index] = val

    def _invert(self):
        if self.doc is None:
            return
        for i in range(self.list.count()):
            card = self.list.itemWidget(self.list.item(i))
            nv = not card.chk.isChecked()
            card.chk.setChecked(nv)
            self.keep[card.index] = nv

    def apply_range(self):
        if self.doc is None:
            return
        text = self.range_edit.text().strip()
        if not text:
            return
        n = self.doc.page_count
        to_del = set()
        try:
            for part in text.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-")
                    a, b = int(a), int(b)
                    if a < 1 or b > n or a > b:
                        raise ValueError(part)
                    to_del.update(range(a - 1, b))
                else:
                    x = int(part)
                    if x < 1 or x > n:
                        raise ValueError(part)
                    to_del.add(x - 1)
        except ValueError as e:
            QMessageBox.warning(self, "范围格式错误", f"无法解析: {e}\n请用如 '3-5,8' 的格式")
            return
        for i in range(self.list.count()):
            card = self.list.itemWidget(self.list.item(i))
            card.chk.setChecked(card.index not in to_del)
            self.keep[card.index] = card.index not in to_del
        InfoBar.info("范围删除", f"已标记删除 {len(to_del)} 页", parent=self)

    # ---------- 导出 (无损) ----------
    def export_pdf(self):
        if self.doc is None:
            QMessageBox.warning(self, "未打开", "请先打开 PDF")
            return

        # 收集最终顺序与保留标志
        seq = []
        for i in range(self.list.count()):
            card = self.list.itemWidget(self.list.item(i))
            seq.append(card.index)
        keep_list = [self.keep[idx] for idx in seq]

        if all(keep_list):
            QMessageBox.information(self, "提示", "所有页面都保留, 没有要删除的")
            return
        if not any(keep_list):
            if QMessageBox.question(self, "确认", "将删除所有页面, 导出空文件, 继续?") != QMessageBox.StandardButton.Yes:
                return

        out, _ = QFileDialog.getSaveFileName(
            self, "保存为", "已删页_" + os.path.basename(self.pdf_path),
            "PDF 文件 (*.pdf)")
        if not out:
            return

        try:
            reader = PdfReader(self.pdf_path)
            writer = PdfWriter()
            for idx, keep in zip(seq, keep_list):
                if keep:
                    writer.add_page(reader.pages[idx])
            if reader.metadata:
                writer.add_metadata(reader.metadata)
            with open(out, "wb") as f:
                writer.write(f)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return

        kept = sum(keep_list)
        InfoBar.success("完成", f"保留 {kept} 页, 删除 {len(seq) - kept} 页 (无损)",
                        parent=self, position=InfoBarPosition.TOP)


def main():
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    w = PDFCutWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
