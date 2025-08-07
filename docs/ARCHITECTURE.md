# Technical Architecture

## 🏗️ System Overview

GameWikiTooltip is built as a modular Windows desktop application with three main components:

```
┌─────────────────────────────────────────────────┐
│             User Interface Layer                │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐     │
│  │ PyQt6 UI │ │ WebView2 │ │ System Tray  │     │
│  └──────────┘ └──────────┘ └──────────────┘     │
└─────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────┐
│              Core Services Layer                │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐      │
│  │ Hotkey  │ │   Game   │ │    Window    │      │
│  │ Manager │ │ Detector │ │  Controller  │      │
│  └─────────┘ └──────────┘ └──────────────┘      │
└─────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────┐
│                 AI/RAG Layer                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐     │
│  │  Vector  │ │  Query   │ │   Gemini     │     │
│  │  Search  │ │ Processor│ │ Integration  │     │
│  └──────────┘ └──────────┘ └──────────────┘     │
└─────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
gamewiki/
├── src/game_wiki_tooltip/
│   ├── qt_app.py              # Main application entry
│   ├── assistant_integration.py # AI assistant controller
│   ├── window_component/       # UI components
│   │   ├── unified_window.py   # Main window system
│   │   ├── chat_view.py        # Chat interface
│   │   └── wiki_view.py        # Website browser
│   ├── ai/                     # AI subsystem
│   │   ├── rag_query.py        # RAG orchestrator
│   │   ├── hybrid_retriever.py # RAG retriever
│   │   └── gemini_summarizer.py # Response generator
│   └── core/                   # Core utilities
│       ├── config.py           # Configuration manager
│       └── i18n.py             # Internationalization
├── data/                       # Knowledge bases
└── docs/                       # Documentation
```

## 🔧 Core Components

### 1. Application Layer (`qt_app.py`)

The main Qt application that manages:
- Application lifecycle
- System tray integration
- Global hotkey registration
- Window management

**Key Technologies**:
- PyQt6 for GUI framework
- pywin32 for Windows API integration
- QSystemTrayIcon for background operation

### 2. Window System (`unified_window.py`)

Unified window controller handling:
- Overlay positioning
- Window states (compact/expanded)
- Always-on-top behavior

**Features**:
- blured background
- Click-through regions
- Dynamic resizing

### 3. Hotkey Management (`qt_hotkey_manager.py`)

Windows-native hotkey system:
```python
# Register global hotkey
win32gui.RegisterHotKey(hwnd, hotkey_id, modifiers, key_code)

# Process Windows messages
def process_hotkey(msg):
    if msg == win32con.WM_HOTKEY:
        trigger_overlay()
```

### 4. Game Detection

Automatic game recognition:
```python
def detect_active_game():
    # Get foreground window
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    
    # Match against game database
    for game in games_config:
        if game in title:
            return load_game_config(game)
```

## 🤖 AI/RAG Architecture

### RAG Pipeline

```
User Query
    │
    ▼
┌─────────────────┐
│ Query Processor │ ← Language detection, intent analysis
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Hybrid Retriever│ ← FAISS + BM25 search
└─────────────────┘
    │
    ▼
┌─────────────────┐
│    Reranker     │ ← Intent-aware scoring
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   Summarizer    │ ← Gemini response generation
└─────────────────┘
    │
    ▼
Response
```

### Key AI Components

#### 1. Vector Search (FAISS)
- Pre-built indices for each game
- ~768-dimensional embeddings
- Approximate nearest neighbor search
- Sub-second query times

#### 2. BM25 Text Search
- Traditional keyword matching
- Handles exact term queries
- Language-specific tokenization
- Complementary to vector search

#### 3. Hybrid Retrieval
```python
def hybrid_search(query):
    # Vector search for semantic similarity
    vector_results = faiss_index.search(query_embedding, k=10)
    
    # BM25 for keyword matching
    bm25_results = bm25_index.search(query_tokens, k=10)
    
    # Combine and rerank
    return rerank(vector_results + bm25_results)
```

