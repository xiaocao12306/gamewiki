# GameWikiTooltip - Intelligent Game Wiki Overlay Tool

An intelligent Wiki overlay tool designed specifically for gamers, featuring automatic game detection and AI-powered RAG (Retrieval-Augmented Generation) capabilities for smart Q&A services.
👉 [中文说明请点击这里](README.zh-CN.md)
## 🎮 Key Features

- **Global Hotkey Activation** - Quick Wiki overlay access with customizable hotkey combinations
- **Smart Game Detection** - Automatically detects the currently active game window
- **Multi-Game Support** - Built-in Wiki configurations for 12 popular games
- **Floating Overlay** - Displays Wiki content above games without interrupting gameplay
- **System Tray Management** - Runs in background with system tray icon management
- **Custom Configuration** - Add new games and customize Wiki links
- **Keyword Mapping** - Intelligent mapping from in-game keywords to Wiki pages
- **Dual UI Architecture** - Traditional WebView version and modern Qt version
- **Unified Window Management** - Integrated search, settings, and display interface
- **AI RAG Integration** - Google Gemini AI and local vector search engine
- **Local Vector Search** - FAISS vector database for document retrieval
- **Multi-Game Knowledge Base** - Built-in knowledge bases and strategy data for multiple games
- **Hybrid Search** - Combines vector search and BM25 algorithm
- **Smart Re-ranking** - Intent-aware search result reordering
- **Quality Assessment** - Built-in RAG system quality evaluation and optimization framework
- **Adaptive Retrieval** - Intelligent search strategy and parameter optimization

## 🚀 Quick Start

### System Requirements

- Windows 10/11
- Python 3.8+
- Internet connection
- Google Cloud account (optional, for RAG features)

### Installation

1. **Clone the project**
   ```bash
   git clone https://github.com/your-username/gamewiki.git
   cd gamewiki
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   
   **Qt version (Recommended):**
   ```bash
   python src/game_wiki_tooltip/qt_app.py
   ```
   
   **Unified window version:**
   ```bash
   python src/game_wiki_tooltip/unified_window.py
   ```
   
   **Traditional version (WebView):**
   ```bash
   python -m src.game_wiki_tooltip
   ```

### First Time Setup

1. Launch the application - a hotkey setup window will appear
2. Set your preferred hotkey combination (default: Ctrl + X)
3. After setup, the application will display an icon in the system tray
4. Press the hotkey in-game to activate the Wiki overlay

## 🎯 Supported Games

Currently supports Wiki quick access for the following games:

- **VALORANT** - Riot Games' tactical shooter
- **Counter-Strike 2** - Valve's tactical shooter
- **Delta Force** - Tactical military shooter
- **MONSTER HUNTER: WORLD** - Capcom's action RPG
- **Monster Hunter Wilds** - Upcoming Monster Hunter title
- **Stardew Valley** - Farming simulation RPG
- **Don't Starve Together** - Survival game multiplayer
- **Don't Starve** - Survival adventure game
- **Elden Ring** - FromSoftware's action RPG
- **HELLDIVERS 2** - Arrowhead's cooperative shooter
- **7 Days to Die** - Survival horror game
- **Civilization VI** - Turn-based strategy game

## 📚 Game Knowledge Bases

The project includes detailed knowledge base data for multiple games:

### Knowledge Base Data Files
- **civilization6.json** - Civilization 6 game data
- **dst.json** - Don't Starve Together data
- **eldenring.json** - Elden Ring data
- **helldiver2.json** - Helldivers 2 data

### Special Features
- **Smart Q&A** - Natural language Q&A based on game knowledge bases
- **Fast Retrieval** - Millisecond-level search response
- **Multi-dimensional Search** - Support for weapons, equipment, skills, strategies, and more
- **Relevance Ranking** - Intelligent ranking of most relevant search results

## 💡 Usage Examples

### Basic Usage
1. **Launch the application** - Choose your preferred version (Qt recommended)
2. **Set hotkey** - Configure your hotkey combination on first run
3. **In-game activation** - Press hotkey during gameplay to open Wiki overlay
4. **AI Q&A** - Use RAG features for intelligent question answering
5. **Close application** - Right-click system tray icon to exit

### Advanced Features
- **Keyword Search** - Enter keywords in the overlay for quick searches
- **Window Adjustment** - Resize and reposition the overlay window
- **Multi-window Support** - Open multiple Wiki pages simultaneously
- **AI Smart Q&A** - Intelligent Q&A system based on multi-game knowledge bases
- **Local Vector Search** - Fast retrieval using local databases
- **Hybrid Search** - Combines semantic and keyword search
- **Quality Assessment** - Real-time search result quality evaluation
- **Multi-game Support** - Specialized knowledge bases for different games
- **Unified Interface** - Integrated search, settings, and management functions

### Version Selection Guide
- **Qt Version** - Recommended for better user experience and stability
- **WebView Version** - Traditional version, suitable for lightweight needs
- **Unified Window Version** - Single interface integrating all functions

## 🔧 Configuration

### Hotkey Settings

The application supports customizable hotkey combinations:
- Modifier keys: Ctrl, Alt, Shift, Win
- Function keys: F1-F12, A-Z, etc.
- Qt version provides better hotkey management and configuration interface

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

3. **Build Vector Indexes**
   ```bash
   # Build FAISS vector index
   python src/game_wiki_tooltip/ai/build_vector_index.py
   
   # Build enhanced BM25 index
   python src/game_wiki_tooltip/ai/enhanced_bm25_indexer.py
   
   # Rebuild all enhanced indexes
   python src/game_wiki_tooltip/ai/rebuild_enhanced_indexes.py
   ```

4. **Run Quality Evaluation**
   ```bash
   python src/game_wiki_tooltip/ai/run_quality_evaluation.py
   ```

5. **Vector Database Diagnosis**
   ```bash
   python test_diagnose_vector.py
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
   - Run vector diagnosis tool

