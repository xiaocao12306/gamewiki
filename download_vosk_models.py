#!/usr/bin/env python
"""Download Vosk models for voice recognition."""

import os
import sys
import requests
import zipfile
from pathlib import Path

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("Warning: tqdm not installed. Progress bars will not be shown.")
    print("Install with: pip install tqdm")

def download_file(url, dest_path):
    """Download file with progress bar."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest_path, 'wb') as f:
        if TQDM_AVAILABLE:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=dest_path.name) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
        else:
            # Simple progress without tqdm
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    print(f"\rDownloading {dest_path.name}: {percent:.1f}%", end='', flush=True)
            print()  # New line after download

def main():
    models = {
        'vosk-model-small-cn-0.22': {
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',
            'desc': 'Chinese voice model (42 MB)'
        },
        'vosk-model-small-en-us-0.15': {
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
            'desc': 'English voice model (40 MB)'
        }
    }
    
    # Target directory
    models_dir = Path("src/game_wiki_tooltip/assets/vosk_models")
    models_dir.mkdir(parents=True, exist_ok=True)
    
    print("=== Vosk Voice Recognition Model Downloader ===")
    print("This will download voice recognition models for GameWiki Assistant")
    print("Total download size: ~80 MB\n")
    
    success_count = 0
    
    for model_name, info in models.items():
        model_path = models_dir / model_name
        
        if model_path.exists():
            print(f"✓ {model_name} already exists, skipping...")
            success_count += 1
            continue
            
        print(f"\nDownloading {info['desc']}...")
        print(f"URL: {info['url']}")
        
        zip_path = models_dir / f"{model_name}.zip"
        
        try:
            # Download
            download_file(info['url'], zip_path)
            
            # Extract
            print(f"Extracting {model_name}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract to models_dir, the zip should contain the model folder
                zip_ref.extractall(models_dir)
            
            # Clean up zip file
            zip_path.unlink()
            
            print(f"✓ {model_name} installed successfully!")
            success_count += 1
            
        except KeyboardInterrupt:
            print("\n\nDownload cancelled by user.")
            if zip_path.exists():
                zip_path.unlink()
            sys.exit(1)
            
        except Exception as e:
            print(f"✗ Error installing {model_name}: {e}")
            if zip_path.exists():
                zip_path.unlink()
    
    print("\n" + "="*50)
    if success_count == len(models):
        print("✅ All models downloaded successfully!")
        print("Voice recognition is now ready to use.")
    else:
        print(f"⚠️  {success_count}/{len(models)} models installed.")
        print("Some models failed to download. Voice recognition may not work for all languages.")
    
    print("\nModels location:", models_dir.absolute())

if __name__ == "__main__":
    main()