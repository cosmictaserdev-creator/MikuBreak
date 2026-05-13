# 🌸 mikuBreak

**mikuBreak** is an interactive, cyber-cute desktop companion designed to help you maintain a healthy balance between work and rest. Featuring Hatsune Miku, this app monitors your computer activity and gently (or firmly!) nudges you to take much-needed breaks.

![Miku Icon](assests/img/icon.png)

## ✨ Features

- **Interactive Mascot:** Miku lives on your desktop, sitting, sleeping, and roaming around while you work.
- **Smart Activity Tracking:** Uses high-precision monitoring (mouse & keyboard) to detect when you are actually working.
- **Dynamic Break Reminders:** 
  - Automatically triggers a centered prompt when it's time for a break.
  - Miku walks to the center of your screen to deliver the message.
- **"Angry Miku" Anti-Cheat:** 
  - If you use your PC during a break, Miku will wait 5 seconds before getting angry and demanding you stop!
  - Features a custom "Angry" UI theme and unique mascot reactions.
- **Auto-Break Logic:** If you're away from the prompt, Miku will automatically complete a break and show you the "Good boy" screen upon your return.
- **Customizable Control Room:**
  - Adjust reminder intervals, snooze durations, and break lengths.
  - Toggle "Run at Startup" directly from the settings.
- **Desktop Physics:**
  - Drag Miku anywhere on your screen (Hold `Ctrl + Click`).
  - Watch her fall and land with a cute animation if you drop her in the air.
- **Single Instance Enforcement:** Prevents multiple copies from running simultaneously.

## 🖱️ How to Interact

- **Standard:** Miku roams and idles automatically.
- **Drag & Interact:** Hold the **`Ctrl`** key and **Left Click** to drag Miku or trigger unique reactions.
- **Break Prompt:** Choose between "Cozy Break", "Snooze", or "Dismiss" when she appears.

## 🛠️ Installation

### For Users (Executable)
1. Download the latest `mikuBreak.exe` from the Releases page.
2. Run the executable.
3. (Optional) Open **Settings** from the system tray and enable **Run at Startup**.

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

## 📦 Packaging (Creating the .exe)

To build the executable yourself, use `PyInstaller`:

```bash
pyinstaller --noconsole --onefile --name "mikuBreak" --icon "assests/appIcon.png" --add-data "assests;assests" --add-data "font;font" main.py
```

## 🎨 Credits & Assets
This project is licensed under the **MIT License** (see [LICENSE](LICENSE) for details).

Mascot sprites are created by **digitalromance**. For full asset attributions and third-party credits, please see [CREDITS.md](CREDITS.md).

---
*Miku is watching over your PC! Go relax and stretch! 🌸*