5. **Inaccurate Search Results**
   - Check if knowledge base data is up to date
   - Adjust RAG configuration parameters
   - Run quality evaluation tool
   - Rebuild vector indexes
   - Use adaptive retrieval optimization

6. **Performance Issues**
   - Run vector database diagnosis
   - Check batch embedding processing settings
   - Optimize hybrid search parameters
   - Clean and rebuild indexes

### Logs

Application logs are located at: `%APPDATA%/game_wiki_tooltip/`

### Diagnostic Tools

- **Vector Diagnosis** - `python diagnose_vector.py`
- **Quality Evaluation** - `python src/game_wiki_tooltip/ai/run_quality_evaluation.py`
- **Index Rebuild** - `python src/game_wiki_tooltip/ai/rebuild_enhanced_indexes.py`

## 🤖 AI Features

### RAG (Retrieval-Augmented Generation)
- Based on Google Gemini 2.0 Flash model
- Supports multiple document formats (JSON, PDF, Markdown, etc.)
- Provides accurate citations and source links
- Unified RAG configuration management system
- Optimized batch embedding processing

### Local Vector Search
- Uses FAISS vector database
- Supports Chinese multi-language embedding models
- Localized document retrieval for privacy protection
- Fast similarity search
- Enhanced index building process

### Hybrid Search System
- Combines vector search and BM25 algorithm
- Adaptive fusion strategy (RRF - Reciprocal Rank Fusion)
- Intelligent weight adjustment
- Multi-dimensional relevance evaluation
- Adaptive hybrid retrieval optimization

### Smart Query Processing
- Game-aware query preprocessing
- Intent analysis and classification
- Query rewriting and optimization
- Multi-language support
- Unified query processing pipeline

### Quality Assessment Framework
- Automatic quality assessment system
- Detailed evaluation report generation
- Support for multiple evaluation metrics
- Continuous optimization recommendations
- Real-time quality monitoring

### Experimental Features
- **Adaptive Hybrid Retrieval** - Dynamic retrieval strategy adjustment
- **Game-Aware Query Processing** - Specialized processing for game content
- **Hybrid Search Optimizer** - Intelligent search parameter optimization
- **Data Cleaning Tools** - Automatic knowledge base data cleaning and optimization

## 🛠️ Technical Details

### Core Technologies
- **Cross-process Hotkeys** - Windows API implementation for global hotkeys
- **Dual UI Architecture** - WebView and Qt UI implementations
- **Smart Window Management** - Automatic window position and size saving/restoration
- **Asynchronous Processing** - asyncio for concurrent task handling
- **Hot Configuration Updates** - Runtime game configuration updates

### AI Technology Stack
- **AI Integration** - Google Gemini AI and local vector search integration
- **Multi-language Support** - Chinese and other language document processing
- **FAISS Vector Storage** - Efficient similarity search engine
- **BM25 Text Search** - Traditional keyword search optimization
- **Hybrid Retrieval Fusion** - RRF algorithm for multiple search result fusion
- **Smart Intent Analysis** - Automatic query intent type recognition
- **Quality Assessment System** - Automatic RAG system performance evaluation

### Advanced Features
- **Batch Embedding Processing** - Large-scale document vectorization optimization
- **Adaptive Retrieval** - Dynamic search strategy adjustment
- **Intent-Aware Re-ranking** - Query intent-based result ranking optimization
- **Query Translation and Processing** - Multi-language query processing capabilities
- **Real-time Quality Monitoring** - Continuous system performance monitoring

## 📁 Project Structure

