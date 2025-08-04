# GameWikiTooltip - Intelligent Game Wiki Overlay Tool

An intelligent Wiki overlay tool designed specifically for gamers, featuring automatic game detection and AI-powered RAG (Retrieval-Augmented Generation) capabilities for smart Q&A services.
👉 [中文说明请点击这里](README.zh-CN.md)
## 🎮 Key Features

- **Global Hotkey Activation** - Quick Wiki overlay access with customizable hotkey combinations
- **Smart Game Detection** - Automatically detects the currently active game window
- **Floating Overlay** - Displays Wiki content above games without interrupting gameplay
- **AI-Powered Q&A** - Google Gemini AI with local vector search for intelligent game assistance
- **Multi-Game Support** - Built-in Wiki configurations and AI knowledge bases
- **Hybrid Search** - Combines semantic vector search with traditional keyword search
- **System Tray Management** - Runs quietly in background with easy access

## 🚀 Quick Start

### System Requirements

- Windows 10/11
- Python 3.8+
- Internet connection
- Google Cloud account (optional, for RAG features)
- JINA API key (for vector embeddings)
- bm25s and faiss-cpu packages (for search indexes)

### Installation

1. **Clone the project**
   ```bash
   git clone https://github.com/rimulu030/gamewiki.git
   cd gamewiki
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install bm25s faiss-cpu
   ```

3. **Set up environment variables**
   ```bash
   # Set your JINA API key for vector embeddings
   export JINA_API_KEY="your_jina_api_key_here"
   ```

5. **Run the application**
   
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

### Building Custom Knowledge Bases
To add support for new games or update existing knowledge bases:

```bash
# Build vector store and BM25 index for a new game
python src/game_wiki_tooltip/ai/build_vector_index.py --game GAME_NAME

# Rebuild only BM25 indexes (keeping existing vector stores)
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py GAME_NAME

# For detailed documentation, see:
# src/game_wiki_tooltip/ai/README.md
```

## 💡 Usage Examples

### Basic Usage
1. **Launch the application** - Choose your preferred version (Qt recommended)
2. **Set hotkey** - Configure your hotkey combination on first run
3. **In-game activation** - Press hotkey during gameplay to open Wiki overlay
4. **AI Q&A** - Use RAG features for intelligent question answering
5. **Close application** - Right-click system tray icon to exit

### Advanced Features
- **AI Smart Q&A** - Ask natural language questions about supported games
- **Keyword Search** - Quick Wiki searches with overlay input
- **Window Adjustment** - Customizable overlay size and position
- **Multi-window Support** - Open multiple game references simultaneously

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
│   └── game_wiki_tooltip/       # Main application module
│       ├── ai/                  # AI and RAG related features
│       │   ├── vectorstore/     # FAISS vector index storage
│       │   ├── build_vector_index.py  # Vector index builder
│       │   ├── hybrid_retriever.py   # Hybrid retrieval system
│       │   ├── intent_aware_reranker.py # Intent-aware reranker
│       │   ├── unified_query_processor.py # Unified query processor
│       │   └── rag_query.py          # RAG query interface
│       ├── assets/              # Static resource files
│       │   ├── games.json       # Game configuration
│       │   ├── games_en.json    # English game configuration
│       │   ├── games_zh.json    # Chinese game configuration
│       │   ├── html/            # Game task flow HTML
│       │   └── icons/           # Icon resources
│       ├── window_component/    # Window components
│       │   ├── unified_window.py     # Unified window system
│       │   ├── wiki_view.py          # Wiki view component
│       │   └── window_controller.py  # Window controller
│       ├── qt_app.py            # Qt application main entry
│       ├── qt_hotkey_manager.py # Global hotkey management
│       ├── qt_settings_window.py # Settings window
│       ├── qt_tray_icon.py      # System tray icon
│       ├── assistant_integration.py  # AI assistant integration
│       ├── config.py            # Configuration management
│       ├── history_manager.py   # History management
│       ├── i18n.py             # Internationalization support
│       └── webview_widget.py    # WebView component
├── data/
│   ├── knowledge_chunk/         # Game knowledge base JSON files
│   │   ├── helldiver2.json     # HELLDIVERS 2 knowledge base
│   │   ├── eldenring.json      # Elden Ring knowledge base
│   │   ├── dst.json            # Don't Starve Together knowledge base
│   │   └── civilization6.json  # Civilization VI knowledge base
│   └── LLM_prompt/             # LLM prompt templates
├── requirements.txt             # Python dependencies
├── CLAUDE.md                   # Claude AI development guide
└── README.md                   # English documentation
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

## 🔧 AI Module Development

### Building Knowledge Bases
The AI module provides comprehensive tools for building and managing game knowledge bases:

#### Quick Commands
```bash
# Build complete knowledge base (vector + BM25)
python src/game_wiki_tooltip/ai/build_vector_index.py --game GAME_NAME

# Rebuild only BM25 indexes
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py GAME_NAME

# Verify existing indexes
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --verify-only
```

#### Knowledge Base Format
Knowledge bases should be JSON files in `data/knowledge_chunk/` with the following structure:
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

#### Documentation
- **English**: [AI Module README](src/game_wiki_tooltip/ai/README.md)
- **中文**: [AI模块文档](src/game_wiki_tooltip/ai/README.zh-CN.md)

### Prerequisites for AI Development
```bash
# Install AI dependencies
pip install bm25s faiss-cpu

# Set API key
export JINA_API_KEY="your_jina_api_key_here"
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
