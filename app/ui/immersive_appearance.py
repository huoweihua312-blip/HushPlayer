from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.services.lyrics_timing import normalize_lyrics_offset_ms


BACKGROUND_MODES = {"default", "cover", "custom"}
BACKGROUND_FILL_MODES = {"cover", "contain"}
APPEARANCE_SETTING_KEYS = {
    "immersive_background_mode",
    "immersive_background_custom_path",
    "immersive_background_blur",
    "immersive_background_darkness",
    "immersive_background_image_opacity",
    "immersive_background_fill_mode",
    "immersive_lyrics_font_scale",
    "immersive_cover_background_enabled",
    "immersive_background_alpha",
}


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return int(default)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(int(minimum), min(int(maximum), number))


@dataclass(frozen=True, slots=True)
class ImmersiveAppearanceConfig:
    background_mode: str = "cover"
    custom_image_path: str = ""
    blur_radius: int = 40
    darkness: int = 68
    image_opacity: int = 100
    fill_mode: str = "cover"
    lyrics_font_scale: int = 100

    @classmethod
    def defaults(cls) -> "ImmersiveAppearanceConfig":
        return cls()

    @classmethod
    def from_settings(cls, settings: dict | None) -> "ImmersiveAppearanceConfig":
        document = settings if isinstance(settings, dict) else {}
        defaults = cls.defaults()

        raw_mode = document.get("immersive_background_mode")
        if isinstance(raw_mode, str) and raw_mode.strip().casefold() in BACKGROUND_MODES:
            mode = raw_mode.strip().casefold()
        else:
            legacy_cover = document.get("immersive_cover_background_enabled", True)
            if not isinstance(legacy_cover, bool):
                legacy_cover = True
            mode = "cover" if legacy_cover else "default"

        raw_path = document.get("immersive_background_custom_path", "")
        custom_path = raw_path.strip() if isinstance(raw_path, str) else ""

        darkness_source = document.get(
            "immersive_background_darkness",
            document.get("immersive_background_alpha", defaults.darkness),
        )
        fill_mode = document.get("immersive_background_fill_mode", defaults.fill_mode)
        if not isinstance(fill_mode, str) or fill_mode.strip().casefold() not in BACKGROUND_FILL_MODES:
            fill_mode = defaults.fill_mode
        else:
            fill_mode = fill_mode.strip().casefold()

        font_scale = _bounded_int(
            document.get("immersive_lyrics_font_scale", defaults.lyrics_font_scale),
            defaults.lyrics_font_scale,
            70,
            160,
        )
        font_scale = max(70, min(160, int(round(font_scale / 5.0) * 5)))

        return cls(
            background_mode=mode,
            custom_image_path=custom_path,
            blur_radius=_bounded_int(
                document.get("immersive_background_blur", defaults.blur_radius),
                defaults.blur_radius,
                0,
                40,
            ),
            darkness=_bounded_int(darkness_source, defaults.darkness, 0, 90),
            image_opacity=_bounded_int(
                document.get(
                    "immersive_background_image_opacity",
                    defaults.image_opacity,
                ),
                defaults.image_opacity,
                20,
                100,
            ),
            fill_mode=fill_mode,
            lyrics_font_scale=font_scale,
        )

    def to_settings(self) -> dict:
        return {
            "immersive_background_mode": self.background_mode,
            "immersive_background_custom_path": self.custom_image_path,
            "immersive_background_blur": int(self.blur_radius),
            "immersive_background_darkness": int(self.darkness),
            "immersive_background_image_opacity": int(self.image_opacity),
            "immersive_background_fill_mode": self.fill_mode,
            "immersive_lyrics_font_scale": int(self.lyrics_font_scale),
            # 兼容旧版本：新字段优先，旧字段仅作为降级读取入口。
            "immersive_cover_background_enabled": self.background_mode == "cover",
            "immersive_background_alpha": int(self.darkness),
        }

    def background_render_signature(self) -> tuple:
        return (
            self.background_mode,
            self.custom_image_path,
            int(self.blur_radius),
            self.fill_mode,
        )


class _RenderSignals(QObject):
    finished = Signal(object)