```
gamewiki/
├── src/game_wiki_tooltip/          # Main program source code
│   ├── __main__.py                 # Main program entry
│   ├── config.py                   # Configuration management
│   ├── i18n.py                     # Internationalization support
│   ├── utils.py                    # Utility functions
│   ├── assistant_integration.py    # AI assistant integration
│   ├── auto_click.js               # Auto-click script
│   │
│   ├── app_v1/                     # Traditional WebView version
│   │   ├── app.py                  # Main application
│   │   ├── overlay.py              # Overlay management
│   │   ├── hotkey.py               # Hotkey management
│   │   ├── tray_icon.py            # System tray
│   │   ├── searchbar.py            # Search bar component
│   │   └── hotkey_setup.py         # Hotkey setup interface
│   │
│   ├── # Qt version implementation
│   ├── qt_app.py                   # Qt main application
│   ├── qt_hotkey_manager.py        # Qt hotkey manager
│   ├── qt_settings_window.py       # Qt settings window
│   ├── qt_tray_icon.py             # Qt system tray
│   ├── unified_window.py           # Unified window interface
│   │
│   ├── ai/                         # AI feature modules
│   │   ├── rag_config.py           # RAG configuration management
│   │   ├── rag_engine_factory.py   # RAG engine factory
│   │   ├── rag_query.py            # RAG query processing
│   │   ├── hybrid_retriever.py     # Hybrid retriever
│   │   ├── enhanced_bm25_indexer.py # Enhanced BM25 indexer
│   │   ├── enhanced_query_processor.py # Enhanced query processor
│   │   ├── unified_query_processor.py # Unified query processor
│   │   ├── build_vector_index.py   # Vector index building
│   │   ├── batch_embedding.py      # Batch embedding processing
│   │   ├── rebuild_enhanced_indexes.py # Rebuild enhanced indexes
│   │   ├── rag_quality_evaluator.py # Quality evaluator
│   │   ├── run_quality_evaluation.py # Evaluation runner
│   │   ├── gemini_summarizer.py    # Gemini summarizer
│   │   ├── query_translator.py     # Query translator
│   │   ├── intent_aware_reranker.py # Intent-aware reranker
│   │   │
│   │   ├── intent/                 # Intent analysis module
│   │   │   └── intent_classifier.py
│   │   │
│   │   ├── trial_proto/            # Experimental prototypes
│   │   │   ├── adaptive_hybrid_retriever.py
│   │   │   ├── game_aware_query_processor.py
│   │   │   ├── hybrid_search_optimizer.py
│   │   │   └── cleanchunk.py
│   │   │
│   │   ├── vectorstore/            # Vector storage
│   │   │   ├── helldiver2_vectors/
│   │   │   │   ├── index.faiss
│   │   │   │   ├── metadata.json
│   │   │   │   └── enhanced_bm25_index.pkl
│   │   │   ├── eldenring_vectors/
│   │   │   │   ├── index.faiss
│   │   │   │   └── metadata.json
│   │   │   ├── helldiver2_vectors_config.json
│   │   │   └── eldenring_vectors_config.json
│   │   │
│   │   └── evaluate_report/        # Evaluation reports
│   │       └── helldivers2/
│   │           └── quality_report_*.json/md
│   │
│   └── assets/                     # Resource files
│       ├── games.json              # Main game configuration
│       ├── games_en.json           # English game configuration
│       ├── games_zh.json           # Chinese game configuration
│       ├── settings.json           # Default settings
│       └── app.ico                 # Application icon
│
├── data/                           # Game data and resources
│   ├── knowledge_chunk/            # Knowledge base data
│   │   ├── 7daystodie.json
│   │   ├── civilization6.json
│   │   ├── dst.json
│   │   ├── eldenring.json
│   │   └── helldiver2.json
│   │
│   ├── evaluator/                  # Evaluator data
│   │   ├── helldivers2_enemy_weakpoints.json
│   │   ├── inoutput/
│   │   └── quality_report_*.json/md
│   │
│   ├── sample_inoutput/            # Sample input/output
│   │   └── helldiver2.json
│   │
│   ├── sync/                       # Sync data
│   │   └── root/
│   │
│   ├── GameFloaty.pdf              # Game documentation
│   ├── warbond.srt                 # Warbond data
│   ├── warbondmd.md                # Warbond strategy
│   └── dbprompt.docx               # Database prompt document
│
├── tests/                          # Test files
├── diagnose_vector.py              # Vector diagnosis tool
├── requirements.txt                # Python dependencies
├── pyproject.toml                  # Project configuration
├── LICENSE                         # License
├── CLAUDE.md                       # Claude AI documentation
└── README.md                       # Documentation
```

## 🤝 Contributing

We welcome Issue submissions and Pull Requests!

1. Fork the project
2. Create a feature branch
3. Submit changes
4. Create a Pull Request

### Development Guidelines

- **Code Structure** - Follow the existing modular architecture
- **AI Features** - Place experimental features in the `trial_proto/` directory
- **Testing** - Ensure new features have corresponding test coverage
- **Documentation** - Update relevant documentation and configuration instructions

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
