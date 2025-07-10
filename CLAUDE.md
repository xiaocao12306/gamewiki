# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GameWikiTooltip is a Windows desktop application that provides an intelligent in-game wiki overlay with AI-powered game assistance. It uses global hotkeys to display game-specific information and answers questions using RAG (Retrieval-Augmented Generation) technology.

## Essential Commands

### Development Setup
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Run as module (recommended)
python -m game_wiki_tooltip

# Alternative: direct execution
python src/game_wiki_tooltip/app.py
```

### Building the Application
```bash
# Build standalone Windows executable
pyinstaller app.spec
# Output: dist/app.exe
```

### AI/Vector Database Commands
```bash
# Build vector index for a specific game
python src/game_wiki_tooltip/ai/build_vector_index.py --game helldiver2

# Build for all games
python src/game_wiki_tooltip/ai/build_vector_index.py --game all

# List available games
python src/game_wiki_tooltip/ai/build_vector_index.py --list-games
```

## Architecture Overview

### Core Components
- **app.py**: Main application entry point, manages window lifecycle and system integration
- **overlay.py**: WebView-based overlay window that displays wiki content
- **hotkey.py**: Windows API integration for global hotkey detection (Win32 API)
- **config.py**: Configuration management, including API keys and user settings
- **tray_icon.py**: System tray integration for background operation

### AI System Architecture
The AI subsystem uses a sophisticated multi-stage pipeline:

1. **Query Processing Flow**:
   - `game_aware_query_processor.py`: Detects language, intent, and optimizes queries
   - `hybrid_retriever.py`: Combines FAISS vector search with BM25 for optimal retrieval
   - `intent_aware_reranker.py`: Re-ranks results based on detected intent
   - `gemini_summarizer.py`: Generates final responses using Google's Gemini

2. **Vector Storage**:
   - FAISS indexes stored in `ai/vectorstore/{game}_vectors/`
   - Metadata and configurations in corresponding JSON files
   - Support for both local FAISS and cloud Qdrant backends

3. **Knowledge Management**:
   - Game knowledge stored in `data/knowledge_chunk/{game}.json`
   - Batch embedding via Jina AI API for vector generation
   - Automatic chunking and metadata extraction

### Key Technical Considerations

1. **Windows-Specific Implementation**:
   - Uses `pywin32` for Windows API access
   - Global hotkeys require proper Windows message pump handling
   - Administrator privileges may be needed for some features

2. **Asynchronous Operations**:
   - AI queries run asynchronously to prevent UI blocking
   - WebView runs in separate thread for smooth overlay rendering

3. **Configuration Storage**:
   - User settings in `%APPDATA%/game_wiki_tooltip/settings.json`
   - API keys stored securely in configuration
   - Game-specific settings in `assets/games.json`

4. **AI Model Configuration**:
   - Supports multiple LLM providers (Gemini, OpenAI)
   - Configurable embedding models (Jina, text-embedding-3-small)
   - Temperature and other parameters adjustable per query type

## Important Development Notes

1. **Testing AI Features**:
   - Ensure JINA_API_KEY is set for embedding generation
   - Google Cloud credentials needed for Gemini integration
   - Test with small knowledge chunks first to verify pipeline

2. **Adding New Games**:
   - Add game configuration to `assets/games.json`
   - Create knowledge chunk JSON in `data/knowledge_chunk/`
   - Build vector index using the build script
   - Update supported games list in README

3. **Debugging Tips**:
   - Check `%APPDATA%/game_wiki_tooltip/` for logs
   - Use `--verbose` flag with AI scripts for detailed output
   - WebView console accessible via F12 in overlay window

4. **Performance Considerations**:
   - Vector searches are memory-intensive; monitor RAM usage
   - Batch process embeddings to avoid API rate limits
   - Cache frequently accessed game data in memory

5. **Security Notes**:
   - Never commit API keys to repository
   - Use environment variables or secure config for credentials
   - Validate all user input before processing AI queries