class _BackgroundRenderTask(QRunnable):
    MAX_SOURCE_SIDE = 3072
    MAX_RENDER_PIXELS = 12_000_000

    def __init__(
        self,
        *,
        generation: int,
        source_key: str,
        source_image: QImage | None,
        custom_path: str,
        target_size: QSize,
        blur_radius: int,
        fill_mode: str,
    ) -> None:
        super().__init__()
        self.generation = int(generation)
        self.source_key = str(source_key)
        self.source_image = QImage(source_image) if source_image is not None else QImage()
        self.custom_path = str(custom_path)
        self.target_size = QSize(target_size)
        self.blur_radius = int(blur_radius)
        self.fill_mode = str(fill_mode)
        self.signals = _RenderSignals()

    @staticmethod
    def _limited_size(size: QSize, max_side: int) -> QSize:
        if not size.isValid() or size.width() <= 0 or size.height() <= 0:
            return QSize()
        if max(size.width(), size.height()) <= max_side:
            return QSize(size)
        return size.scaled(
            QSize(max_side, max_side),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _read_custom_image(self) -> tuple[QImage, str]:
        reader = QImageReader(self.custom_path)
        reader.setAutoTransform(True)
        source_size = reader.size()
        limited_size = self._limited_size(source_size, self.MAX_SOURCE_SIDE)
        if limited_size.isValid() and limited_size != source_size:
            reader.setScaledSize(limited_size)
        image = reader.read()
        if image.isNull():
            return QImage(), reader.errorString() or "图片无法解码"
        return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied), ""

    def _bounded_target_size(self) -> QSize:
        size = QSize(
            max(1, int(self.target_size.width())),
            max(1, int(self.target_size.height())),
        )
        pixels = size.width() * size.height()
        if pixels <= self.MAX_RENDER_PIXELS:
            return size
        ratio = (self.MAX_RENDER_PIXELS / float(pixels)) ** 0.5
        return QSize(
            max(1, int(size.width() * ratio)),
            max(1, int(size.height() * ratio)),
        )

    def _fit_image(self, source: QImage, target_size: QSize) -> QImage:
        aspect_mode = (
            Qt.AspectRatioMode.KeepAspectRatioByExpanding
            if self.fill_mode == "cover"
            else Qt.AspectRatioMode.KeepAspectRatio
        )
        scaled = source.scaled(
            target_size,
            aspect_mode,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self.fill_mode == "cover":
            crop_x = max(0, (scaled.width() - target_size.width()) // 2)
            crop_y = max(0, (scaled.height() - target_size.height()) // 2)
            return scaled.copy(
                crop_x,
                crop_y,
                target_size.width(),
                target_size.height(),
            )

        canvas = QImage(
            target_size,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.drawImage(
            (target_size.width() - scaled.width()) // 2,
            (target_size.height() - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        return canvas

    def _blur_image(self, image: QImage) -> QImage:
        if self.blur_radius <= 0 or image.isNull():
            return image
        divisor = max(1.0, 1.0 + self.blur_radius / 5.0)
        reduced_size = QSize(
            max(1, int(image.width() / divisor)),
            max(1, int(image.height() / divisor)),
        )
        reduced = image.scaled(
            reduced_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return reduced.scaled(
            image.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def run(self) -> None:
        source = QImage(self.source_image)
        loaded_source = QImage()
        error = ""
        if source.isNull() and self.custom_path:
            source, error = self._read_custom_image()
            loaded_source = QImage(source)
        if source.isNull():
            self.signals.finished.emit(
                {
                    "generation": self.generation,
                    "source_key": self.source_key,
                    "source_image": loaded_source,
                    "rendered_image": QImage(),
                    "error": error or "背景图片不可用",
                }
            )
            return
        target_size = self._bounded_target_size()
        rendered = self._fit_image(source, target_size)
        rendered = self._blur_image(rendered)
        self.signals.finished.emit(
            {
                "generation": self.generation,
                "source_key": self.source_key,
                "source_image": loaded_source,
                "rendered_image": rendered,
                "error": "",
            }
        )


class ImmersiveBackgroundView(QWidget):
    availabilityChanged = Signal(bool, str)

    DEBOUNCE_MS = 150
    MAX_CACHE_ENTRIES = 3
    MAX_CACHE_BYTES = 64 * 1024 * 1024

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self.config = ImmersiveAppearanceConfig.defaults()
        self.transparent_mode = True
        self._closed = False
        self._generation = 0
        self._task_running = False
        self._pending_after_task = False
        self._active_task: _BackgroundRenderTask | None = None
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)

        self._cover_track_key = ""
        self._cover_source_key = ""
        self._cover_source_image = QImage()
        self._custom_source_key = ""
        self._custom_source_image = QImage()
        self._rendered_source_key = ""
        self._rendered_pixmap = QPixmap()
        self._cache: OrderedDict[tuple, QImage] = OrderedDict()
        self._cache_bytes = 0
        self._render_count = 0
        self._task_start_count = 0
        self._fallback_active = True
        self._status_text = "默认背景"

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(self.DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._render_latest)

    @property
    def render_count(self) -> int:
        return self._render_count

    @property
    def task_start_count(self) -> int:
        return self._task_start_count

    @property
    def rendered_source_key(self) -> str:
        return self._rendered_source_key

    @property
    def task_running(self) -> bool:
        return bool(self._task_running)

    @property
    def cache_entry_count(self) -> int:
        return len(self._cache)

    @property
    def cache_bytes(self) -> int:
        return int(self._cache_bytes)

    @property
    def fallback_active(self) -> bool:
        return bool(self._fallback_active)

    @property
    def status_text(self) -> str:
        return self._status_text

    def set_transparent_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.transparent_mode == enabled:
            return
        self.transparent_mode = enabled
        self.update()

    def set_config(self, config: ImmersiveAppearanceConfig) -> None:
        if not isinstance(config, ImmersiveAppearanceConfig):
            return
        old_signature = self.config.background_render_signature()
        old_custom_path = self.config.custom_image_path
        self.config = config
        if old_custom_path != config.custom_image_path:
            self._custom_source_key = ""
            self._custom_source_image = QImage()
        if old_signature != config.background_render_signature():
            self._invalidate_and_schedule()
        else:
            self.update()

    def set_cover_pixmap(self, track_key: str, pixmap: QPixmap | None) -> None:
        track_key = str(track_key or "")
        valid_pixmap = pixmap is not None and not pixmap.isNull()
        pixmap_key = int(pixmap.cacheKey()) if valid_pixmap else 0
        source_key = f"cover:{track_key}:{pixmap_key}" if valid_pixmap else ""
        changed = track_key != self._cover_track_key or source_key != self._cover_source_key
        if not changed:
            return
        self._cover_track_key = track_key
        self._cover_source_key = source_key
        # QPixmap -> QImage conversion is intentionally restricted to the GUI thread.
        self._cover_source_image = pixmap.toImage() if valid_pixmap else QImage()
        if self.config.background_mode == "cover":
            self._rendered_pixmap = QPixmap()
            self._rendered_source_key = ""
            self._set_fallback(True, "当前歌曲封面准备中，已显示默认背景")
            self.update()
            self._invalidate_and_schedule()

    def revalidate_custom_image(self) -> None:
        if self.config.background_mode != "custom":
            return
        self._custom_source_key = ""
        self._custom_source_image = QImage()
        self._invalidate_and_schedule()

    def _invalidate_and_schedule(self) -> None:
        if self._closed:
            return
        self._generation += 1
        if self._task_running:
            self._pending_after_task = True
        self._debounce_timer.start(self.DEBOUNCE_MS)

    def _set_fallback(self, active: bool, message: str) -> None:
        next_active = bool(active)
        next_message = str(message)
        changed = self._fallback_active != next_active or self._status_text != next_message
        self._fallback_active = next_active
        self._status_text = next_message
        if changed:
            self.availabilityChanged.emit(not next_active, next_message)

    def _custom_file_key(self) -> tuple[str, str]:
        path_text = self.config.custom_image_path
        if not path_text:
            return "", "尚未选择自定义图片"
        path = Path(path_text).expanduser()
        try:
            if not path.is_file():
                return "", "自定义图片不存在，已回退默认背景"
            stat = path.stat()
            resolved_path = path.resolve()
        except OSError:
            return "", "自定义图片无法读取，已回退默认背景"
        return f"custom:{resolved_path}:{stat.st_mtime_ns}:{stat.st_size}", ""

    def _resolve_source(self) -> tuple[str, QImage, str, str]:
        if self.config.background_mode == "default":
            return "", QImage(), "", "默认 / 纯色背景"
        if self.config.background_mode == "cover":
            if self._cover_source_image.isNull() or not self._cover_source_key:
                return "", QImage(), "", "当前歌曲没有可用封面，已回退默认背景"
            return self._cover_source_key, QImage(self._cover_source_image), "", ""

        source_key, error = self._custom_file_key()
        if not source_key:
            return "", QImage(), "", error
        if source_key == self._custom_source_key and not self._custom_source_image.isNull():
            return source_key, QImage(self._custom_source_image), "", ""
        return source_key, QImage(), self.config.custom_image_path, ""

    def _target_pixel_size(self) -> tuple[QSize, float]:
        dpr = max(1.0, float(self.devicePixelRatioF()))
        return QSize(
            max(1, int(round(self.width() * dpr))),
            max(1, int(round(self.height() * dpr))),
        ), dpr

    def _cache_key(self, source_key: str, target_size: QSize, dpr: float) -> tuple:
        width_bucket = max(64, ((target_size.width() + 63) // 64) * 64)
        height_bucket = max(64, ((target_size.height() + 63) // 64) * 64)
        return (
            source_key,
            width_bucket,
            height_bucket,
            round(dpr, 2),
            int(self.config.blur_radius),
            self.config.fill_mode,
        )

    def _apply_image(self, source_key: str, image: QImage, dpr: float) -> None:
        if self._closed or image.isNull():
            return
        # QPixmap creation remains on the GUI thread.
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(max(1.0, float(dpr)))
        self._rendered_pixmap = pixmap
        self._rendered_source_key = source_key
        self._render_count += 1
        self._set_fallback(False, "背景图片可用")
        self.update()

    def _insert_cache(self, key: tuple, image: QImage) -> None:
        if image.isNull():
            return
        if key in self._cache:
            previous = self._cache.pop(key)
            self._cache_bytes -= int(previous.sizeInBytes())
        image_copy = QImage(image)
        cost = int(image_copy.sizeInBytes())
        if cost <= self.MAX_CACHE_BYTES:
            self._cache[key] = image_copy
            self._cache_bytes += cost
        while (
            len(self._cache) > self.MAX_CACHE_ENTRIES
            or self._cache_bytes > self.MAX_CACHE_BYTES
        ):
            _, removed = self._cache.popitem(last=False)
            self._cache_bytes -= int(removed.sizeInBytes())

    def _render_latest(self) -> None:
        if self._closed or self.width() <= 0 or self.height() <= 0:
            return
        if self._task_running:
            self._pending_after_task = True
            return

        source_key, source_image, custom_path, error = self._resolve_source()
        if not source_key:
            self._rendered_pixmap = QPixmap()
            self._rendered_source_key = ""
            self._set_fallback(True, error or "默认背景")
            self.update()
            return

        target_size, dpr = self._target_pixel_size()
        cache_key = self._cache_key(source_key, target_size, dpr)
        cached = self._cache.get(cache_key)
        if cached is not None and not cached.isNull():
            self._cache.move_to_end(cache_key)
            self._apply_image(source_key, cached, dpr)
            return

        self._task_running = True
        self._pending_after_task = False
        generation = self._generation
        task = _BackgroundRenderTask(
            generation=generation,
            source_key=source_key,
            source_image=source_image,
            custom_path=custom_path,
            target_size=target_size,
            blur_radius=self.config.blur_radius,
            fill_mode=self.config.fill_mode,
        )
        task.signals.finished.connect(
            self._on_task_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._active_task = task
        self._task_start_count += 1
        self._thread_pool.start(task)

    def _on_task_finished(self, result: object) -> None:
        self._task_running = False
        self._active_task = None
        if self._closed or not isinstance(result, dict):
            return

        generation = int(result.get("generation", -1))
        source_key = str(result.get("source_key") or "")
        source_image = result.get("source_image")
        rendered_image = result.get("rendered_image")
        error = str(result.get("error") or "")

        if (
            isinstance(source_image, QImage)
            and not source_image.isNull()
            and self.config.background_mode == "custom"
        ):
            current_custom_key, _ = self._custom_file_key()
            if current_custom_key == source_key:
                self._custom_source_key = source_key
                self._custom_source_image = QImage(source_image)

        if generation == self._generation:
            if error or not isinstance(rendered_image, QImage) or rendered_image.isNull():
                self._rendered_pixmap = QPixmap()
                self._rendered_source_key = ""
                message = error or "背景图片不可用"
                if self.config.background_mode == "custom":
                    message = f"自定义图片不可用：{message}，已回退默认背景"
                else:
                    message = f"{message}，已回退默认背景"
                self._set_fallback(True, message)
                self.update()
            else:
                target_size, dpr = self._target_pixel_size()
                cache_key = self._cache_key(source_key, target_size, dpr)
                self._insert_cache(cache_key, rendered_image)
                self._apply_image(source_key, rendered_image, dpr)

        if self._pending_after_task or generation != self._generation:
            self._pending_after_task = False
            self._debounce_timer.start(self.DEBOUNCE_MS)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.rect()
        if not self.transparent_mode:
            painter.fillRect(rect, QColor("#050609"))
            return

        has_image = not self._rendered_pixmap.isNull() and not self._fallback_active
        if has_image:
            painter.fillRect(rect, QColor("#050609"))
            painter.save()
            painter.setOpacity(max(0.2, min(1.0, self.config.image_opacity / 100.0)))
            painter.drawPixmap(rect, self._rendered_pixmap)
            painter.restore()
            overlay_alpha = int(round(255 * self.config.darkness / 100.0))
            painter.fillRect(rect, QColor(0, 0, 0, overlay_alpha))
        else:
            base_alpha = int(round(255 * self.config.darkness / 100.0))
            painter.fillRect(rect, QColor(5, 6, 9, base_alpha))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._invalidate_and_schedule()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._pending_after_task = False
        self._task_running = False
        self._debounce_timer.stop()
        task = self._active_task
        if task is not None:
            try:
                task.signals.finished.disconnect(self._on_task_finished)
            except (RuntimeError, TypeError):
                pass
        self._active_task = None
        self._cache.clear()
        self._cache_bytes = 0
        self._cover_source_image = QImage()
        self._custom_source_image = QImage()
        self._rendered_pixmap = QPixmap()


class ImmersiveAppearanceDialog(QDialog):
    configChanged = Signal(object)
    lyricsOffsetChanged = Signal(str, int)

    def __init__(
        self,
        config: ImmersiveAppearanceConfig,
        parent: QWidget | None = None,
        *,
        track_identity: str = "",
        lyrics_offset_ms: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("沉浸歌词外观")
        self.setObjectName("immersiveAppearanceDialog")
        self.setMinimumWidth(520)
        self.config = config
        self._updating = False
        self._offset_updating = False
        self.track_identity = str(track_identity or "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)

        title = QLabel("沉浸歌词外观")
        title.setObjectName("appearanceTitle")
        subtitle = QLabel(
            "背景处理会在停止操作约 150ms 后更新；歌词字号和当前歌曲时间偏移即时预览。"
        )
        subtitle.setObjectName("appearanceSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("appearanceCard")
        form = QVBoxLayout(card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(13)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("默认 / 纯色背景", "default")
        self.mode_combo.addItem("当前歌曲封面", "cover")
        self.mode_combo.addItem("自定义本地图片", "custom")
        form.addLayout(self._combo_row("背景模式", self.mode_combo))

        image_row = QHBoxLayout()
        image_row.setSpacing(10)
        image_row.addWidget(QLabel("自定义图片"))
        self.path_label = QLabel()
        self.path_label.setObjectName("appearancePath")
        self.path_label.setWordWrap(True)
        image_row.addWidget(self.path_label, 1)
        self.choose_button = QPushButton("选择图片")
        self.choose_button.clicked.connect(self.choose_custom_image)
        image_row.addWidget(self.choose_button)
        form.addLayout(image_row)

        self.blur_slider, self.blur_value = self._slider_row(form, "模糊程度", 0, 40, 1)
        self.darkness_slider, self.darkness_value = self._slider_row(form, "背景暗度", 0, 90, 1, "%")
        self.opacity_slider, self.opacity_value = self._slider_row(form, "图片透明度", 20, 100, 1, "%")

        self.fill_combo = QComboBox()
        self.fill_combo.addItem("裁剪填满", "cover")
        self.fill_combo.addItem("完整显示", "contain")
        form.addLayout(self._combo_row("图片填充", self.fill_combo))

        self.font_slider, self.font_value = self._slider_row(
            form,
            "歌词字体大小",
            70,
            160,
            5,
            "%",
        )

        offset_row = QHBoxLayout()
        offset_row.setSpacing(8)
        offset_row.addWidget(QLabel("歌词时间偏移"))
        self.offset_minus_button = QPushButton("-0.5 秒")
        self.offset_minus_button.clicked.connect(lambda: self._adjust_offset(-5))
        offset_row.addWidget(self.offset_minus_button)
        self.offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.offset_slider.setRange(-100, 100)
        self.offset_slider.setSingleStep(1)
        self.offset_slider.setPageStep(5)
        self.offset_slider.valueChanged.connect(self._offset_slider_changed)
        offset_row.addWidget(self.offset_slider, 1)
        self.offset_plus_button = QPushButton("+0.5 秒")
        self.offset_plus_button.clicked.connect(lambda: self._adjust_offset(5))
        offset_row.addWidget(self.offset_plus_button)
        self.offset_zero_button = QPushButton("归零")
        self.offset_zero_button.clicked.connect(lambda: self.offset_slider.setValue(0))
        offset_row.addWidget(self.offset_zero_button)
        self.offset_value = QLabel("0.0 秒")
        self.offset_value.setMinimumWidth(66)
        self.offset_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        offset_row.addWidget(self.offset_value)
        form.addLayout(offset_row)

        self.status_label = QLabel("等待预览")
        self.status_label.setObjectName("appearanceStatus")
        self.status_label.setWordWrap(True)
        form.addWidget(self.status_label)
        layout.addWidget(card)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.reset_button = QPushButton("恢复默认")
        self.reset_button.clicked.connect(self.reset_defaults)
        close_button = QPushButton("完成")
        close_button.setObjectName("appearancePrimaryButton")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.reset_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.mode_combo.currentIndexChanged.connect(self._controls_changed)
        self.fill_combo.currentIndexChanged.connect(self._controls_changed)
        for slider in (
            self.blur_slider,
            self.darkness_slider,
            self.opacity_slider,
            self.font_slider,
        ):
            slider.valueChanged.connect(self._controls_changed)

        self._load_config(config)
        self.set_track_timing(track_identity, lyrics_offset_ms)
        self.setStyleSheet(
            "QDialog#immersiveAppearanceDialog { background: #10131a; color: #f3f4f6; }"
            "QLabel { color: #d7dce6; }"
            "QLabel#appearanceTitle { color: #ffffff; font-size: 20px; font-weight: 800; }"
            "QLabel#appearanceSubtitle, QLabel#appearancePath, QLabel#appearanceStatus { color: #9da6b5; }"
            "QFrame#appearanceCard { background: #171b24; border: 1px solid #2a303b; border-radius: 14px; }"
            "QComboBox, QPushButton { background: #222834; color: #eef1f6; border: 1px solid #343c49; border-radius: 9px; padding: 7px 10px; }"
            "QPushButton:hover { background: #2c3442; }"
            "QPushButton#appearancePrimaryButton { background: #3f7ee8; border-color: #3f7ee8; }"
            "QSlider::groove:horizontal { height: 4px; background: #343b48; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #6d9ff8; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 16px; margin: -6px 0; background: #ffffff; border-radius: 8px; }"
        )

    @staticmethod
    def _combo_row(label_text: str, combo: QComboBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel(label_text))
        row.addWidget(combo, 1)
        return row

    @staticmethod
    def _slider_row(
        parent_layout: QVBoxLayout,
        label_text: str,
        minimum: int,
        maximum: int,
        step: int,
        suffix: str = "",
    ) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel(label_text))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setSingleStep(step)
        slider.setPageStep(step)
        value_label = QLabel()
        value_label.setMinimumWidth(46)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        slider.valueChanged.connect(lambda value, target=value_label, unit=suffix: target.setText(f"{value}{unit}"))
        parent_layout.addLayout(row)
        return slider, value_label

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _load_config(self, config: ImmersiveAppearanceConfig) -> None:
        self._updating = True
        self.config = config
        self._set_combo_value(self.mode_combo, config.background_mode)
        self._set_combo_value(self.fill_combo, config.fill_mode)
        self.blur_slider.setValue(config.blur_radius)
        self.darkness_slider.setValue(config.darkness)
        self.opacity_slider.setValue(config.image_opacity)
        self.font_slider.setValue(config.lyrics_font_scale)
        self.path_label.setText(config.custom_image_path or "尚未选择")
        self.choose_button.setEnabled(config.background_mode == "custom")
        self._updating = False

    def _controls_changed(self, _value=0) -> None:
        if self._updating:
            return
        mode = str(self.mode_combo.currentData() or "default")
        self.config = replace(
            self.config,
            background_mode=mode,
            blur_radius=int(self.blur_slider.value()),
            darkness=int(self.darkness_slider.value()),
            image_opacity=int(self.opacity_slider.value()),
            fill_mode=str(self.fill_combo.currentData() or "cover"),
            lyrics_font_scale=int(self.font_slider.value()),
        )
        self.choose_button.setEnabled(mode == "custom")
        self.configChanged.emit(self.config)

    @staticmethod
    def _format_offset(offset_ms: int) -> str:
        seconds = int(offset_ms) / 1000.0
        return f"{seconds:+.1f} 秒" if offset_ms else "0.0 秒"

    def set_track_timing(self, track_identity: str, offset_ms: int) -> None:
        self.track_identity = str(track_identity or "").strip()
        normalized = normalize_lyrics_offset_ms(offset_ms)
        self._offset_updating = True
        self.offset_slider.setValue(int(normalized / 100))
        self.offset_value.setText(self._format_offset(normalized))
        enabled = bool(self.track_identity)
        for control in (
            self.offset_minus_button,
            self.offset_slider,
            self.offset_plus_button,
            self.offset_zero_button,
        ):
            control.setEnabled(enabled)
        if not enabled:
            self.offset_value.setToolTip("当前没有正在播放的歌曲")
        else:
            self.offset_value.setToolTip(
                "正值让歌词向前推进；负值让歌词向后推迟"
            )
        self._offset_updating = False

    def _adjust_offset(self, steps: int) -> None:
        if self.offset_slider.isEnabled():
            self.offset_slider.setValue(self.offset_slider.value() + int(steps))

    def _offset_slider_changed(self, value: int) -> None:
        offset_ms = normalize_lyrics_offset_ms(int(value) * 100)
        self.offset_value.setText(self._format_offset(offset_ms))
        if self._offset_updating or not self.track_identity:
            return
        self.lyricsOffsetChanged.emit(self.track_identity, offset_ms)

    def choose_custom_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择沉浸歌词背景图片",
            self.config.custom_image_path or "",
            "图片文件 (*.jpg *.jpeg *.png *.webp);;所有文件 (*)",
        )
        if not path:
            return
        self.config = replace(
            self.config,
            background_mode="custom",
            custom_image_path=str(Path(path)),
        )
        self._load_config(self.config)
        self.configChanged.emit(self.config)

    def reset_defaults(self) -> None:
        self._load_config(ImmersiveAppearanceConfig.defaults())
        self.configChanged.emit(self.config)

    def set_availability(self, available: bool, message: str) -> None:
        self.status_label.setText(str(message))
        self.status_label.setStyleSheet(
            "color: #8fd5a6;" if available else "color: #e7ad79;"
        )
