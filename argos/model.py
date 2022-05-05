from dataclasses import dataclass
from enum import IntEnum
from functools import partial
import logging
from typing import Any, List, TYPE_CHECKING

from gi.repository import Gio, GLib, GObject

if TYPE_CHECKING:
    from .app import Application

LOGGER = logging.getLogger(__name__)


class PlaybackState(IntEnum):
    UNKNOWN = 0
    PLAYING = 1
    PAUSED = 2
    STOPPED = 3

    @staticmethod
    def from_string(value: str) -> "PlaybackState":
        if value == "playing":
            state = PlaybackState.PLAYING
        elif value == "paused":
            state = PlaybackState.PAUSED
        elif value == "stopped":
            state = PlaybackState.STOPPED
        else:
            state = PlaybackState.UNKNOWN
            LOGGER.error(f"Unexpected state {value!r}")
        return state


@dataclass
class Album:
    name: str
    uri: str
    image_path: str
    image_uri: str


class Model(GObject.GObject):
    network_available = GObject.Property(type=bool, default=False)
    connected = GObject.Property(type=bool, default=False)

    state = GObject.Property(type=int, default=PlaybackState.UNKNOWN)

    mute = GObject.Property(type=bool, default=False)
    volume = GObject.Property(type=int, default=0)

    track_uri = GObject.Property(type=str, default="")
    track_name = GObject.Property(type=str, default="")
    track_length = GObject.Property(type=int, default=-1)

    time_position = GObject.Property(type=int, default=-1)  # ms

    artist_uri = GObject.Property(type=str, default="")
    artist_name = GObject.Property(type=str, default="")

    image_path = GObject.Property(type=str, default="")

    albums_loaded = GObject.Property(type=bool, default=False)
    albums_images_loaded = GObject.Property(type=bool, default=False)

    def __init__(
        self,
        application: "Application",
    ):
        super().__init__()

        self.network_available = application._nm.get_network_available()
        application._nm.connect("network-changed", self._on_nm_network_changed)

        self.albums: List[Album] = []

    def clear_track_list(self) -> None:
        self.set_property_in_gtk_thread("track_uri", "")
        self.set_property_in_gtk_thread("track_name", "")
        self.set_property_in_gtk_thread("track_length", -1)
        self.set_property_in_gtk_thread("time_position", -1)
        self.set_property_in_gtk_thread("artist_uri", "")
        self.set_property_in_gtk_thread("artist_name", "")
        self.set_property_in_gtk_thread("image_path", "")

    def set_property_in_gtk_thread(self, name: str, value: Any) -> None:
        if name == "albums":
            # albums isn't a GObject.Property()!
            LOGGER.debug(f"Updating {name!r}")
            self._set_albums(value)
        else:
            if self.get_property(name) != value:
                LOGGER.debug(
                    f"Updating {name!r} from {self.get_property(name)!r} to {value!r}"
                )
                GLib.idle_add(
                    partial(
                        self.set_property,
                        name,
                        value,
                    )
                )
            else:
                LOGGER.debug(f"No need to set {name!r} to {value!r}")

    def _set_albums(self, value: Any) -> None:
        if self.albums_loaded:
            self.set_property_in_gtk_thread("albums_loaded", False)
            self.set_property_in_gtk_thread("albums_images_loaded", False)
            self.albums.clear()

        for v in value:
            name = v.get("name")
            uri = v.get("uri")
            if not all([name, uri]):
                continue

            album = Album(
                name,
                uri,
                v.get("image_path", ""),
                v.get("image_uri", ""),
            )
            self.albums.append(album)

        self.set_property_in_gtk_thread("albums_loaded", True)

    def _on_nm_network_changed(
        self, network_monitor: Gio.NetworkMonitor, network_available: bool
    ) -> None:
        LOGGER.debug("Network monitor signal a network status change")
        self.set_property_in_gtk_thread("network_available", network_available)
