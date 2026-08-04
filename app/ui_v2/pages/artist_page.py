"""Public Artist page name for the UI V2 content router."""

from app.ui_v2.pages.artist_detail_page import ArtistDetailPage


# Keep the existing detail-page import stable while exposing the stage-level
# ArtistPage name used by the content-page contract.
ArtistPage = ArtistDetailPage

__all__ = ["ArtistPage", "ArtistDetailPage"]
