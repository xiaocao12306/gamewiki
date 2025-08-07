# Frequently Asked Questions (FAQ)

## 🎮 General Questions

### What is GameWikiTooltip?
GameWikiTooltip is an AI-powered overlay tool that provides instant game information without leaving your game. It combines wiki access with AI-driven Q&A using local knowledge bases.

### Which platforms are supported?
Currently, GameWikiTooltip only supports **Windows 10/11**. Linux and macOS support may be considered in future versions.

### Is it free?
Yes! GameWikiTooltip is completely free and open-source. The AI features require a Google Gemini API key, which offers a generous free tier.

### Will using this tool get me banned from games?
No. GameWikiTooltip is a non-invasive overlay that doesn't modify game files or memory. It works similarly to Discord overlay or Steam overlay.

## 🚨 Common Issues & Solutions

### Hotkey Not Working

**Problem**: Pressing the hotkey doesn't show the overlay

**Solutions**:
1. **Run as Administrator**
   - Right-click `GameWikiAssistant.exe`
   - Select "Run as administrator"

2. **Check for Conflicts**
   - Some games or applications may use the same hotkey
   - Try changing to a different combination (e.g., `Ctrl+D`)

3. **Antivirus Interference**
   - Add GameWikiTooltip to your antivirus whitelist
   - Windows Defender may block hotkey hooks

4. **Game in Fullscreen**
   - Try switching game to Borderless Windowed mode
   - Some exclusive fullscreen games block overlays

### Game Not Detected

**Problem**: The tool doesn't recognize my game

**Solutions**:
1. **Check Window Title**
   - The game window title must match the configuration
   - Use Task Manager to see the exact window title

2. **Add Game Manually**
   - Configure in tray settings
   - Or directly edit `src/game_wiki_tooltip/assets/games.json`:
   ```json
   {
     "Your Game Name": {
       "BaseUrl": "https://wiki.example.com",
       "NeedsSearch": true
     }
   }
   ```

3. **Language Variants**
   - Check both `games_en.json` and `games_zh.json`
   - Some games have different titles in different languages

### AI Features Not Working

**Problem**: AI chat doesn't respond or gives errors

**Solutions**:
1. **API Key Issues**
   - Verify your Gemini API key is correct
   - Check if you've exceeded the free tier limits
   - Get a new key at [Google AI Studio](https://makersuite.google.com/app/apikey)

2. **Network Connection**
   - AI features require internet connection
   - Check firewall settings
   - Try using a VPN if Google services are blocked

3. **Missing Vector Database**
   ```bash
   # Rebuild vector index for a game
   python src/game_wiki_tooltip/ai/build_vector_index.py --game helldiver2
   ```

### Overlay Not Showing

**Problem**: Hotkey works but no overlay appears

**Solutions**:
1. **Install WebView2 Runtime**
   - Run `runtime/MicrosoftEdgeWebView2Setup.exe` from the package
   - Or download from [Microsoft](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

2. **Graphics Compatibility**
   - Disable Hardware Acceleration in settings
   - Update graphics drivers
   - Try compatibility mode for Windows 8

3. **Multiple Monitors**
   - Overlay may appear on wrong monitor
   - Move game to primary monitor
   - Check display scaling settings

### Voice Recognition Not Working

**Problem**: Voice input doesn't activate or recognize speech

**Solutions**:
1. **Microphone Permissions**
   - Windows Settings → Privacy → Microphone
   - Allow apps to access microphone

2. **Download Voice Model**
   ```bash
   python download_vosk_models.py
   ```

3. **Audio Device**
   - Set correct default microphone in Windows
   - Check microphone volume levels

## 📚 Configuration Questions

### How do I change the hotkey?

1. Right-click system tray icon
2. Select "Settings"
3. Click on hotkey field
4. Press new key combination
5. Click "Save"

### Where are settings stored?

- Windows: `%APPDATA%/game_wiki_tooltip/settings.json`

### How do I add a new game?

See [Adding New Games](#game-not-detected) section above.

### Can I use multiple API keys?

Currently, only one Gemini API key is supported. You can switch between keys in settings.

## 🤖 AI & Knowledge Base

### What games have AI support?

Full AI support with knowledge bases:
- HELLDIVERS 2
- Elden Ring
- Don't Starve Together
- Civilization VI

Basic wiki support: 100+ other games

### How accurate is the AI?

The AI uses curated knowledge bases from community guides. Accuracy is generally high for factual information, but always verify critical game decisions.

### Can I add my own knowledge base?

Yes! See [Building Custom Knowledge Bases](ARCHITECTURE.md#knowledge-base) for details.

### Does AI work offline?

Partially. The vector search works offline, but generating responses requires internet connection to Google Gemini API.

## 🛠️ Technical Questions

### System Requirements

**Minimum**:
- Windows 10 version 1803
- 4GB RAM
- 500MB disk space
- Internet connection (for AI features)

**Recommended**:
- Windows 11
- 8GB RAM
- 1GB disk space
- Stable broadband connection

### Is my data private?

- **Local Storage**: All settings and history stored locally
- **API Calls**: Queries sent to Google Gemini are subject to Google's privacy policy
- **No Tracking**: We don't collect any usage data

### Can I contribute to the project?

Absolutely! We welcome:
- Bug reports and fixes
- New game support
- Knowledge base contributions
- Documentation improvements
- Translations

See [Contributing Guide](CONTRIBUTING.md) for details.

## 🔍 Debugging

### Where are log files?

```
%APPDATA%/game_wiki_tooltip/logs/
```

### How to enable debug mode?

Add to settings.json:
```json
{
  "debug": true,
  "log_level": "DEBUG"
}
```

### Reporting bugs effectively

Include:
1. Windows version
2. Game name and version
3. Error messages from logs
4. Steps to reproduce
5. Screenshots if applicable

## 📞 Still Need Help?

- **GitHub Issues**: [Report a bug](https://github.com/rimulu030/gamewiki/issues/new)
- **Discussions**: [Ask the community](https://github.com/rimulu030/gamewiki/discussions)
- **Discord**: [Join our server](https://discord.gg/gamewiki)
- **Email**: support@gamewikitooltip.com

## 🔄 Updates

### How do I update?

**Portable Version**:
1. Download new release
2. Extract to same folder (overwrites old files)
3. Your settings are preserved

**Source Version**:
```bash
git pull
pip install -r requirements.txt --upgrade
```

### Will updates break my settings?

No, settings are stored separately and preserved across updates.

### How often are updates released?

We aim for monthly releases with bug fixes and new game support. Major features are released quarterly.

---

**Didn't find your answer?** [Ask on GitHub Discussions](https://github.com/rimulu030/gamewiki/discussions)