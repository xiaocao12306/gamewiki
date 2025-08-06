# GameWikiTooltip - Intelligent Game Wiki Overlay Tool

An intelligent Wiki overlay tool designed specifically for gamers, featuring automatic game detection and AI-powered RAG (Retrieval-Augmented Generation) capabilities for smart Q&A services.
👉 [中文说明请点击这里](README.zh-CN.md)
## 🎮 Key Features

- **Global Hotkey Activation** - Quick Wiki overlay access with customizable hotkey combinations
- **Smart Game Detection** - Automatically detects the currently active game window
- **Floating Overlay** - Displays Wiki content above games without interrupting gameplay
- **AI-Powered Q&A** - Google Gemini AI with local vector search for intelligent game assistance
- **Multi-Game Support** - Built-in Wiki configurations and AI knowledge bases

## 🎯 Supported Games

### 🤖 AI-Enhanced Games (Full Knowledge Base Support)
These games feature advanced AI Q&A with comprehensive knowledge bases:

- **HELLDIVERS 2** - Cooperative shooter with weapons, stratagems, and enemy data
- **Elden Ring** - Action RPG with items, weapons, spells, and boss strategies  
- **Don't Starve Together** - Survival multiplayer with crafting recipes and character guides
- **Civilization VI** - Strategy game with civilizations, units, and victory guides

### 📖 Wiki Access Games
Basic Wiki overlay support for quick reference:

- **VALORANT, Counter-Strike 2** - Tactical shooters
- **Monster Hunter Series** - Action RPGs
- **Stardew Valley** - Farming simulation
- **7 Days to Die** - Survival horror
- ... Hundreds of games
## 🤖 AI Features

### Smart Q&A System
- **Natural Language Processing** - Ask questions in plain English/Chinese
- **Fast Vector Search** - Millisecond-level response with FAISS database
- **Hybrid Search** - Combines semantic vector search with BM25 keyword matching
- **Comprehensive Coverage** - Weapons, items, strategies, characters, and game mechanics
- **Source Citations** - Every answer includes relevant source references

### AI Knowledge Base Management
- **Vector Store Builder** - Build FAISS vector indexes for semantic search
- **BM25 Index Builder** - Create high-performance keyword search indexes using bm25s
- **Multi-language Support** - Intelligent text processing for Chinese and English
- **Game-specific Optimization** - Customized processing for different game types

## 🚀 Quick Start

### System Requirements

- Windows 10/11
- Python 3.8+
- Internet connection
- Google Cloud account (for RAG features)

### Installation

