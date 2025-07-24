# GameWiki Assistant 便携版

## Instructions

1. **Read Before First Use**: This application uses WebView2 technology and requires Microsoft Edge WebView2 Runtime.
2. Double-click GameWikiAssistant.exe to start the program.
3. Opening this exe can take a few seconds (normally in 10 seconds).
4. If the program fails to start or displays a white screen, please install the WebView2 Runtime.
5. API keys need to be configured on first run (optional).
6. Use the shortcut Ctrl+X or set a new shortcut to activate the game assistant feature.

## System Requirements

- Windows 10 or higher (recommended Windows 11)
- 64-bit system (64-bit system is recommended)
- Microsoft Edge WebView2 Runtime

## WebView2 Runtime Installation

### Windows 11 Users
✅ Your system is pre-installed with WebView2 Runtime, you can use it directly.

### Windows 10 Users  
⚠️ Need to install WebView2 Runtime:

**Method 1 (recommended)**: Run the automatic installation script
1. Enter the runtime folder
2. Double-click to run install_webview2.bat
3. Follow the prompts to complete the installation

**Method 2**: Manually download and install
1. Visit: https://go.microsoft.com/fwlink/p/?LinkId=2124703
2. Download and install WebView2 Runtime
3. Restart the application

## Notes

- This program is a standalone portable version, no installation required (except for WebView2 Runtime)
- Configuration files will be saved in the system's AppData directory
- For full AI functionality, please configure Gemini and Jina API keys
- The first installation of WebView2 Runtime requires downloading about 100MB, but only needs to be installed once

## Troubleshooting

### Problem: The program fails to start or displays a white screen
**Solution**: Install WebView2 Runtime (see installation instructions above)

### Problem: Video playback fails
**Solution**: Confirm that WebView2 Runtime is correctly installed and restart the program

### Problem: Temporary files accumulation
**Note**: When the program exits abnormally or crashes, temporary files may remain in the system temp directory:
- Location: %TEMP%\_MEI****** (such as: AppData\Local\Temp\_MEI260882\)
- These folders are safe to delete and won't affect system operation
- PyInstaller automatically cleans up these folders on normal program exit
- You can manually delete these folders periodically to free up disk space

## Support

If you have any problems, please visit the project page for help.
