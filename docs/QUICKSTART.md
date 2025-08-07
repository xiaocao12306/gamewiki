# Quick Start Guide

Get GameWikiTooltip running in under 5 minutes! This guide covers the essentials to get you gaming with AI assistance.

## 📦 Installation

### Method 1: Portable Version (Easiest)

1. **Download the latest release**
   - Go to [Releases Page](https://github.com/rimulu030/gamewiki/releases/latest)
   - Download `GameWikiAssistant_Portable.zip`

2. **Extract and Run**
   ```
   📁 GameWikiAssistant/
   ├── GameWikiAssistant.exe    ← Double-click this
   ├── runtime/
   └── data/
   ```

3. **First Launch**
   - The hotkey setup window will appear
   - Choose your preferred hotkey (default: `Ctrl+Q`)
   - Click "Save" and you're ready!

### Method 2: From Source Code

```bash
# 1. Clone the repository
git clone https://github.com/rimulu030/gamewiki.git
cd gamewiki

# 2. Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python -m src.game_wiki_tooltip
```

## 🎮 Basic Usage

### Step 1: Launch Your Game
Start any supported game normally. GameWikiTooltip runs in the background.

### Step 2: Press the Hotkey
While in-game, press your configured hotkey (default: `Ctrl+Q`)

### Step 3: Choose Your Mode

#### Wiki Mode
- Automatically opens relevant wiki pages
- Perfect for quick item/boss lookups
- Works with 100+ games

#### AI Chat Mode (Advanced)
- Ask questions in natural language
- Get personalized build recommendations
- Requires API key for full features

### Step 4: Ask Questions
- **Text Input**: Type your question and press Enter
- **Voice Input**: Click "microphone" button and speak (if enabled)

## ⚡ Essential Settings

### Setting Up AI Features (Optional but Recommended)

1. **Get a Gemini API Key**
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Create a free API key
   - Copy the key

2. **Configure in GameWikiTooltip**
   - Right-click the system tray icon
   - Select "Settings"
   - Paste your API key in the Gemini API field
   - Click "Save"

### Customizing Hotkeys

1. Right-click system tray icon → Settings
2. Click on the hotkey field
3. Press your desired key combination
4. Supported modifiers: `Ctrl`, `Alt`, `Shift`, `Win`

## 🎯 Supported Games (AI-Enhanced)

These games have full AI knowledge bases:

| Game | What You Can Ask                                         |
|------|----------------------------------------------------------|
| **HELLDIVERS 2** | "Best loadout for bugs?" "How to beat Bile Titan?"       |
| **Elden Ring** | "Where to find Moonveil?" "Recommended dexterity build?" |
| **Don't Starve Together** | "How to survive winter?" "Wickerbottom tips?"            |
| **Civilization VI** | "City management fundamentals?" "Early game strategy?"   |


## 🚨 Troubleshooting Quick Fixes

| Issue | Solution |
|-------|----------|
| Hotkey not working | Run as Administrator |
| Overlay not showing | Install included WebView2 Runtime |
| AI not responding | Check API key in Settings |
| Game not detected | Add game to `games.json` config |

## 📹 Video Tutorial

Coming soon! For now, check our [FAQ](FAQ.md) for detailed help.

## 🆘 Need More Help?

- **Detailed FAQ**: [FAQ.md](FAQ.md)
- **Report Issues**: [GitHub Issues](https://github.com/rimulu030/gamewiki/issues)
- **Community**: [Discord Server](https://discord.gg/gamewiki)

---

**Ready to game smarter?** Launch your game and press `Ctrl+Q` to begin!