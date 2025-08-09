import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

try:
    from PIL import ImageGrab
except ImportError:
    print("Error: Pillow library is not installed.")
    print("Please install it using: pip install Pillow")
    sys.exit(1)


class ScreenshotCapture:
    def __init__(self, save_directory: Optional[str] = None, interval: int = 3):
        self.project_root = Path(__file__).parent.parent.parent
        
        if save_directory:
            self.save_directory = Path(save_directory)
        else:
            self.save_directory = self.project_root / "data" / "screenshot"
        
        self.interval = interval
        self.is_running = False
        self.screenshot_count = 0
        
        self._ensure_directory_exists()
    
    def _ensure_directory_exists(self):
        self.save_directory.mkdir(parents=True, exist_ok=True)
        print(f"Screenshot directory: {self.save_directory}")
    
    def _generate_filename(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"screenshot_{timestamp}.jpg"
    
    def capture_screenshot(self) -> bool:
        try:
            screenshot = ImageGrab.grab()
            
            filename = self._generate_filename()
            filepath = self.save_directory / filename
            
            # Convert RGBA to RGB if necessary (JPEG doesn't support transparency)
            if screenshot.mode == 'RGBA':
                rgb_image = screenshot.convert('RGB')
            else:
                rgb_image = screenshot
            
            # Save as JPEG with quality 75 (balance between quality and file size)
            rgb_image.save(filepath, "JPEG", quality=75, optimize=True)
            self.screenshot_count += 1
            
            file_size = filepath.stat().st_size / 1024
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Screenshot saved: {filename} ({file_size:.1f} KB)")
            
            return True
            
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return False
    
    def start_capture(self):
        self.is_running = True
        print(f"Starting screenshot capture (interval: {self.interval} seconds)")
        print("Press Ctrl+C to stop...")
        print("-" * 50)
        
        try:
            while self.is_running:
                success = self.capture_screenshot()
                
                if not success:
                    print("Failed to capture screenshot, retrying...")
                
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.stop_capture()
    
    def stop_capture(self):
        self.is_running = False
        print("\n" + "-" * 50)
        print(f"Screenshot capture stopped.")
        print(f"Total screenshots captured: {self.screenshot_count}")
        print(f"Screenshots saved in: {self.save_directory}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Automated screenshot capture tool")
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Interval between screenshots in seconds (default: 3)"
    )
    parser.add_argument(
        "--directory",
        type=str,
        default=None,
        help="Directory to save screenshots (default: data/screenshot)"
    )
    parser.add_argument(
        "--cleanup",
        type=int,
        default=0,
        help="Keep only the last N screenshots (0 = no cleanup)"
    )
    
    args = parser.parse_args()
    
    capture = ScreenshotCapture(
        save_directory=args.directory,
        interval=args.interval
    )

    
    try:
        capture.start_capture()
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()