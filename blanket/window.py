# Copyright 2020-2021 Rafael Mardojai CM
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from gettext import gettext as _
from gi.repository import GLib, GObject, Gtk, Adw

from blanket.settings import Settings
from blanket.sound import MainPlayer, SoundObject
from blanket.widgets import PlayPauseButton, PresetChooser, VolumeRow


@Gtk.Template(resource_path='/com/rafaelmardojai/Blanket/window.ui')
class BlanketWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'BlanketWindow'

    headerbar = Gtk.Template.Child()
    grid = Gtk.Template.Child()
    playpause_btn: PlayPauseButton = Gtk.Template.Child()
    volumes = Gtk.Template.Child()
    volume = Gtk.Template.Child()
    volume_box = Gtk.Template.Child()
    volume_list = Gtk.Template.Child()
    presets_chooser: PresetChooser = Gtk.Template.Child()

    def __init__(self, mpris, **kwargs):
        super().__init__(**kwargs)

        # Set default window icon for window managers
        self.set_default_icon_name('com.rafaelmardojai.Blanket')

        # Main player & MPRIS server object
        self.mpris = mpris

        # Setup widgets
        self.setup()

    def setup(self):
        # Setup grid
        model = MainPlayer.get()
        model.populate_sounds()
        selection = Gtk.NoSelection(model=model)
        factory = Gtk.BuilderListItemFactory.new_from_resource(
            None, '/com/rafaelmardojai/Blanket/grid-item.ui'
        )

        self.grid.props.factory = factory
        self.grid.props.model = selection
        self.grid.connect('activate', self._on_grid_activate)

        # Wire playpause button
        MainPlayer.get().bind_property(
            'playing', self.playpause_btn, 'playing',
            GObject.BindingFlags.SYNC_CREATE
        )

        # Setup presets widgets
        self.setup_presets()
        # Setup volume
        self.setup_volume_menu()

    def setup_presets(self):
        self.mpris.update_title(self.presets_chooser.selected.name)

    def setup_volume_menu(self):
        # Get volume scale adjustment
        vol_adjustment = self.volume.get_adjustment()
        # Bind volume scale value with main player volume
        vol_adjustment.bind_property('value', MainPlayer.get(),
                                     'volume',
                                     GObject.BindingFlags.BIDIRECTIONAL)
        # Set volume scale value on first run
        self.volume.set_value(MainPlayer.get().volume)

        # Setup volume list
        self.volume_filter = Gtk.CustomFilter.new(
            match_func=lambda item: item.playing
        )
        model = Gtk.FilterListModel(
            model=MainPlayer.get(),
            filter=self.volume_filter
        )
        model.connect('items-changed', self._volume_model_changed)
        self.volume_box.props.visible = model.get_n_items() > 0
        self.volume_list.bind_model(model, self._create_vol_row)

        # Connect mainplayer preset-changed signal
        MainPlayer.get().connect(
            'preset-changed',
            self._on_preset_changed
        )
        # Connect mainplayer reset-volumes signal
        MainPlayer.get().connect(
            'reset-volumes',
            self._on_reset_volumes
        )

        self.volumes.connect('closed', self._volumes_popup_closed)

    def open_audio(self):
        def on_response(_filechooser, _id):
            gfile = self.filechooser.get_file()
            if gfile:
                filename = gfile.get_path()
                name = os.path.basename(filename).split('.')[0]
                uri = gfile.get_uri()

                # Create a new SoundObject
                sound = SoundObject(name, uri=uri, custom=True)
                # Save to settings
                GLib.idle_add(Settings.get().add_custom_audio,
                              sound.name, sound.uri)
                # Add SoundObject to SoundsGroup
                MainPlayer.get().append(sound)

        filters = {
            'Ogg': ['audio/ogg'],
            'FLAC': ['audio/flac'],
            'WAV': ['audio/x-wav', 'audio/wav'],
            'MP3': ['audio/mpeg'],
        }

        self.filechooser = Gtk.FileChooserNative.new(
            _('Open audio'),
            self,
            Gtk.FileChooserAction.OPEN,
            None,
            None)
        self.filechooser.connect('response', on_response)

        for f, mts in filters.items():
            audio_filter = Gtk.FileFilter()
            audio_filter.set_name(f)
            for mt in mts:
                audio_filter.add_mime_type(mt)
            self.filechooser.add_filter(audio_filter)

        response = self.filechooser.show()

    def _create_vol_row(self, sound):
        row = VolumeRow()

        row.volume = sound.saved_volume
        sound.bind_property(
            'saved_volume',
            row,
            'volume',
            GObject.BindingFlags.BIDIRECTIONAL
        )

        sound.bind_property(
            'title',
            row,
            'title',
            GObject.BindingFlags.SYNC_CREATE
        )

        return row

    def _on_grid_activate(self, _grid, position):
        sound = MainPlayer.get().get_item(position)
        sound.playing = not sound.playing

        # Update volumes list
        self.__update_volume_model()

    def _on_preset_changed(self, _player, preset):
        self.mpris.update_title(preset.name)
        self.__update_volume_model()

    def _on_reset_volumes(self, _player):
        self.__update_volume_model()

    def _volume_model_changed(self, model, _pos, _del, _add):
        # Hide volumes list if empty
        self.volume_box.props.visible = model.get_n_items() > 0

    def _volumes_popup_closed(self, _popover):
        # Disable sounds with volume = 0
        MainPlayer.get().mute_vol_zero()
        self.__update_volume_model()

    def _on_add_sound_clicked(self, _group):
        self.open_audio()

    def __update_volume_model(self):
        self.volume_filter.changed(Gtk.FilterChange.DIFFERENT)
