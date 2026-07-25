"""Navigation values that keep UI V2 routing independent from widgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationItem:
    route_id: str
    title: str
    icon_name: str
    group: str
    playlist_id: str = ""


@dataclass(frozen=True, slots=True)
class MockPlaylist:
    id: str
    name: str
