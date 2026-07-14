import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QFrame,
    QCheckBox, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget,
    QTextEdit, QMessageBox, QRadioButton, QButtonGroup, QScrollArea, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from config import ConfigManager
from memory.store import MemoryStore
from voice.tts import get_speaker
from audio_devices import list_input_devices, list_output_devices, apply_output_device

STYLE = """
QWidget { color: #959bb5; font-family: 'DM Serif Display', serif; background: transparent; }
QWidget#root { background-color: #0a1123; }
QFrame#sidebar { background-color: #12172b; border-right: 1px solid #2a2f4d; }
QLabel#navItem { font-size: 14px; font-weight: 700; color: #959bb5; padding: 10px 16px; }
QLabel#pageTitle { color: #8387c4; font-size: 22px; font-weight: 900; }
QLabel#sectionHint { color: #6b7092; font-size: 12px; font-style: italic; }
QLabel { font-size: 14px; font-weight: 600; color: #8387c4; }
QCheckBox, QRadioButton { color: #8387c4; font-size: 14px; font-weight: 600; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px; border-radius: 4px; border: 2px solid #8387c4; background: #1a1e2e;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #8387c4; }
QSlider::handle:horizontal {
    background: #8387c4; border: 2px solid #FFFFFF; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
}
QSlider::groove:horizontal { border: 1px solid #8387c4; height: 6px; background: #1a1e2e; margin: 2px 0; border-radius: 3px; }
QLineEdit, QTextEdit {
    background: #1a1e2e; border: 2px solid #3a3e6d; border-radius: 8px; padding: 6px 10px;
    color: #ffffff; font-size: 13px; font-family: Consolas, monospace;
}
QLineEdit:focus, QTextEdit:focus { border: 2px solid #8387c4; }
QListWidget {
    background: #1a1e2e; border: 2px solid #3a3e6d; border-radius: 8px; color: #ffffff; font-size: 13px;
}
QPushButton {
    background-color: #8387c4; color: #0a1123; border: none; padding: 8px 14px;
    border-radius: 10px; font-weight: 900; font-size: 12px;
}
QPushButton:hover { background-color: #898cab; }
QPushButton#dangerBtn { background-color: #F7768E; }
QPushButton#dangerBtn:hover { background-color: #ff8fa3; }
QFrame#divider { background-color: #2a2f4d; min-height: 1px; max-height: 1px; }
"""

NAV_SECTIONS = ["General", "Voice", "Brain", "Memory & Reminders", "Screen Guide", "Chatter", "Gestures", "Shortcuts", "About"]


