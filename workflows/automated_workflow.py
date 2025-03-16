from data_models import Site, Page
import os
from workflows.automation_utils import extract_assets_from_html
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import asyncio
import re
import json

# Function to detect and truncate grid-like elements
def truncate_repeated_elements(soup, max_items=12, max_carousels=2):
    """
    Detects and truncates grid-like or repeated elements in the HTML.
    Returns the number of elements truncated.
    """
    truncated_count = 0
    carousel_count = 0
    # Common selectors for carousels, grids, and repeated elements
    grid_selectors = [
        # Carousels
        "ul.f4.cs.bh.nq.gn.nr",  
        "ul.f9.ak.gn.ns",        
        "ul[data-testid='carousel']",
        "div.carousel",
        "div.slider",
        "ul.carousel-items",
        "div[data-testid='carousel-slide']",
        "ul.f4.cs.bh.no.gl.np",  # Added from example
        "ul.al.f4.cs.bh.no.gl.np",  # Added from example
        
        # Grids
        "div.grid",
        "div.grid-container",
        "ul.grid",
        "div.products-grid",
        "div.items-grid",
        "div.gallery",
        
        # Lists
        "ul.product-list",
        "div.product-list",
        "ul.items",
        "div.items-container",
        
        # Common e-commerce patterns
        "div.products",
        "ul.products",
        "div.search-results",
        "div.collection-products",
        
        # Store/restaurant card grids (from example)
        "div[data-testid='store-card']",
        "div.m9.p0.p1[data-testid='store-card']",
        "div.store-list",
        "div.restaurants-list",
        "li[data-testid='carousel-slide']",  # Added from example
        "div.l7.al.l9.la.nn"  # Added from example - container for carousel sections
    ]
    
    # First try with predefined selectors
    for selector in grid_selectors:
        elements = soup.select(selector)
        for element in elements:
            # Find direct children that could be grid items
            items = element.find_all(["li", "div", "article"], recursive=False)
            
            # If we have more than max_items, truncate
            if len(items) > max_items:
                print(f"Truncating element with selector '{selector}' from {len(items)} to {max_items} items")
                # Remove all items after max_items
                for item in items[max_items:]:
                    item.decompose()
                truncated_count += 1
    
    # Special handling for store cards pattern from the example
    # Look for parent containers that have multiple store-card children
    store_card_containers = []
    store_cards = soup.find_all("div", attrs={"data-testid": "store-card"})
    
    if store_cards and len(store_cards) > max_items:
        # Find common parent that contains these cards
        for card in store_cards[:5]:  # Check first few cards
            parents = list(card.parents)
            for parent in parents[:3]:  # Check first few levels of parents
                if parent.name == 'div':
                    # Count how many store cards this parent contains
                    child_cards = parent.find_all("div", attrs={"data-testid": "store-card"})
                    if len(child_cards) > max_items:
                        store_card_containers.append((parent, child_cards))
                        break
    
    # Truncate store card containers
    for container, cards in store_card_containers:
        if len(cards) > max_items:
            print(f"Truncating store card grid from {len(cards)} to {max_items} items")
            # Remove all cards after max_items
            for card in cards[max_items:]:
                card.decompose()
            truncated_count += 1
    
    # Handle the specific Uber Eats / food delivery pattern from the example
    # This pattern has div.m9.p0.p1[data-testid='store-card'] elements
    food_delivery_cards = soup.select("div.m9.p0.p1[data-testid='store-card']")
    if food_delivery_cards and len(food_delivery_cards) > max_items:
        print(f"Truncating food delivery store cards from {len(food_delivery_cards)} to {max_items} items")
        # Find the parent container
        if food_delivery_cards[0].parent:
            parent_container = food_delivery_cards[0].parent
            # Remove excess cards
            for card in food_delivery_cards[max_items:]:
                card.decompose()
            truncated_count += 1
    
    # Special handling for carousel sections (like in the example)
    carousel_sections = []
    
    # Find all section elements that might be carousels
    for section in soup.find_all("section"):
        if carousel_count >= max_carousels:
            break
            
        # Look for carousel indicators like navigation buttons or carousel slides
        carousel_indicators = section.select("button[data-testid='next-arrow-carousel']") or section.select("li[data-testid='carousel-slide']")
        if carousel_indicators:
            # Find all carousel slide lists (ul elements with carousel slides)
            slide_lists = section.select("ul:has(li[data-testid='carousel-slide'])")
            if slide_lists and len(slide_lists) > 3:  # If there are more than 3 carousel sections
                carousel_sections.append((section, slide_lists))
                carousel_count += 1
                print(f"Found carousel section with {len(slide_lists)} lists")
    
    # Truncate carousel sections to show only the first 3
    for section, slide_lists in carousel_sections:
        if len(slide_lists) > 3:
            print(f"Truncating carousel section from {len(slide_lists)} lists to 3 lists")
            # Remove all slide lists after the first 3
            for slide_list in slide_lists[3:]:
                slide_list.decompose()
            truncated_count += 1
    
    # Handle multiple carousel sections in a page (common in e-commerce sites)
    # This is for the pattern where there are multiple carousel sections, each with a heading and a set of items
    all_carousel_sections = soup.find_all("section")
    if len(all_carousel_sections) > max_carousels:
        print(f"Found {len(all_carousel_sections)} carousel sections, truncating to {max_carousels}")
        for section in all_carousel_sections[max_carousels:]:
            section.decompose()
        truncated_count += 1
    
    # Look for any collection of elements with the same data-testid attribute
    # This is a common pattern in modern web apps
    data_testid_values = {}
    for element in soup.find_all(attrs={"data-testid": True}):
        testid = element.get("data-testid")
        if testid not in data_testid_values:
            data_testid_values[testid] = []
        data_testid_values[testid].append(element)
    
    # Check if any data-testid group has more than max_items
    for testid, elements in data_testid_values.items():
        if len(elements) > max_items and testid not in ["carousel", "carousel-slide"]:  # Avoid duplicating carousel handling
            print(f"Truncating elements with data-testid='{testid}' from {len(elements)} to {max_items}")
            # Remove excess elements
            for element in elements[max_items:]:
                element.decompose()
            truncated_count += 1
    
    # Handle repeated UL elements that contain carousel slides
    # This is for the pattern in the example where multiple UL elements contain carousel slides
    carousel_ul_containers = []
    for container in soup.select("div.l7.al.l9.la.nn"):
        carousel_uls = container.select("ul.al.f4.cs.bh.no.gl.np")
        if carousel_uls and len(carousel_uls) > 3:
            carousel_ul_containers.append((container, carousel_uls))
    
    for container, uls in carousel_ul_containers:
        if len(uls) > 3:
            print(f"Truncating carousel UL container from {len(uls)} ULs to 3")
            for ul in uls[3:]:
                ul.decompose()
            truncated_count += 1
    
    # Next, try to detect grid-like structures by looking for patterns
    # Look for parent elements with many similar children
    potential_grids = []
    
    # Find elements that have many similar direct children (at least 8)
    for tag in ["div", "ul", "section"]:
        for element in soup.find_all(tag):
            # Skip elements that are too deep in the DOM (likely not main content)
            if len(list(element.parents)) > 10:
                continue
                
            # Get direct children
            children = element.find_all(["div", "li", "article"], recursive=False)
            
            # If there are enough children, check if they're similar
            if len(children) >= 8:
                # Check if children have similar structure (class names or tag structure)
                class_sets = [set(child.get('class', [])) for child in children if child.get('class')]
                
                # If at least 70% of children have classes and they share some common classes
                if class_sets and len(class_sets) >= 0.7 * len(children):
                    # Find common classes across children
                    common_classes = set.intersection(*class_sets) if class_sets else set()
                    
                    # If there are common classes or all children have the same tag
                    if common_classes or all(child.name == children[0].name for child in children):
                        potential_grids.append((element, children))
    
    # Truncate detected potential grids
    for element, children in potential_grids:
        if len(children) > max_items:
            print(f"Detected and truncating grid-like element from {len(children)} to {max_items} items")
            # Remove all items after max_items
            for child in children[max_items:]:
                child.decompose()
            truncated_count += 1
    
    # Handle repeated elements with similar structure but different parent tags
    # This is useful for catching patterns that don't match our predefined selectors
    repeated_elements_by_structure = {}
    
    # Find elements with similar structure based on their tag and class attributes
    for tag in ["li", "div", "article"]:
        elements = soup.find_all(tag)
        for element in elements:
            # Create a key based on tag name and classes
            classes = element.get('class', [])
            if classes:
                key = f"{tag}:{'.'.join(sorted(classes))}"
                if key not in repeated_elements_by_structure:
                    repeated_elements_by_structure[key] = []
                repeated_elements_by_structure[key].append(element)
    
    # Check for groups of similar elements that exceed our threshold
    for key, elements in repeated_elements_by_structure.items():
        if len(elements) > max_items:
            # Check if they share a common parent
            parents = [element.parent for element in elements]
            parent_counts = {}
            for parent in parents:
                if parent not in parent_counts:
                    parent_counts[parent] = 0
                parent_counts[parent] += 1
            
            # If most elements share the same parent, truncate them
            for parent, count in parent_counts.items():
                if count > max_items:
                    parent_elements = [e for e in elements if e.parent == parent]
                    print(f"Truncating repeated elements with structure '{key}' from {len(parent_elements)} to {max_items}")
                    for element in parent_elements[max_items:]:
                        element.decompose()
                    truncated_count += 1
                    break
    
    # Final fallback: Look for any parent with many similar children based on HTML structure
    # This is more aggressive but will catch more patterns
    for tag in ["div", "section", "main"]:
        for element in soup.find_all(tag):
            # Skip if we've already processed this element
            if element.decomposed or element in [grid[0] for grid in potential_grids]:
                continue
                
            # Get all children with the same tag
            for child_tag in ["div", "li", "article"]:
                children = element.find_all(child_tag, recursive=False)
                
                # If enough similar children, check if they look like a grid
                if len(children) > max_items:
                    # Check if they have similar HTML structure (length)
                    html_lengths = [len(str(child)) for child in children]
                    avg_length = sum(html_lengths) / len(html_lengths)
                    
                    # If the HTML lengths are similar (within 30% of average)
                    similar_count = sum(1 for length in html_lengths if 0.7 * avg_length <= length <= 1.3 * avg_length)
                    if similar_count >= 0.8 * len(children):
                        print(f"Truncating similar HTML structure elements from {len(children)} to {max_items}")
                        # Remove excess elements
                        for child in children[max_items:]:
                            child.decompose()
                        truncated_count += 1
                        break  # Only process one child tag per parent
    
    return truncated_count

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
            
            # Handle style tags
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
                        data_attrs_removed += 1
            
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