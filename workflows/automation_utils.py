from bs4 import BeautifulSoup
from data_models import Asset
import os
import requests
import mimetypes
from urllib.parse import urlparse, urljoin
import hashlib
import re

def extract_assets_from_html(html_content, page_url, page):
    """
    Uses the page's HTML and URL to update the assets object
    of the page.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    base_url = '/'.join(page_url.split('/')[:3])
    
    # Directory to save assets
    page_assets_dir = os.path.join("assets", page.dir)
    os.makedirs(page_assets_dir, exist_ok=True)
    
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            asset_url, file_path = download_asset(src, base_url, page_assets_dir, 'img')
            if file_path:
                page.assets.imgs.append(Asset(url=file_path, asset_type='img'))
    
    for link in soup.find_all('link', rel='stylesheet'):
        href = link.get('href')
        if href:
            asset_url, file_path = download_asset(href, base_url, page_assets_dir, 'css')
            if file_path:
                page.assets.styling.append(Asset(url=file_path, asset_type='css'))
    
    for script in soup.find_all('script', src=True):
        src = script.get('src')
        if src:
            asset_url, file_path = download_asset(src, base_url, page_assets_dir, 'js')
            if file_path:
                page.assets.js.append(Asset(url=file_path, asset_type='js'))
    
    for link in soup.find_all('link', rel='icon'):
        href = link.get('href')
        if href:
            asset_url, file_path = download_asset(href, base_url, page_assets_dir, 'favicon')
            if file_path:
                page.assets.imgs.append(Asset(url=file_path, asset_type='favicon'))
    
    for element in soup.find_all(style=True):
        style = element['style']
        urls = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', style)
        for url in urls:
            asset_url, file_path = download_asset(url, base_url, page_assets_dir, 'bg-img')
            if file_path:
                page.assets.imgs.append(Asset(url=file_path, asset_type='bg-img'))
                
    return page


def download_asset(asset_url, base_url, save_dir, asset_type):
    try:
        original_url = asset_url  
        if asset_url.startswith('//'):
            asset_url = 'https:' + asset_url
        elif not (asset_url.startswith('http://') or asset_url.startswith('https://')):
            asset_url = urljoin(base_url, asset_url)

        # Download the asset (to inspect headers for content-type, etc.)
        response = requests.get(asset_url, timeout=10)
        if response.status_code != 200:
            # print(f"Skipping {asset_url} because of status code {response.status_code}")
            return None, None

        # Retrieve the content type
        content_type = response.headers.get("content-type", "").lower()
        guessed_ext = None
        if content_type:
            guessed_ext = mimetypes.guess_extension(content_type, strict=False)

        # Extract a filename portion from the URL (excluding query params)
        parsed_url = urlparse(asset_url)
        basename = os.path.basename(parsed_url.path)

        # If the URL does not have a valid extension, try the content-type guess
        _, ext_in_url = os.path.splitext(basename)
        # If the ext_in_url is something like '.jpg', keep it
        # but if it's missing or not an actual image extension, try the guessed_ext
        valid_image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico'}
        if not ext_in_url.lower() in valid_image_exts:
            ext_in_url = guessed_ext or ext_in_url  # fallback to guessed_ext
            if not ext_in_url:
                # If we still don't have anything, fallback to .png or use your function:
                ext_in_url = get_extension_from_asset_type(asset_type)

        url_hash = hashlib.md5(asset_url.encode('utf-8')).hexdigest()
        final_ext = ext_in_url if ext_in_url.startswith('.') else f".{ext_in_url}"
        filename = f"{asset_type}_{url_hash}{final_ext}"
        
        file_path = os.path.join(save_dir, filename)

        # Skip if file already exists
        if os.path.exists(file_path):
            #print(f"File already exists: {file_path}")
            return original_url, file_path

        with open(file_path, 'wb') as f:
            f.write(response.content)
        #print(f"Downloaded {asset_type}: {filename}")

        return original_url, file_path

    except Exception as e:
        print(f"Error downloading {asset_type} from {asset_url}: {e}")
        return None, None

def get_extension_from_asset_type(asset_type):
    extensions = {
        'img': '.jpg',
        'css': '.css',
        'js': '.js',
        'favicon': '.ico',
        'bg-img': '.png'
    }
    return extensions.get(asset_type, '')