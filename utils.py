import re
from urllib.parse import urlparse, parse_qs
import time
import os

def get_sanitized_name_from_url(url: str) -> str:
    parsed_url = urlparse(url)

    # Extract domain parts, keeping www if present
    domain_parts = parsed_url.netloc.split('.')
    domain_name = domain_parts[0]
    
    # If domain starts with www, use the next part
    if domain_name == "www":
        domain_name = domain_parts[1]

    path_parts = [p for p in parsed_url.path.split('/') if p]
    
    # Create base name from domain and path
    base_parts = [domain_name] + path_parts
    base_name = '/'.join(base_parts)
    
    # Process query parameters
    if parsed_url.query:
        query_params = parse_qs(parsed_url.query)
        # Include all parameters that are less than 12 characters in length
        param_values = []
        for param, values in query_params.items():
            if len(param) < 12 and values and len(values[0]) < 12:
                param_values.append(f"{param}={values[0]}")
        
        if param_values:
            base_name += '/' + '_'.join(param_values)
    
    # Remove any special characters
    sanitized_name = re.sub(r'[^\w\-=/]', '', base_name)
    
    return sanitized_name

async def screenshot_page(playwright_page, page):
    try:
        # Use a shorter timeout to avoid hanging
        await playwright_page.wait_for_load_state('domcontentloaded', timeout=5000)
        screenshot_filename = f"initial_{time.strftime('%Y%m%d-%H%M%S')}.png"
        screenshot_path = os.path.join("assets", page.dir, screenshot_filename)
        await playwright_page.screenshot(path=screenshot_path)
        page.screenshot = screenshot_path
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        # Still set the screenshot path even if it fails, to avoid None references
        if not hasattr(page, 'screenshot') or page.screenshot is None:
            page.screenshot = os.path.join("assets", page.dir, "screenshot_failed.png")
