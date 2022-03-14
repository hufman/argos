import logging
from pathlib import Path
import threading
from typing import Mapping, Optional

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from gi.repository.GdkPixbuf import Pixbuf

from .message import MessageType
from .model import Album, PlaybackState
from .utils import compute_target_size, elide_maybe, ms_to_text

LOGGER = logging.getLogger(__name__)

ALBUM_STORE_TEXT_COLUMN = 0
ALBUM_STORE_TOOLTIP_COLUMN = 1
ALBUM_STORE_URI_COLUMN = 2
ALBUM_STORE_ICON_FILE_PATH = 3
ALBUM_STORE_PIXBUF_COLUMN = 4

ALBUM_ICON_SIZE = 100


def _default_album_icon_pixbuf() -> Pixbuf:
    pixbuf = Gtk.IconTheme.get_default().load_icon(
        "media-optical-cd-audio-symbolic", ALBUM_ICON_SIZE, 0
    )
    width, height = compute_target_size(
        pixbuf.get_width(),
        pixbuf.get_height(),
        target_width=ALBUM_ICON_SIZE,
    )
    scaled_pixbuf = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
    return scaled_pixbuf


def _scale_album_icon(image_path: Path) -> Optional[Pixbuf]:
    pixbuf = None
    try:
        pixbuf = Pixbuf.new_from_file(str(image_path))
    except GLib.Error as error:
        LOGGER.warning(f"Failed to read image at {str(image_path)!r}: {error}")

    if pixbuf is None:
        return None

    width, height = compute_target_size(
        pixbuf.get_width(),
        pixbuf.get_height(),
        target_width=ALBUM_ICON_SIZE,
    )
    scaled_pixbuf = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
    return scaled_pixbuf


