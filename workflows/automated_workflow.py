from data_models import Site, Page
import os
from workflows.automation_utils import extract_assets_from_html, truncate_repeated_elements
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import asyncio
import re
import json

async def automated_workflow(playwright_page, site):
    pages = list(site.get_pages())  # Convert to list to avoid modification during iteration
    
    for page in pages:
        try:
            url = page.url
            print(f"Processing page: {url}")

            # This assets directory is the same that we previously used in the manual workflow
            # to screenshots. This is where we want to save the assets for the page.
            assets_dir = os.path.join("assets", page.dir)
            os.makedirs(assets_dir, exist_ok=True)  # Ensure directory exists

            try:
                await playwright_page.goto(url, timeout=30000)
            except Exception as e:
                print(f"Error navigating to {url}: {e}")
                continue  # Skip this page and move to the next one
                
            try:
                # Set a shorter timeout for networkidle
                await playwright_page.wait_for_load_state("domcontentloaded", timeout=5000)
                # Try networkidle with a short timeout
                try:
                    await playwright_page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    print("Network didn't become idle, but continuing anyway")
            except Exception as e:
                print(f"Page load state error, but continuing: {e}")

            # Retrieve the HTML content
            try:
                html = await playwright_page.content()
            except Exception as e:
                print(f"Error getting page content: {e}")
                continue  # Skip this page if we can't get content
                
            soup = BeautifulSoup(html, "html.parser")

            scripts_removed = 0
            styles_removed = 0
            data_attrs_removed = 0
            json_scripts_removed = 0
            
            # Handle script tags
            scripts = soup.find_all("script")
            for script in scripts:
                # Special handling for JSON-containing scripts (common in modern web apps)
                script_id = script.get('id', '')
                script_type = script.get('type', '')
                
                # Check if it's a JSON data script (common patterns)
                is_json_script = (
                    script_type == 'application/json' or 
                    script_id and ('__DATA__' in script_id or '__TRANSLATIONS__' in script_id or 'state' in script_id.lower())
                )
                
                if is_json_script and script.string:
                    # For JSON scripts, we'll save them to separate files instead of keeping them inline
                    try:
                        # Try to parse and pretty-print the JSON to verify it's valid
                        json_content = json.loads(script.string)
                        script_filename = f"{script_id or 'json_data'}_{scripts_removed}.json"
                        script_path = os.path.join(assets_dir, script_filename)
                        
                        # Save the JSON to a separate file
                        with open(script_path, 'w', encoding='utf-8') as f:
                            json.dump(json_content, f, indent=2)
                            
                        # Replace with a reference to the saved file
                        placeholder = soup.new_tag("script")
                        placeholder['type'] = script_type
                        placeholder['id'] = script_id
                        placeholder.string = f"/* JSON data saved to {script_filename} */"
                        script.replace_with(placeholder)
                        json_scripts_removed += 1
                        continue
                    except json.JSONDecodeError:
                        # Not valid JSON, handle as regular script
                        pass
                
                # Regular script handling
                if script.string and len(script.string) > 50000:
                    # Replace with a placeholder comment
                    placeholder = soup.new_tag("script")
                    if script.get('id'):
                        placeholder['id'] = script['id']
                    if script.get('type'):
                        placeholder['type'] = script['type']
                    placeholder.string = f"/* Large script removed ({len(script.string)} characters) */"
                    script.replace_with(placeholder)
                    scripts_removed += 1
            
            # Handle inline scripts (on* attributes)
            inline_script_attrs = [
                'onclick', 'onmouseover', 'onmouseout', 'onload', 'onerror', 
                'onchange', 'onsubmit', 'onkeydown', 'onkeyup', 'onkeypress'
            ]
            
            for attr in inline_script_attrs:
                elements_with_attr = soup.find_all(attrs={attr: True})
                for element in elements_with_attr:
                    if len(element[attr]) > 5000:  # Lower threshold for inline scripts
                        element[attr] = f"/* Large inline script removed ({len(element[attr])} characters) */"
                        scripts_removed += 1
            
            """ # Handle style tags
            styles = soup.find_all("style")
            for style in styles:
                if style.string and len(style.string) > 50000:
                    placeholder = soup.new_tag("style")
                    placeholder.string = f"/* Large style removed ({len(style.string)} characters) */"
                    style.replace_with(placeholder)
                    styles_removed += 1
            
            # Handle inline styles
            elements_with_style = soup.find_all(attrs={'style': True})
            for element in elements_with_style:
                if len(element['style']) > 5000:  # Lower threshold for inline styles
                    element['style'] = f"/* Large inline style removed ({len(element['style'])} characters) */"
                    styles_removed += 1
            
            # Handle data attributes (which can contain large JSON or other data)
            for element in soup.find_all():
                for attr_name in list(element.attrs.keys()):
                    if attr_name.startswith('data-') and isinstance(element[attr_name], str) and len(element[attr_name]) > 100000:
                        element[attr_name] = f"[Large data attribute removed ({len(element[attr_name])} characters)]"
                        data_attrs_removed += 1 """
            
            if scripts_removed > 0 or styles_removed > 0 or data_attrs_removed > 0 or json_scripts_removed > 0:
                print(f"Removed {scripts_removed} large scripts, {styles_removed} large styles, {data_attrs_removed} large data attributes, and saved {json_scripts_removed} JSON scripts to separate files")

            # Truncate grid-like and repeated elements
            elements_truncated = truncate_repeated_elements(soup, max_items=12)
            if elements_truncated > 0:
                print(f"Truncated {elements_truncated} grid-like or repeated elements to 12 items each")
            else:
                print("No grid-like or repeated elements found to truncate")
            
            truncated_html = str(soup)
            
            html_file_path = os.path.join(assets_dir, "page.html")
            with open(html_file_path, "w", encoding="utf-8") as f:
                f.write(truncated_html)

            page.html = html_file_path

            current_parsed = urlparse(url)
            current_domain = current_parsed.netloc
            
            # Use BeautifulSoup to extract links from the truncated HTML
            soup_links = soup.find_all("a", href=True)
            for link in soup_links:
                try:
                    href = link.get("href")
                    text = link.get_text().strip()
                    
                    if not href:
                        continue
                        
                    # Fix URLs that start with //
                    if href.startswith("//"):
                        href = current_parsed.scheme + ":" + href
                    
                    # Handle absolute URLs
                    if href.startswith("http://") or href.startswith("https://"):
                        parsed_href = urlparse(href)
                        link_domain = parsed_href.netloc
                        
                        # Check if the domains match (ignoring subdomains)
                        current_main_domain = '.'.join(current_domain.split('.')[-2:]) if len(current_domain.split('.')) > 1 else current_domain
                        link_main_domain = '.'.join(link_domain.split('.')[-2:]) if len(link_domain.split('.')) > 1 else link_domain
                        
                        if link_main_domain != current_main_domain:
                            page.add_external_url(href, text)
                        else:
                            page.add_internal_url(href, text)
                    # Handle relative URLs
                    elif href == "/":
                        # Root path
                        base_url = f"{current_parsed.scheme}://{current_domain}"
                        page.add_internal_url(base_url, text)
                    elif href.startswith("/"):
                        # Relative path
                        base_url = f"{current_parsed.scheme}://{current_domain}"
                        page.add_internal_url(base_url + href, text)
                    else:
                        # Handle other relative URLs (without leading slash)
                        base_path = '/'.join(current_parsed.path.split('/')[:-1]) + '/'
                        if not base_path.startswith('/'):
                            base_path = '/' + base_path
                        base_url = f"{current_parsed.scheme}://{current_domain}{base_path}"
                        page.add_internal_url(base_url + href, text)
                except Exception as e:
                    print(f"Error processing link in HTML: {e}")

            try:
                page = extract_assets_from_html(truncated_html, url, page)
            except Exception as e:
                print(f"Error extracting assets: {e}")
                
            # Give the browser a short break between pages
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Error processing page {page.url}: {e}")
    
    return site