1. **Clone the project**
   ```bash
   git clone https://github.com/rimulu030/gamewiki.git
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   
3. **Set up environment variables**
   ```bash
   # Set your GEMINI API key for vector embeddings and AI rag function
   GEMINI_API_KEY="your_gemini_api_key_here"
   ```

5. **Run the application**
   ```bash
   python -m src.game_wiki_tooltip
   ```

### First Time Setup

1. Launch the application - a hotkey setup window will appear
2. Set your preferred hotkey combination (default: Ctrl + X)
3. After setup, the application will display an icon in the system tray
4. Press the hotkey in-game to activate the Wiki overlay


## 🔧 Configuration

### Hotkey Settings

The application supports customizable hotkey combinations:
- Modifier keys: Ctrl, Alt, Shift, Win
- Function keys: A-Z

### Game Configuration

Game configuration files are located at: `src/game_wiki_tooltip/assets/games.json`

Multi-language configuration support:
- `games_en.json` - English game configuration
- `games_zh.json` - Chinese game configuration
- `games.json` - Main configuration file

Each game configuration includes:
```json
{
    "Game Name": {
        "BaseUrl": "Wiki base URL",
        "NeedsSearch": true/false
    }
}
```

### AI RAG Configuration

1. **Set Google AI API Key**
   ```bash
   # Set environment variable
   export GOOGLE_API_KEY="your-api-key"
   ```

2. **Configure RAG System**
   The system uses a unified RAG configuration manager located at:
   ```
   src/game_wiki_tooltip/ai/rag_config.py
   ```

3. **Build Custom Knowledge Base/Vector Indexes**

#### Knowledge Base Format
Knowledge bases should be JSON files in the `data/knowledge_chunk/` directory with the following structure:
```json
[
  {
    "video_info": { "url": "...", "title": "...", "game": "..." },
    "knowledge_chunks": [
      {
        "chunk_id": "unique_id",
        "topic": "Topic Title",
        "summary": "Detailed description...",
        "keywords": ["keyword1", "keyword2"],
        "type": "Build_Recommendation",
        "build": { "name": "...", "focus": "..." },
        "structured_data": { "enemy_name": "...", "weak_points": [...] }
      }
    ]
  }
]
```

   ```bash
   # Build FAISS vector index for a specific game
   python src/game_wiki_tooltip/ai/build_vector_index.py --game game_name
   ```

### Adding New Games

1. Edit the `games.json` file
2. Add new game configuration
3. Restart the application

Example configuration:
```json
{
    "New Game Name": {
        "BaseUrl": "https://wiki.example.com",
        "NeedsSearch": true
    }
}
```

## 🛠️ Project Structure

```
gamewiki/
├── src/
│   ├── game_wiki_tooltip/       # Main application module
│   │   ├── ai/                  # AI and RAG related features
│   │   │   ├── vectorstore/     # FAISS vector index storage
│   │   │   ├── build_vector_index.py  # Vector index builder
│   │   │   ├── enhanced_bm25_indexer.py # Enhanced BM25 indexer
│   │   │   ├── batch_embedding.py    # Batch embedding processor
│   │   │   ├── gemini_embedding.py   # Gemini embedding service
│   │   │   ├── gemini_summarizer.py  # Gemini summarization
│   │   │   ├── hybrid_retriever.py   # Hybrid retrieval system
│   │   │   ├── intent_aware_reranker.py # Intent-aware reranker
│   │   │   ├── unified_query_processor.py # Unified query processor
│   │   │   ├── rag_config.py         # RAG configuration manager
│   │   │   └── rag_query.py          # RAG query interface
│   │   ├── assets/              # Static resource files
│   │   │   ├── games.json       # Game configuration
│   │   │   ├── games_en.json    # English game configuration
│   │   │   ├── games_zh.json    # Chinese game configuration
│   │   │   ├── settings.json    # Application settings
│   │   │   ├── vector_mappings.json # Vector mapping config
│   │   │   ├── html/            # Game task flow HTML
│   │   │   ├── icons/           # Icon resources
│   │   │   └── vosk_models/     # Voice recognition models
│   │   ├── core/                # Core functionality modules
│   │   │   ├── config.py        # Configuration management
│   │   │   ├── graphics_compatibility.py # Graphics compatibility
│   │   │   ├── i18n.py          # Internationalization support
│   │   │   ├── smart_interaction_manager.py # Smart interaction
│   │   │   └── utils.py         # Utility functions
│   │   ├── window_component/    # Window components
│   │   │   ├── chat_messages.py      # Chat message handling
│   │   │   ├── chat_view.py          # Chat view component
│   │   │   ├── chat_widgets.py       # Chat UI widgets
│   │   │   ├── enums.py              # Enumerations
│   │   │   ├── history_manager.py    # History management
│   │   │   ├── markdown_converter.py # Markdown conversion
│   │   │   ├── quick_access_popup.py # Quick access popup
│   │   │   ├── svg_icon.py           # SVG icon handler
│   │   │   ├── unified_window.py     # Unified window system
│   │   │   ├── voice_recognition.py  # Voice recognition
│   │   │   ├── wiki_view.py          # Wiki view component
│   │   │   └── window_controller.py  # Window controller
│   │   ├── webview2/            # WebView2 components
│   │   │   └── lib/             # WebView2 libraries
│   │   ├── qt_app.py            # Qt application main entry
│   │   ├── qt_hotkey_manager.py # Global hotkey management
│   │   ├── qt_settings_window.py # Settings window
│   │   ├── qt_tray_icon.py      # System tray icon
│   │   ├── assistant_integration.py  # AI assistant integration
│   │   ├── preloader.py         # Application preloader
│   │   ├── splash_screen.py     # Splash screen
│   │   ├── webview_widget.py    # WebView component
│   │   ├── webview2_setup.py    # WebView2 setup
│   │   └── webview2_simple.py   # Simple WebView2 component
│   ├── live_api/                # Live API module
│   │   ├── config.py            # Live API configuration
│   │   ├── main.py              # Live API main entry
│   │   └── requirements.txt     # Live API dependencies
│   └── live_api_in_progress/    # Live API development module
│       ├── audio_player.py      # Audio playback
│       ├── conversation_manager.py # Conversation management
│       ├── live_api_client.py   # Live API client
│       └── voice_listener.py    # Voice listening service
├── data/
│   ├── knowledge_chunk/         # Game knowledge base JSON files
│   │   ├── helldiver2.json     # HELLDIVERS 2 knowledge base
│   │   ├── eldenring.json      # Elden Ring knowledge base
│   │   ├── dst.json            # Don't Starve Together knowledge base
│   │   └── civilization6.json  # Civilization VI knowledge base
│   └── LLM_prompt/             # LLM prompt templates
├── requirements.txt             # Python dependencies
├── CLAUDE.md                   # Claude AI development guide
├── README.md                   # English documentation
└── README.zh-CN.md             # Chinese documentation
```

## 🐛 Troubleshooting

### Common Issues

1. **Hotkey Not Responding**
   - Check for conflicts with other applications
   - Try changing the hotkey combination
   - Qt version provides better hotkey management

2. **Game Not Detected**
   - Confirm game window title is included in configuration
   - Manually add game configuration
   - Check multi-language configuration files

3. **Wiki Page Won't Load**
   - Check internet connection
   - Confirm Wiki website is accessible

4. **AI Features Not Working**
   - Check Google AI API key settings
   - Confirm internet connection is normal
   - Verify vector index files exist
   - Check knowledge base data file integrity

5. **Inaccurate Search Results**
   - Check if knowledge base data is up to date
   - Adjust RAG configuration parameters
   - Run quality evaluation tools
   - Rebuild vector indexes

6. **Performance Issues**
   - Run vector database diagnosis
   - Check batch embedding processing settings
   - Optimize hybrid search parameters
   - Clean and rebuild indexes

### Logs

Application logs are located at: `%APPDATA%/game_wiki_tooltip/`



#### Documentation
- **English**: [AI Module README](src/game_wiki_tooltip/ai/README.md)
- **中文**: [AI模块文档](src/game_wiki_tooltip/ai/README.zh-CN.md)、

## 🤝 Contributing

We welcome Issue submissions and Pull Requests!

1. Fork the project
2. Create a feature branch
3. Submit changes
4. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Thanks to all developers who have contributed to the gaming Wiki community!

Special thanks to:
- Google Gemini AI for providing powerful AI capabilities
- FAISS for providing efficient vector search engine
- Gaming community for contributing Wiki content and data

---

**Note**: This tool supports Windows systems. Qt version is recommended for the best experience. AI features require a Google AI API key. Python 3.8+ is recommended for best compatibility. Some features may require administrator privileges to run. 
