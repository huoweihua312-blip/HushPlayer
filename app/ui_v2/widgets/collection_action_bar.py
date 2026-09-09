"""Canonical collection action entry point with legacy signal compatibility.

The original row stays available; only AllSongsPage opts into this entry point.
"""
from app.ui_v2.widgets.collection_action_row import CollectionActionRow
from app.ui_v2.theme.button_styles import action_button_qss


class CollectionActionBar(CollectionActionRow):
    def set_theme(self, theme):
        super().set_theme(theme)
        self.play_button.setStyleSheet(action_button_qss(theme, primary=True))
        self.shuffle_button.setStyleSheet(action_button_qss(theme, primary=False))
