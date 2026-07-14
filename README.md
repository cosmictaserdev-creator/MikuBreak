# 🌸 mikuBreak

**mikuBreak** is a cyber-cute desktop companion built around Hatsune Miku. She started as a break-reminder mascot — now she's a full AI desktop assistant: chat with her, talk to her, ask her about what's on your screen, and let her handle reminders, habits, timers, and focus sessions while she keeps you honest about taking breaks.

![Miku Icon](assests/img/icon.png)

## ✨ Features

### Break reminders
- **Smart activity tracking:** monitors mouse & keyboard to know when you're actually working.
- **Dynamic break prompts:** Miku walks to the center of your screen and asks you to take a break.
- **"Angry Miku" anti-cheat:** keep using your PC through a break and she'll call you out.
- **Auto-break logic:** step away and she finishes the break for you, greeting you on return.
- **Do Not Disturb** toggle to pause reminders when you need to focus.

### AI chat assistant
- Type or talk to Miku (Groq or OpenCode Zen as the LLM backend) — she remembers past conversations and can save facts about you long-term.
- Tool-calling: she can set reminders, timers, and habits; open apps, files, folders, and URLs; read the clipboard; check your active window; control media playback; run shell commands (with your confirmation); and take a screenshot for herself.
- **Focus Mode:** blocks distracting sites/apps you name, for a duration you set.
- **Daily recap** and **idle chatter**: an occasional unprompted good-morning summary or comment while you work.
- Drop a file or image on her — she'll describe images or summarize text files.

### Voice
- **Voice chat:** hold a hotkey, talk, release — she transcribes (Groq Whisper) and replies out loud (Edge TTS or ElevenLabs).
- **Dictation:** hold a hotkey anywhere, speak, release — your speech gets pasted at the cursor. No LLM involved, just fast speech-to-text.
- **Screen Guide:** hold a hotkey and ask about what's on screen — she looks at a screenshot + the UI elements, answers, and walks over to point at what you meant.
- Mic/speaker device pickers with a live input meter, and a mic that auto-recovers if the wrong device (or a slow-to-wake Bluetooth headset) gets picked.

### Desktop presence
- Miku roams, idles, and sits on your desktop.
- Hold **`Ctrl` + Left Click** to drag her around; drop her in the air and she'll fall and land.
- **Shake-to-pause:** a quick drag direction-reversal interrupts whatever she's doing.
- Fully customizable global hotkeys for chat, voice chat, screen guide, and dictation, set from Settings by just pressing the combo you want.
- Single-instance enforcement — launching her again just refocuses the existing window.

## 🖱️ How to Interact

- **Standard:** Miku roams and idles automatically.
- **Chat / Voice / Dictation / Screen Guide:** press their hotkeys (defaults: `Ctrl+Alt+M`, `Ctrl+Alt+V`, `Ctrl+Alt+S`, `Ctrl+Alt+F`) — all customizable in Settings → Shortcuts.
- **Drag & Interact:** hold **`Ctrl`** and **Left Click** to drag Miku or trigger reactions.
- **Break Prompt:** choose "Cozy Break", "Snooze", or "Dismiss" when she appears.

## 🛠️ Installation

### For Users (Installer)
1. Download the latest `mysetup.exe` from the [Releases page](https://github.com/cosmictaserdev-creator/MikuBreak/releases).
2. Run it and follow the setup wizard.
3. (Optional) Open **Settings** from the system tray and enable **Run at Startup**.
4. Set your Groq (and/or OpenCode Zen) API key in Settings → Brain to enable chat, voice, and screen guide.

### For Developers (Python)
1. Clone the repository:
   ```bash
   git clone https://github.com/cosmictaserdev-creator/MikuBreak.git
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Or .\.venv\Scripts\activate on Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python main.py
   ```

## 📦 Packaging

Build the executable with `PyInstaller` (spec already checked in):

```bash
pyinstaller mikuBreak.spec
```

Then build the Windows installer with [Inno Setup](https://jrsoftware.org/isinfo.php) from `miku.iss`:

```bash
ISCC miku.iss
```

The installer is written to `Output/mysetup.exe`.

## 🎨 Credits & Assets
This project is licensed under the **MIT License** (see [LICENSE](LICENSE) for details).

Mascot sprites are created by **digitalromance**. For full asset attributions and third-party credits, please see [CREDITS.md](CREDITS.md).

---
*Miku is watching over your PC! Go relax and stretch! 🌸*