@Gtk.Template(resource_path="/app/argos/Argos/ui/window.ui")
class ArgosWindow(Gtk.ApplicationWindow):
    __gtype_name__ = "ArgosWindow"

    central_view = Gtk.Template.Child()
    albums_view = Gtk.Template.Child()

    playing_track_image = Gtk.Template.Child()
    play_image = Gtk.Template.Child()
    pause_image = Gtk.Template.Child()

    track_name_label = Gtk.Template.Child()
    artist_name_label = Gtk.Template.Child()
    track_length_label = Gtk.Template.Child()

    play_favorite_playlist_button = Gtk.Template.Child()
    play_random_album_button = Gtk.Template.Child()
    app_menu_button = Gtk.Template.Child()
    volume_button = Gtk.Template.Child()
    prev_button = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()

    time_position_scale = Gtk.Template.Child()
    time_position_adjustement = Gtk.Template.Child()
    time_position_label = Gtk.Template.Child()

    def __init__(
        self,
        *,
        application: Gtk.Application,
        disable_tooltips: bool = False,
    ):
        Gtk.Window.__init__(self, application=application)
        self.set_wmclass("Argos", "Argos")
        self._app = application
        self._disable_tooltips = disable_tooltips

        builder = Gtk.Builder.new_from_resource("/app/argos/Argos/ui/app_menu.ui")
        menu_model = builder.get_object("app-menu")
        self.app_menu_button.set_use_popover(True)
        self.app_menu_button.set_menu_model(menu_model)

        self._volume_button_value_changed_id = self.volume_button.connect(
            "value_changed", self.volume_button_value_changed_cb
        )

        albums_store = Gtk.ListStore(str, str, str, str, Pixbuf)
        self.albums_view.set_model(albums_store)
        self.albums_view.set_text_column(ALBUM_STORE_TEXT_COLUMN)
        self.albums_view.set_tooltip_column(ALBUM_STORE_TOOLTIP_COLUMN)
        self.albums_view.set_pixbuf_column(ALBUM_STORE_PIXBUF_COLUMN)
        self.albums_view.set_item_width(ALBUM_ICON_SIZE)

        if self._disable_tooltips:
            for widget in (
                self.albums_view,
                self.play_favorite_playlist_button,
                self.play_random_album_button,
                self.volume_button,
                self.prev_button,
                self.play_button,
                self.next_button,
            ):
                widget.props.has_tooltip = False

        self._default_album_icon = _default_album_icon_pixbuf()

    def update_albums_list(self, albums: Mapping[str, Album]) -> None:
        LOGGER.debug("Updating album list...")

        store = self.albums_view.get_model()
        store.clear()
        for uri, album in albums.items():
            store.append(
                [
                    elide_maybe(album.name),
                    GLib.markup_escape_text(album.name),
                    album.uri,
                    str(album.image_path) if album.image_path else None,
                    self._default_album_icon,
                ]
            )

    def update_album_icons(self) -> None:
        thread = threading.Thread(target=self._update_album_icons)
        thread.daemon = True
        thread.start()

    def _update_album_icons(self) -> None:
        LOGGER.debug("Updating album icons...")

        store = self.albums_view.get_model()

        def update_album_icon(path: Gtk.TreePath, pixbuf: Pixbuf) -> None:
            store_iter = store.get_iter(path)
            store.set_value(store_iter, ALBUM_STORE_PIXBUF_COLUMN, pixbuf)

        store_iter = store.get_iter_first()
        while store_iter is not None:
            image_path = store.get_value(store_iter, ALBUM_STORE_ICON_FILE_PATH)
            if image_path:
                scaled_pixbuf = _scale_album_icon(image_path)
                path = store.get_path(store_iter)
                GLib.idle_add(update_album_icon, path, scaled_pixbuf)
            else:
                LOGGER.debug("No image path")
            store_iter = store.iter_next(store_iter)

    def update_playing_track_image(self, image_path: Optional[Path]) -> None:
        if not image_path:
            self.playing_track_image.set_from_resource(
                "/app/argos/Argos/icons/welcome-music.svg"
            )
        else:
            try:
                pixbuf = Pixbuf.new_from_file(str(image_path))
            except GLib.Error as error:
                LOGGER.warning(f"Failed to read image at {str(image_path)!r}: {error}")
                self.playing_track_image.set_from_resource(
                    "/app/argos/Argos/icons/welcome-music.svg"
                )
            else:
                rectangle = self.playing_track_image.get_allocation()
                target_width = min(rectangle.width, rectangle.height)
                width, height = compute_target_size(
                    pixbuf.get_width(), pixbuf.get_height(), target_width=target_width
                )
                scaled_pixbuf = pixbuf.scale_simple(
                    width, height, GdkPixbuf.InterpType.BILINEAR
                )
                self.playing_track_image.set_from_pixbuf(scaled_pixbuf)

        self.playing_track_image.show_now()

    def update_labels(
        self,
        *,
        track_name: Optional[str],
        artist_name: Optional[str],
        track_length: Optional[int],
    ) -> None:
        if track_name:
            short_track_name = GLib.markup_escape_text(elide_maybe(track_name))
            track_name_text = (
                f"""<span size="xx-large"><b>{short_track_name}</b></span>"""
            )
            self.track_name_label.set_markup(track_name_text)
            if not self._disable_tooltips:
                self.track_name_label.set_has_tooltip(True)
                self.track_name_label.set_tooltip_text(track_name)
        else:
            self.track_name_label.set_markup("")
            self.track_name_label.set_has_tooltip(False)

        if artist_name:
            short_artist_name = GLib.markup_escape_text(elide_maybe(artist_name))
            artist_name_text = f"""<span size="x-large">{short_artist_name}</span>"""
            self.artist_name_label.set_markup(artist_name_text)
            if not self._disable_tooltips:
                self.artist_name_label.set_has_tooltip(True)
                self.artist_name_label.set_tooltip_text(artist_name)
        else:
            self.artist_name_label.set_markup("")
            self.artist_name_label.set_has_tooltip(False)

        pretty_length = ms_to_text(track_length)
        self.track_length_label.set_text(pretty_length)

        if track_length:
            self.time_position_adjustement.set_upper(track_length)
            self.time_position_scale.set_sensitive(True)
        else:
            self.time_position_adjustement.set_upper(0)
            self.time_position_scale.set_sensitive(False)

        self.update_time_position_scale(time_position=None)
        self.track_name_label.show_now()
        self.artist_name_label.show_now()
        self.track_length_label.show_now()

    def update_time_position_scale(self, *, time_position: Optional[int]) -> None:
        pretty_time_position = ms_to_text(time_position)
        self.time_position_label.set_text(pretty_time_position)

        if time_position is not None:
            self.time_position_adjustement.set_value(time_position)

        self.time_position_label.show_now()
        self.time_position_scale.show_now()

    def update_volume(self, *, mute: Optional[bool], volume: Optional[int]) -> None:
        if mute:
            volume = 0

        if volume is not None:
            with self.volume_button.handler_block(self._volume_button_value_changed_id):
                self.volume_button.set_value(volume / 100)

            self.volume_button.show_now()

    def update_play_button(self, *, state: PlaybackState) -> None:
        if state in (PlaybackState.PAUSED, PlaybackState.STOPPED):
            self.play_button.set_image(self.play_image)
        elif state == PlaybackState.PLAYING:
            self.play_button.set_image(self.pause_image)

    def volume_button_value_changed_cb(self, *args) -> None:
        volume = self.volume_button.get_value() * 100
        self._app.send_message(MessageType.SET_VOLUME, {"volume": volume})

    @Gtk.Template.Callback()
    def prev_button_clicked_cb(self, *args) -> None:
        self._app.send_message(MessageType.PLAY_PREV_TRACK)

    @Gtk.Template.Callback()
    def play_button_clicked_cb(self, *args) -> None:
        self._app.send_message(MessageType.TOGGLE_PLAYBACK_STATE)

    @Gtk.Template.Callback()
    def next_button_clicked_cb(self, *args) -> None:
        self._app.send_message(MessageType.PLAY_NEXT_TRACK)

    @Gtk.Template.Callback()
    def time_position_scale_change_value_cb(
        self, widget: Gtk.Widget, scroll_type: Gtk.ScrollType, value: float
    ) -> None:
        time_position = round(value)
        self._app.send_message(MessageType.SEEK, {"time_position": time_position})

    @Gtk.Template.Callback()
    def albums_view_item_activated_cb(
        self, icon_view: Gtk.IconView, path: Gtk.TreePath
    ) -> None:
        store = icon_view.get_model()
        store_iter = store.get_iter(path)
        uri = store.get_value(store_iter, ALBUM_STORE_URI_COLUMN)
        self._app.send_message(MessageType.PLAY_ALBUM, {"uri": uri})

    @Gtk.Template.Callback()
    def key_press_event_cb(self, widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        mod1_mask = Gdk.ModifierType.MOD1_MASK
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        keyval = event.keyval
        LOGGER.debug(f"Received {event} with modifiers {modifiers} and keyval {keyval}")
        if modifiers == mod1_mask:
            if keyval in [Gdk.KEY_1, Gdk.KEY_KP_1]:
                self.central_view.set_visible_child_name("playing_page")
                return True
            elif keyval in [Gdk.KEY_2, Gdk.KEY_KP_2]:
                self.central_view.set_visible_child_name("albums_page")
                return True
        return False
