"""Reusable sliders that can request one seek from a track click."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ClickableSlider(QSlider):
    """A slider that reports track clicks without owning playback state."""

    seekRequested = Signal(int)

    def _style_option(self) -> QStyleOptionSlider:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return option

    def value_from_track_position(self, position: QPoint | QPointF) -> int:
        """Map a click to a value using Qt's actual groove and handle geometry."""
        point = position.toPoint() if isinstance(position, QPointF) else position
        option = self._style_option()
        style = self.style()
        groove = style.subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        handle = style.subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )

        if self.orientation() == Qt.Orientation.Horizontal:
            slider_minimum = groove.x()
            slider_maximum = groove.right() - handle.width() + 1
            clicked_position = point.x() - handle.width() // 2
        else:
            slider_minimum = groove.y()
            slider_maximum = groove.bottom() - handle.height() + 1
            clicked_position = point.y() - handle.height() // 2

        span = max(0, slider_maximum - slider_minimum)
        offset = max(0, min(span, clicked_position - slider_minimum))
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            offset,
            span,
            option.upsideDown,
        )

    def _track_hit_rect(self, option: QStyleOptionSlider):
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        if self.orientation() == Qt.Orientation.Horizontal:
            extra = max(0, 20 - groove.height()) // 2
            return groove.adjusted(0, -extra, 0, extra)
        extra = max(0, 20 - groove.width()) // 2
        return groove.adjusted(-extra, 0, extra, 0)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        option = self._style_option()
        style = self.style()
        point = event.position().toPoint()
        handle = style.subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        if handle.contains(point) or not self._track_hit_rect(option).contains(point):
            super().mousePressEvent(event)
            return

        value = self.value_from_track_position(point)
        self.setValue(value)
        self.seekRequested.emit(value)
        event.accept()
