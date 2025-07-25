"""
Early splash screen loader - shows splash immediately on startup.
This module has minimal imports to ensure fastest possible display.
"""

def show_early_splash():
    """Show splash screen with absolute minimal imports"""
    # Only import what we absolutely need
    from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont
    import sys
    
    # Check if QApplication already exists
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Create minimal splash window
    splash = QWidget()
    splash.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    splash.setFixedSize(300, 150)
    
    # Center on screen
    screen = QApplication.primaryScreen().geometry()
    x = (screen.width() - splash.width()) // 2
    y = (screen.height() - splash.height()) // 2
    splash.move(x, y)
    
    # Simple layout
    layout = QVBoxLayout()
    splash.setLayout(layout)
    
    # Background
    bg = QWidget()
    bg.setStyleSheet("""
        background-color: #2b2b2b;
        border-radius: 10px;
        border: 1px solid #444;
    """)
    bg_layout = QVBoxLayout(bg)
    
    # Title
    title = QLabel("🎮 GameWiki Assistant")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
    bg_layout.addWidget(title)
    
    # Status
    status = QLabel("Loading...")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status.setStyleSheet("color: #cccccc; font-size: 12px;")
    bg_layout.addWidget(status)
    
    # First run notice if applicable
    if hasattr(sys, '_MEIPASS'):
        import os
        marker_file = os.path.join(os.environ.get('TEMP', ''), '.gamewiki_first_run')
        if not os.path.exists(marker_file):
            notice = QLabel("First run: Extracting files...")
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
            notice.setStyleSheet("color: #ffcc00; font-size: 11px;")
            bg_layout.addWidget(notice)
    
    layout.addWidget(bg)
    
    # Show immediately
    splash.show()
    app.processEvents()
    
    return splash, app