#### 4. Intent-Aware Reranking
- Classifies query intent
- Adjusts result scoring
- Prioritizes relevant content types

### Knowledge Base Structure

```json
{
  "chunk_id": "unique_identifier",
  "topic": "Weapon: Railgun",
  "summary": "High-damage anti-armor weapon...",
  "keywords": ["railgun", "anti-armor", "weapon"],
  "type": "Equipment_Guide",
  "game": "HELLDIVERS 2",
  "metadata": {
    "damage": 900,
    "armor_penetration": "Heavy"
  }
}
```

## 🖼️ UI Architecture

### WebView2 Integration

For wiki display:
```python
class WikiView(WebView2):
    def __init__(self):
        self.create_webview()
        self.bind_javascript_interface()
        
    def navigate(self, url):
        self.webview.Navigate(url)
```

### Chat Interface

Custom Qt widgets:
- Markdown rendering
- Code syntax highlighting
- Image embedding support
- Voice input integration

## 🔐 Security Considerations

### API Key Management
- Stored in user's %APPDATA%
- Never committed to repository
- Encrypted in memory

### Process Isolation
- WebView2 runs in separate process
- Sandboxed JavaScript execution
- No direct file system access

### Input Validation
- Sanitize all user queries
- Escape special characters
- Prevent injection attacks

## 🎯 Performance Optimizations

### 1. Lazy Loading
- Load AI models on-demand
- Initialize game configs when needed
- Defer WebView2 creation

### 2. Caching Strategy
- Query result caching
- Vector embedding cache
- WebView page cache

### 3. Asynchronous Operations
```python
async def process_query_async(query):
    # Non-blocking RAG pipeline
    results = await hybrid_retriever.search_async(query)
    response = await gemini.generate_async(results)
    return response
```

### 4. Memory Management
- Release unused models
- Compress vector indices
- Periodic garbage collection

## 🔄 Data Flow

### Query Processing Flow

```
1. User Input (Text/Voice)
       ↓
2. Language Detection
       ↓
3. Intent Classification
       ↓
4. Query Expansion
       ↓
5. Hybrid Search
       ├── Vector Search (FAISS)
       └── Keyword Search (BM25)
       ↓
6. Result Fusion
       ↓
7. Reranking
       ↓
8. Context Building
       ↓
9. Response Generation (Gemini)
       ↓
10. UI Rendering
```

## 🛠️ Development Guidelines

### Code Organization
- Follow MVC pattern
- Separate concerns clearly
- Use dependency injection
- Write testable code

### Adding New Features
1. Create feature branch
2. Update relevant components
3. Add unit tests
4. Update documentation
5. Submit pull request

### Testing Strategy
- Unit tests for core logic
- Integration tests for AI pipeline
- UI automation tests
- Performance benchmarks

## 📊 Monitoring & Debugging

### Logging System
```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Log to file and console
file_handler = logging.FileHandler('app.log')
console_handler = logging.StreamHandler()
```

### Performance Metrics
- Query response time
- Memory usage
- API call frequency
- Cache hit rates

### Debug Mode
Enable in settings.json:
```json
{
  "debug": true,
  "log_level": "DEBUG",
  "show_timings": true
}
```

## 🚀 Future Architecture Plans

### Planned Improvements
1. **Plugin System**: Allow third-party extensions
2. **Cloud Sync**: Synchronize settings and history
3. **Multi-Language Models**: Support for local LLMs
4. **Streaming Responses**: Real-time answer generation
5. **P2P Knowledge Sharing**: Community-driven knowledge bases

### Scalability Considerations
- Microservice architecture for AI components
- Distributed vector search
- Edge caching for popular queries
- Load balancing for API calls

---

For implementation details, see the source code and inline documentation.