class SettingsWindow(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, config: ConfigManager, store: MemoryStore):
        super().__init__()
        self.config = config
        self.store = store
        self._pending = {}  # staged edits; written to config only on Save
        # side effects that must run when a staged key is actually saved
        self._on_save_effects = {
            "run_at_startup": lambda v: self._handle_startup_registry(v),
            "speaker_device": lambda v: apply_output_device(self.audio_output, self.config),
        }

        self.setObjectName("root")
        self.setWindowTitle("Miku Settings")
        icon_path = os.path.join("assests", "appIcon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(760, 560)
        self.resize(760, 560)
        self.setStyleSheet(STYLE)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        apply_output_device(self.audio_output, config)
        self.player.setAudioOutput(self.audio_output)

        self._build_ui()

    # -- layout scaffolding --------------------------------------------------------

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(180)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 20, 0, 20)
        side_layout.setSpacing(4)

        title = QLabel("✧ Miku ✧")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #8387c4; font-size: 18px; font-weight: 900; padding-bottom: 12px;")
        side_layout.addWidget(title)

        self.stack = QStackedWidget()

        builders = {
            "General": self._build_general_page,
            "Voice": self._build_voice_page,
            "Brain": self._build_brain_page,
            "Memory & Reminders": self._build_memory_page,
            "Screen Guide": self._build_screen_guide_page,
            "Chatter": self._build_chatter_page,
            "Gestures": self._build_gestures_page,
            "Shortcuts": self._build_shortcuts_page,
            "About": self._build_about_page,
        }

        for i, name in enumerate(NAV_SECTIONS):
            nav_label = QLabel(name)
            nav_label.setObjectName("navItem")
            nav_label.setCursor(Qt.CursorShape.PointingHandCursor)
            nav_label.mousePressEvent = lambda e, idx=i: self.stack.setCurrentIndex(idx)
            side_layout.addWidget(nav_label)

            page = self._wrap_scrollable(builders[name]())
            self.stack.addWidget(page)

        side_layout.addStretch()
        outer.addWidget(sidebar)

        # content column: pages on top, persistent Save bar below
        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(0)
        content_col.addWidget(self.stack, 1)

        save_bar = QFrame()
        save_bar.setStyleSheet("QFrame { background-color: #12172b; border-top: 1px solid #2a2f4d; }")
        bar_layout = QHBoxLayout(save_bar)
        bar_layout.setContentsMargins(20, 10, 20, 10)
        self.unsaved_label = QLabel("Unsaved changes")
        self.unsaved_label.setStyleSheet("color: #F7768E; font-size: 12px; font-weight: 700;")
        self.unsaved_label.hide()
        self.save_btn = QPushButton("Save changes")
        self.save_btn.setEnabled(False)
        self.save_btn.setFixedWidth(140)
        self.save_btn.clicked.connect(self._apply_pending)
        bar_layout.addWidget(self.unsaved_label)
        bar_layout.addStretch()
        bar_layout.addWidget(self.save_btn)
        content_col.addWidget(save_bar)

        outer.addLayout(content_col, 1)

        self.stack.setCurrentIndex(0)

        # Transient "Saved" toast, floats over the content pane
        self.toast = QLabel("Saved ✨", self.stack)
        self.toast.setStyleSheet("""
            background-color: rgba(131, 135, 196, 230); color: #0a1123;
            font-weight: 900; font-size: 12px; border-radius: 10px; padding: 6px 14px;
        """)
        self.toast.adjustSize()
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

    def _wrap_scrollable(self, content: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _page(self, title_text: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(14)
        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        line = QFrame()
        line.setObjectName("divider")
        layout.addWidget(line)
        return page, layout

    def _show_saved_toast(self):
        self.toast.move(self.stack.width() - self.toast.width() - 20, 16)
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(1200)

    def _save_field(self, key, value):
        """Stage a change — nothing touches config.json until the Save button."""
        self._pending[key] = value
        self._update_dirty_state()

    def _update_dirty_state(self):
        dirty = bool(self._pending)
        self.save_btn.setEnabled(dirty)
        self.unsaved_label.setVisible(dirty)

    def _apply_pending(self):
        if not self._pending:
            return
        for key, value in self._pending.items():
            self.config.config[key] = value
        self.config.save_config()
        # side effects (startup registry, output device) run after config is written
        for key, effect in self._on_save_effects.items():
            if key in self._pending:
                effect(self._pending[key])
        self._pending.clear()
        self._update_dirty_state()
        self._show_saved_toast()
        self.settings_changed.emit()

    def _effective(self, key):
        """Config value including staged edits — for previews like the voice test."""
        return self._pending.get(key, self.config.get(key))

    def _hint(self, text):
        label = QLabel(text)
        label.setObjectName("sectionHint")
        label.setWordWrap(True)
        return label

    def _key_field(self, config_key, placeholder=""):
        """Masked API key field with a show/hide toggle, auto-saves on focus loss."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)

        edit = QLineEdit(self.config.get(config_key) or "")
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText(placeholder)
        edit.editingFinished.connect(lambda: self._save_field(config_key, edit.text()))

        toggle = QPushButton("Show")
        toggle.setFixedWidth(60)

        def _toggle():
            if edit.echoMode() == QLineEdit.EchoMode.Password:
                edit.setEchoMode(QLineEdit.EchoMode.Normal)
                toggle.setText("Hide")
            else:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                toggle.setText("Show")

        toggle.clicked.connect(_toggle)
        h.addWidget(edit, 1)
        h.addWidget(toggle)
        return row

    def _text_field(self, config_key, placeholder=""):
        edit = QLineEdit(str(self.config.get(config_key) or ""))
        edit.setPlaceholderText(placeholder)
        edit.editingFinished.connect(lambda: self._save_field(config_key, edit.text()))
        return edit

    def _device_combo(self, config_key, device_names, default_label="System default"):
        """Dropdown of audio device names; empty selection means system default."""
        combo = QComboBox()
        combo.addItem(default_label, "")
        current = self.config.get(config_key) or ""
        for name in device_names:
            combo.addItem(name, name)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.currentIndexChanged.connect(lambda i: self._save_field(config_key, combo.itemData(i)))
        return combo

    def _slider_row(self, config_key, min_v, max_v, suffix="m"):
        value_label = QLabel()
        value_label.setStyleSheet("color: #898cab; font-size: 15px; font-weight: 800;")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_v, max_v)
        slider.setValue(int(self.config.get(config_key)))
        value_label.setText(f"{slider.value()}{suffix}")
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v}{suffix}"))
        slider.sliderReleased.connect(lambda: self._save_field(config_key, slider.value()))

        row = QHBoxLayout()
        row.addWidget(slider)
        row.addWidget(value_label)
        return row

    def _checkbox(self, config_key, label_text):
        box = QCheckBox(label_text)
        box.setChecked(bool(self.config.get(config_key)))
        box.toggled.connect(lambda checked: self._save_field(config_key, checked))
        return box

    # -- General --------------------------------------------------------

    def _build_general_page(self):
        page, layout = self._page("General")

        layout.addWidget(self._checkbox("run_at_startup", "Launch on Windows startup"))
        layout.addWidget(self._checkbox("dnd_enabled", "Do Not Disturb ~ Miku won't bug you"))

        layout.addWidget(QLabel("How often should I bug you? (minutes)"))
        layout.addLayout(self._slider_row("reminder_interval_min", 5, 120))

        layout.addWidget(QLabel("Snooze duration (minutes)"))
        layout.addLayout(self._slider_row("snooze_duration_min", 1, 30))

        layout.addWidget(QLabel("Break duration (minutes)"))
        layout.addLayout(self._slider_row("break_duration_min", 1, 60))

        layout.addStretch()
        return page

    def _handle_startup_registry(self, enable):
        if sys.platform != "win32":
            return
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "mikuBreak"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                app_path = os.path.abspath(sys.argv[0])
                if not app_path.endswith(".exe"):
                    app_path = f'"{sys.executable}" "{app_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass

    # -- Voice --------------------------------------------------------

    def _build_voice_page(self):
        page, layout = self._page("Voice")

        layout.addWidget(QLabel("Microphone"))
        mic_names = [name for name, _ in list_input_devices()]
        layout.addWidget(self._device_combo("mic_device", mic_names))

        layout.addWidget(QLabel("Speaker"))
        speaker_names = [name for name, _ in list_output_devices()]
        layout.addWidget(self._device_combo("speaker_device", speaker_names))

        layout.addWidget(QLabel("TTS backend"))
        radio_row = QHBoxLayout()
        edge_radio = QRadioButton("Edge TTS (free, recommended)")
        eleven_radio = QRadioButton("ElevenLabs (premium, limited)")
        group = QButtonGroup(page)
        group.addButton(edge_radio)
        group.addButton(eleven_radio)
        if self.config.get("tts_backend") == "elevenlabs":
            eleven_radio.setChecked(True)
        else:
            edge_radio.setChecked(True)
        edge_radio.toggled.connect(lambda checked: checked and self._save_field("tts_backend", "edge"))
        eleven_radio.toggled.connect(lambda checked: checked and self._save_field("tts_backend", "elevenlabs"))
        radio_row.addWidget(edge_radio)
        radio_row.addWidget(eleven_radio)
        layout.addLayout(radio_row)

        layout.addWidget(QLabel("Voice name (edge-tts), e.g. en-US-JennyNeural"))
        layout.addWidget(self._text_field("tts_voice"))

        layout.addWidget(QLabel("Speech rate adjustment"))
        rate_slider = QSlider(Qt.Orientation.Horizontal)
        rate_slider.setRange(-50, 50)
        rate_slider.setValue(int(str(self.config.get("tts_rate")).rstrip("%")))
        rate_val = QLabel(f"{rate_slider.value():+d}%")
        rate_val.setStyleSheet("color: #898cab; font-size: 15px; font-weight: 800;")
        rate_row = QHBoxLayout(); rate_row.addWidget(rate_slider, 1); rate_row.addWidget(rate_val)
        rate_slider.valueChanged.connect(lambda v: rate_val.setText(f"{v:+d}%"))
        rate_slider.sliderReleased.connect(lambda: self._save_field("tts_rate", f"{rate_slider.value():+d}%"))
        layout.addLayout(rate_row)

        layout.addWidget(QLabel("Pitch adjustment"))
        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setRange(-50, 50)
        pitch_slider.setValue(int(str(self.config.get("tts_pitch")).rstrip("Hz")))
        pitch_val = QLabel(f"{pitch_slider.value():+d}Hz")
        pitch_val.setStyleSheet("color: #898cab; font-size: 15px; font-weight: 800;")
        pitch_row = QHBoxLayout(); pitch_row.addWidget(pitch_slider, 1); pitch_row.addWidget(pitch_val)
        pitch_slider.valueChanged.connect(lambda v: pitch_val.setText(f"{v:+d}Hz"))
        pitch_slider.sliderReleased.connect(lambda: self._save_field("tts_pitch", f"{pitch_slider.value():+d}Hz"))
        layout.addLayout(pitch_row)

        layout.addWidget(QLabel("Volume adjustment"))
        vol_slider = QSlider(Qt.Orientation.Horizontal)
        vol_slider.setRange(-50, 50)
        vol_slider.setValue(int(str(self.config.get("tts_volume")).rstrip("%")))
        vol_val = QLabel(f"{vol_slider.value():+d}%")
        vol_val.setStyleSheet("color: #898cab; font-size: 15px; font-weight: 800;")
        vol_row = QHBoxLayout(); vol_row.addWidget(vol_slider, 1); vol_row.addWidget(vol_val)
        vol_slider.valueChanged.connect(lambda v: vol_val.setText(f"{v:+d}%"))
        vol_slider.sliderReleased.connect(lambda: self._save_field("tts_volume", f"{vol_slider.value():+d}%"))
        layout.addLayout(vol_row)

        layout.addWidget(self._hint("ElevenLabs (optional premium backend, falls back to Edge silently if unset)"))
        layout.addWidget(self._key_field("elevenlabs_api_key", "sk_..."))
        layout.addWidget(QLabel("ElevenLabs voice ID"))
        layout.addWidget(self._text_field("elevenlabs_voice_id"))

        test_btn = QPushButton("🔊 Test voice")
        test_btn.clicked.connect(self._test_voice)
        layout.addWidget(test_btn)

        layout.addWidget(self._checkbox("muted", "Mute Miku's voice (captions still show)"))

        layout.addStretch()
        return page

    def _test_voice(self):
        from types import SimpleNamespace
        preview = SimpleNamespace(get=self._effective)  # hears unsaved edits too
        try:
            speaker = get_speaker(preview)
            path = speaker.speak("Hi! This is what I sound like.")
        except Exception as e:
            QMessageBox.warning(self, "Voice test failed", str(e))
            return
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    # -- Brain --------------------------------------------------------

    def _build_brain_page(self):
        page, layout = self._page("Brain (AI)")

        layout.addWidget(QLabel("AI Provider"))
        provider_combo = QComboBox()
        provider_combo.addItem("Groq", "groq")
        provider_combo.addItem("OpenCode Zen (free Big Pickle)", "opencode")
        current = self.config.get("llm_provider") or "groq"
        idx = provider_combo.findData(current)
        provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        provider_combo.currentIndexChanged.connect(
            lambda i: self._on_provider_changed(provider_combo.itemData(i)))
        layout.addWidget(provider_combo)

        # -- Groq fields --
        self._groq_group = QWidget()
        groq_layout = QVBoxLayout(self._groq_group)
        groq_layout.setContentsMargins(0, 0, 0, 0)
        groq_layout.addWidget(self._hint("Get a free API key at console.groq.com"))
        groq_layout.addWidget(self._key_field("groq_api_key", "gsk_..."))
        groq_layout.addWidget(QLabel("Chat model"))
        groq_layout.addWidget(self._text_field("groq_model"))
        groq_layout.addWidget(QLabel("Vision model (screen guide)"))
        groq_layout.addWidget(self._text_field("groq_vision_model"))
        layout.addWidget(self._groq_group)

        # -- OpenCode fields --
        self._opencode_group = QWidget()
        opencode_layout = QVBoxLayout(self._opencode_group)
        opencode_layout.setContentsMargins(0, 0, 0, 0)
        opencode_layout.addWidget(self._hint(
            "Free tier with Big Pickle model — get a key at opencode.ai/auth"))
        opencode_layout.addWidget(self._key_field("opencode_api_key", "oc-..."))
        opencode_layout.addWidget(QLabel("Model"))
        opencode_layout.addWidget(self._text_field("opencode_model", "big-pickle"))
        layout.addWidget(self._opencode_group)

        layout.addWidget(self._hint(
            "Personality is set in brain/llm_client.py's SYSTEM_PROMPT."
        ))

        self._on_provider_changed(current)
        layout.addStretch()
        return page

    def _on_provider_changed(self, provider):
        is_opencode = provider == "opencode"
        self._groq_group.setVisible(not is_opencode)
        self._opencode_group.setVisible(is_opencode)

    # -- Memory & Reminders --------------------------------------------------------

    def _build_memory_page(self):
        page, layout = self._page("Memory & Reminders")

        layout.addWidget(QLabel("Active reminders"))
        self.reminders_list = QListWidget()
        self.reminders_list.setFixedHeight(100)
        layout.addWidget(self.reminders_list)
        del_reminder_btn = QPushButton("Delete selected reminder")
        del_reminder_btn.clicked.connect(self._delete_selected_reminder)
        layout.addWidget(del_reminder_btn)

        layout.addWidget(QLabel("Habits (check to pause)"))
        self.habits_list = QListWidget()
        self.habits_list.setFixedHeight(90)
        self.habits_list.itemChanged.connect(self._habit_item_changed)
        layout.addWidget(self.habits_list)

        layout.addWidget(QLabel("Memories (auto-saved vs manual)"))
        self.memories_list = QListWidget()
        self.memories_list.setFixedHeight(120)
        layout.addWidget(self.memories_list)
        del_memory_btn = QPushButton("Delete selected memory")
        del_memory_btn.clicked.connect(self._delete_selected_memory)
        layout.addWidget(del_memory_btn)

        danger_row = QHBoxLayout()
        clear_convo_btn = QPushButton("Clear conversation memory")
        clear_convo_btn.setObjectName("dangerBtn")
        clear_convo_btn.clicked.connect(self._clear_conversation)
        clear_all_btn = QPushButton("Clear ALL memory")
        clear_all_btn.setObjectName("dangerBtn")
        clear_all_btn.clicked.connect(self._clear_all_memory)
        danger_row.addWidget(clear_convo_btn)
        danger_row.addWidget(clear_all_btn)
        layout.addLayout(danger_row)

        layout.addStretch()
        self._refresh_memory_lists()
        return page

    def _refresh_memory_lists(self):
        self.reminders_list.clear()
        for r in self.store.get_active_reminders():
            item = QListWidgetItem(f"{r['text']}  —  due {r['due_at']}")
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.reminders_list.addItem(item)

        self.habits_list.blockSignals(True)
        self.habits_list.clear()
        for h in self.store.get_habits():
            item = QListWidgetItem(f"{h['name']}  (every {h['target_interval_minutes']}min)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if h["is_paused"] else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, h["name"])
            self.habits_list.addItem(item)
        self.habits_list.blockSignals(False)

        self.memories_list.clear()
        for m in self.store.get_memories(limit=100):
            tag = "auto" if m["source"] == "auto" else "manual"
            item = QListWidgetItem(f"[{tag}] [{m['category']}] {m['content']}")
            item.setData(Qt.ItemDataRole.UserRole, m["id"])
            self.memories_list.addItem(item)

    def _delete_selected_reminder(self):
        item = self.reminders_list.currentItem()
        if not item:
            return
        self.store.delete_reminder(item.data(Qt.ItemDataRole.UserRole))
        self._refresh_memory_lists()
        self._show_saved_toast()

    def _delete_selected_memory(self):
        item = self.memories_list.currentItem()
        if not item:
            return
        self.store.delete_memory(item.data(Qt.ItemDataRole.UserRole))
        self._refresh_memory_lists()
        self._show_saved_toast()

    def _habit_item_changed(self, item: QListWidgetItem):
        name = item.data(Qt.ItemDataRole.UserRole)
        self.store.set_habit_paused(name, item.checkState() == Qt.CheckState.Checked)
        self._show_saved_toast()

    def _clear_conversation(self):
        if QMessageBox.question(self, "Clear conversation memory",
                                 "Forget the conversation history? This can't be undone.") == QMessageBox.StandardButton.Yes:
            self.store.clear_conversation()
            self._show_saved_toast()

    def _clear_all_memory(self):
        if QMessageBox.question(self, "Clear ALL memory",
                                 "Delete every memory, reminder, and habit? This can't be undone.") == QMessageBox.StandardButton.Yes:
            self.store.clear_all()
            self._refresh_memory_lists()
            self._show_saved_toast()

    # -- Screen Guide --------------------------------------------------------

    def _build_screen_guide_page(self):
        page, layout = self._page("Screen Guide")

        layout.addWidget(self._checkbox("screen_guide_enabled", "Enable screen guide skill"))

        layout.addWidget(QLabel("Privacy blocklist — window titles Miku should never capture (one per line)"))
        blocklist_edit = QTextEdit()
        blocklist_edit.setPlainText("\n".join(self.config.get("screen_guide_blocklist") or []))
        blocklist_edit.setFixedHeight(100)

        def _save_blocklist():
            terms = [t.strip() for t in blocklist_edit.toPlainText().splitlines() if t.strip()]
            self._save_field("screen_guide_blocklist", terms)

        blocklist_edit.focusOutEvent = lambda e: (_save_blocklist(), QTextEdit.focusOutEvent(blocklist_edit, e))
        layout.addWidget(blocklist_edit)

        layout.addStretch()
        return page

    # -- Chatter --------------------------------------------------------

    def _build_chatter_page(self):
        page, layout = self._page("Chatter")

        layout.addWidget(self._checkbox("chatter_enabled", "Share random facts/news, unprompted"))
        layout.addWidget(self._hint("Source: model knowledge only (no web search — MCP tools aren't wired up yet)"))

        layout.addWidget(QLabel("Frequency"))
        freq_row = QHBoxLayout()
        group = QButtonGroup(page)
        for value, label in [("rare", "Rare"), ("occasional", "Occasional"), ("chatty", "Chatty")]:
            radio = QRadioButton(label)
            if self.config.get("chatter_frequency") == value:
                radio.setChecked(True)
            radio.toggled.connect(lambda checked, v=value: checked and self._save_field("chatter_frequency", v))
            group.addButton(radio)
            freq_row.addWidget(radio)
        layout.addLayout(freq_row)

        layout.addStretch()
        return page

    # -- Gestures --------------------------------------------------------

    def _build_gestures_page(self):
        page, layout = self._page("Gestures")

        layout.addWidget(self._hint(
            "Shake-to-pause: a rapid drag direction-reversal interrupts whatever she's "
            "doing (voice, animation) and plays a startled beat."
        ))

        layout.addWidget(QLabel("Shake sensitivity (reversals needed — lower = easier to trigger)"))
        layout.addLayout(self._slider_row("shake_reversal_threshold", 2, 8, suffix=""))

        layout.addWidget(QLabel("Grace period before resuming (ms)"))
        layout.addLayout(self._slider_row("shake_grace_period_ms", 500, 3000, suffix="ms"))

        layout.addStretch()
        return page

    # -- Shortcuts --------------------------------------------------------

    def _hotkey_recorder(self, config_key, label_text):
        """A button that captures the next key combo when clicked."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 4)

        label = QLabel(label_text)
        layout.addWidget(label)

        btn = QPushButton(self.config.get(config_key) or "Click to set...")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #1a1e2e; color: #ffffff; border: 2px solid #3a3e6d;
                border-radius: 10px; padding: 8px 14px; font-size: 14px; font-weight: 700;
                text-align: center; min-width: 180px;
            }
            QPushButton:hover { border-color: #8387c4; }
            QPushButton#capturing { border-color: #F7768E; color: #F7768E; }
        """)
        layout.addWidget(btn)

        hint = QLabel("")
        hint.setStyleSheet("color: #6b7092; font-size: 11px; font-style: italic; padding-left: 4px;")
        layout.addWidget(hint)

        combo_keys = []

        def _on_key(e):
            nonlocal combo_keys
            if e.type() == e.Type.KeyPress:
                k = e.key()
                mods = e.modifiers()
                parts = []
                if mods & Qt.KeyboardModifier.ControlModifier:
                    parts.append("<ctrl>")
                if mods & Qt.KeyboardModifier.AltModifier:
                    parts.append("<alt>")
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    parts.append("<shift>")
                if mods & Qt.KeyboardModifier.MetaModifier:
                    parts.append("<win>")
                if k not in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
                    key_name = {
                        Qt.Key.Key_Space: "space",
                        Qt.Key.Key_Return: "enter",
                        Qt.Key.Key_Tab: "tab",
                        Qt.Key.Key_Escape: "esc",
                    }.get(k, e.text().lower() or chr(k).lower() if 32 <= k < 256 else "")
                    if key_name:
                        parts.append(key_name)
                combo = "+".join(parts)
                if combo:
                    btn.setText(combo)
                    self._save_field(config_key, combo)
                    QTimer.singleShot(2000, lambda: hint.setText(""))
                    btn.releaseKeyboard()
                    btn.setProperty("capturing", False)
                    btn.setStyleSheet(btn.styleSheet())
                    hint.setText("Applies after Save")
                e.accept()

        def _start_capture():
            btn.grabKeyboard()
            btn.setText("Press a key combo...")
            btn.keyPressEvent = _on_key
            hint.setText("")

        btn.clicked.connect(_start_capture)
        return container

    def _build_shortcuts_page(self):
        page, layout = self._page("Shortcuts")
        layout.addWidget(self._hint("Click a button, then press your desired key combo to set it."))
        layout.addSpacing(8)

        layout.addWidget(self._hotkey_recorder("chat_hotkey", "Chat (type a message)"))
        layout.addWidget(self._hotkey_recorder("voice_chat_hotkey", "Voice chat (hold to talk)"))
        layout.addWidget(self._hotkey_recorder("screen_guide_hotkey", "Screen guide (hold, ask about screen)"))
        layout.addWidget(self._hotkey_recorder("dictation_hotkey", "Dictation (hold, speech-to-text)"))

        layout.addStretch()
        return page

    # -- About --------------------------------------------------------

    def _build_about_page(self):
        page, layout = self._page("About")
        layout.addWidget(QLabel("mikuBreak"))
        layout.addWidget(self._hint("A desktop companion — screen-time reminders plus an AI companion brain."))
        base_path = os.path.dirname(os.path.abspath(__file__))
        layout.addWidget(self._hint(f"Config: {os.path.join(base_path, 'config.json')}"))
        layout.addWidget(self._hint(f"Memory DB: {self.store.db_path}"))
        layout.addStretch()
        return page

    def save_settings(self):
        """Kept for external callers expecting the old batch-save API."""
        self._apply_pending()

    def closeEvent(self, event):
        if self._pending:
            result = QMessageBox.question(
                self, "Unsaved changes",
                "You have unsaved settings. Save before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if result == QMessageBox.StandardButton.Save:
                self._apply_pending()
            elif result == QMessageBox.StandardButton.Discard:
                self._pending.clear()
                self._update_dirty_state()
            else:
                event.ignore()
                return
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    cfg = ConfigManager()
    test_store = MemoryStore(db_path="miku_settings_test.db")
    win = SettingsWindow(cfg, test_store)
    win.show()
    sys.exit(app.exec())
