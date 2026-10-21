import pathlib
p = pathlib.Path("hushplayer/ui/widgets/settings_widgets.py")
t = p.read_text(encoding="utf-8")
old = '''        super().__init__(parent)
        self._title = title
        self._description = description
        layout = QHBoxLayout(self)
        # Vertical rhythm follows the type scale, otherwise enlarged labels sit
        # right on top of their description and the card feels cramped.
        pad = theme().scaled(9, factor=0.9)
        layout.setContentsMargins(0, pad, 0, pad)
        layout.setSpacing(theme().scaled(16))
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(theme().scaled(3, factor=1.0))
        self.title_label = _label(title, size=10.0, weight=500)
        self.title_label.setWordWrap(False)
        self.desc_label = _label(description, size=8.8, alpha=0.5)
        text_box.addWidget(self.title_label)
        if description:
            text_box.addWidget(self.desc_label)
        layout.addLayout(text_box, 1)
        self.control = control
        if control is not None:
            layout.addWidget(control, 0, Qt.AlignVCenter)
        self._separator = description != ""

    def add_control(self, control: QWidget) -> None:
        self.control = control
        self.layout().addWidget(control, 0, Qt.AlignVCenter)'''
new = '''        super().__init__(parent)
        self._title = title
        self._description = description
        # Grid so a narrow window can drop the control onto its own line
        # instead of squeezing the text into one or two characters per row.
        self._grid = QGridLayout(self)
        pad = theme().scaled(9, factor=0.9)
        self._grid.setContentsMargins(0, pad, 0, pad)
        self._grid.setHorizontalSpacing(theme().scaled(16))
        self._grid.setVerticalSpacing(theme().scaled(7))
        self._grid.setColumnStretch(0, 1)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(theme().scaled(3, factor=1.0))
        self.title_label = _label(title, size=10.0, weight=500)
        self.title_label.setWordWrap(True)
        self.desc_label = _label(description, size=8.8, alpha=0.5)
        self.desc_label.setWordWrap(True)
        text_box.addWidget(self.title_label)
        if description:
            text_box.addWidget(self.desc_label)
        self._grid.addLayout(text_box, 0, 0)
        self.control = None
        self._stacked = False
        if control is not None:
            self.add_control(control)
        self._separator = description != ""

    # ------------------------------------------------------------ responsive
    def _stack_threshold(self) -> int:
        return theme().scaled(360, factor=0.8)

    def _apply_control_placement(self) -> None:
        if self.control is None:
            return
        stacked = self.width() < self._stack_threshold()
        if stacked == self._stacked and self._grid.indexOf(self.control) != -1:
            return
        self._grid.removeWidget(self.control)
        if stacked:
            self._grid.addWidget(self.control, 1, 0, 1, 2, Qt.AlignLeft | Qt.AlignVCenter)
        else:
            self._grid.addWidget(self.control, 0, 1, Qt.AlignRight | Qt.AlignVCenter)
        self._stacked = stacked

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_control_placement()

    def add_control(self, control: QWidget) -> None:
        self.control = control
        self._stacked = not stacked_placeholder if False else False
        self._grid.addWidget(control, 0, 1, Qt.AlignRight | Qt.AlignVCenter)
        self._apply_control_placement()'''
assert old in t
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("setting row reflows")
