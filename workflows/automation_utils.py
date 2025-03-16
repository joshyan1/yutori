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
        text = img.get('alt')
        if src:
            asset_url, file_path = download_asset(src, base_url, page_assets_dir, 'img')
            if file_path:
                page.assets.imgs.append(Asset(url=file_path, asset_type='img', text=text))
    
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

# Function to detect and truncate grid-like elements
def truncate_repeated_elements(soup, max_items=5, max_carousels=2, max_menu_sections=3):
    """
    Detects and truncates grid-like or repeated elements in the HTML.
    Returns the number of elements truncated.
    
    Parameters:
    - soup: BeautifulSoup object
    - max_items: Maximum number of items to keep in each grid/list (default: 5)
    - max_carousels: Maximum number of carousel sections to keep (default: 2)
    - max_menu_sections: Maximum number of menu sections to keep (default: 3)
    """
    try:
        
        truncated_count = 0
        carousel_count = 0
        
        # Remove menu sections in store pages
        parent_div = soup.find("div", {"data-testid": "store-desktop-loaded-coi"})
        if parent_div:
            list_items = parent_div.find_all("li")

            print(f"Found {len(list_items)} list items inside store-desktop-loaded-coi")

            # Keep only the first three, remove the rest
            for li in list_items[3:]:  # Skip first 3, remove the rest
                li.decompose()  # Removes the tag from the tree

        
        # Uber Eats specific menu section selectors
        menu_section_selectors = [
            "div[role='tabpanel']",
            "div[data-baseweb='tab-panel']",
            "section.store-info-card",
            "div.hasMenuItem",
            "div.menu-section",
            "div.menu-category",
            "div[id^='tabs-desktop-ofd-menu-tabpanel']",
            "button[id^='tabs-desktop-ofd-menu-tab']",
            "li.jt.q7",  # Common Uber Eats menu section pattern
            "li.jt"      # Shorter version of the above
        ]
        
        # First, preserve menu sections and their items
        # Find all menu sections
        all_menu_sections = []
        
        """ # Find tab panels (main menu sections in Uber Eats)
        tab_panels = soup.select("div[id^='tabs-desktop-ofd-menu-tabpanel']") or soup.select("div[data-baseweb='tab-panel']")
        if tab_panels:
            all_menu_sections.extend(tab_panels)
            print(f"Found {len(tab_panels)} tab panels") """
        
        """ # Find menu sections structured as list items (common in Uber Eats)
        section_items = soup.select("li.jt.q7") or soup.select("li.jt")
        if section_items:
            all_menu_sections.extend(section_items)
            print(f"Found {len(section_items)} menu section items")
        
        # If we have more menu sections than allowed, keep only the first max_menu_sections
        if len(all_menu_sections) > max_menu_sections:
            print(f"Truncating menu sections from {len(all_menu_sections)} to {max_menu_sections}")
            # Keep the first max_menu_sections sections
            sections_to_remove = all_menu_sections[max_menu_sections:]
            for section in sections_to_remove:
                try:
                    section.decompose()
                except Exception as e:
                    print(f"Error removing menu section: {e}")
            truncated_count += 1 """
        
        # Now handle the menu tabs (buttons that control the sections)
        try:
            menu_tabs = soup.select("button[id^='tabs-desktop-ofd-menu-tab']")
            if menu_tabs and len(menu_tabs) > max_menu_sections:
                print(f"Truncating menu tabs from {len(menu_tabs)} to {max_menu_sections}")
                for tab in menu_tabs[max_menu_sections:]:
                    try:
                        # Also remove the corresponding panel
                        panel_id = tab.get('aria-controls')
                        if panel_id:
                            panel = soup.find(id=panel_id)
                            if panel:
                                panel.decompose()
                        tab.decompose()
                    except Exception as e:
                        print(f"Error while truncating menu tab: {e}")
                truncated_count += 1
        except Exception as e:
            print(f"Error processing menu tabs: {e}")
        
        # For each remaining menu section, ensure it has menu items
        # Find all menu sections again after truncation
        remaining_menu_sections = []
        
        # Find tab panels again after truncation
        tab_panels = soup.select("div[id^='tabs-desktop-ofd-menu-tabpanel']") or soup.select("div[data-baseweb='tab-panel']")
        if tab_panels:
            remaining_menu_sections.extend(tab_panels)
        
        """ # Find menu section items again after truncation
        section_items = soup.select("li.jt.q7") or soup.select("li.jt")
        if section_items:
            remaining_menu_sections.extend(section_items) """
        
        """ # Process each remaining menu section to ensure it has items
        for section in remaining_menu_sections:
            try:
                # Find menu items within this section
                # Try different selectors for menu items
                menu_items = []
                
                # Uber Eats specific menu item selectors
                item_selectors = [
                    "li.np.nq.nr.ak.ns",  # Common menu item pattern
                    "li.np.nq.nr.qg.ak.bb.i7.gn",  # Another common pattern (from your example)
                    "li[data-testid^='store-item']",  # Store items by testid
                    "li[class*='np'][class*='nq'][class*='nr']",  # Partial class match
                    "div[data-testid^='store-item']",  # Store items
                    "a[href*='mod=quickView']",  # Quick view items
                    "div.cd.al.nt.ak",  # Another common pattern
                    "li[data-testid='carousel-slide']",  # Carousel items
                    "div.MenuItem",  # Generic menu item
                    "div.menu-item",  # Generic menu item
                ]
                
                # Try each selector
                for selector in item_selectors:
                    items = section.select(selector)
                    if items:
                        menu_items.extend(items)
                        print(f"Found {len(items)} menu items with selector '{selector}' in section")
                
                # Special handling for the structure in your example
                # Look for ul elements that contain menu items
                if not menu_items:
                    ul_elements = section.select("ul.k8.qb.qc.nl.nm.nn.no.qe.qf") or section.select("ul[class*='k8'][class*='qb']")
                    for ul in ul_elements:
                        items = ul.find_all("li", class_=lambda c: c and "np" in c and "nq" in c and "nr" in c)
                        if items:
                            menu_items.extend(items)
                            print(f"Found {len(items)} menu items in ul element")
                
                # If no items found with specific selectors, try more generic approaches
                if not menu_items:
                    # Look for list items that might be menu items
                    list_items = section.find_all("li")
                    if list_items and len(list_items) > 3:  # If we have several list items, they're likely menu items
                        menu_items.extend(list_items)
                        print(f"Found {len(list_items)} list items that might be menu items")
                
                # If still no items, look for divs with similar structure
                if not menu_items:
                    # Find potential grid-like structures
                    for tag in ["div", "ul"]:
                        containers = section.find_all(tag)
                        for container in containers:
                            children = container.find_all(["div", "li", "a"], recursive=False)
                            if len(children) >= 3:  # If container has several children, they might be menu items
                                menu_items.extend(children)
                                print(f"Found {len(children)} potential menu items in a {tag}")
                                break  # Only use the first container with enough children
                
                # If we found menu items and there are more than max_items, truncate
                if menu_items and len(menu_items) > max_items:
                    print(f"Truncating menu items in section from {len(menu_items)} to {max_items}")
                    # Keep only the first max_items
                    for item in menu_items[max_items:]:
                        try:
                            if not item.decomposed:
                                item.decompose()
                        except Exception as e:
                            print(f"Error removing menu item: {e}")
                    truncated_count += 1
                elif menu_items:
                    print(f"Section has {len(menu_items)} menu items, no truncation needed")
                else:
                    print("No menu items found in this section")
            
            except Exception as e:
                print(f"Error processing menu section: {e}") """
        
        # Now handle other repeated elements
        
        # Common selectors for carousels, grids, and repeated elements
        grid_selectors = [
            # Uber Eats specific menu item selectors
            "ul.k8.nj.nk.nl.nm.nn.no.ae",
            "ul.k8.qb.qc.nl.nm.nn.no.qe.qf",  # Menu items container from your example
            "li.np.nq.nr.ak.ns",
            "li.np.nq.nr.qg.ak.bb.i7.gn",  # From your example
            #"div[data-testid^='store-item']",
            #"a[href*='mod=quickView']",
            "div.cd.al.nt.ak",
            
            # Carousels
            "ul.f4.cs.bh.nq.gn.nr",  
            "ul.f9.ak.gn.ns",        
            "ul[data-testid='carousel']",
            "div.carousel",
            "div.slider",
            "ul.carousel-items",
            "div[data-testid='carousel-slide']",
            "ul.f4.cs.bh.no.gl.np",
            "ul.al.f4.cs.bh.no.gl.np",
            "ul.al.f4.cs.bh.np.gn.nq",
            "ul.dv.er.c9.cd.ng.c4.nh.ni.mi.af",
            
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
            
            # Store/restaurant card grids
            "div[data-testid='store-card']",
            "div.m9.p0.p1[data-testid='store-card']",
            "div.store-list",
            "div.restaurants-list",
            "li[data-testid='carousel-slide']",
            "div.l7.al.l9.la.nn",
            
            # Uber Eats specific patterns
            "div.f4.f8.bs.m0.ly",
            "li.f9.ak.gn.nr",
            "div.ak.bu",
            "ol.ak.al.bh.ly.m0.mr",
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
                        try:
                            if not item.decomposed:
                                item.decompose()
                        except Exception as e:
                            print(f"Error removing grid item: {e}")
                    truncated_count += 1
        
        # Handle the specific Uber Eats menu item pattern
        menu_items = soup.select("li.np.nq.nr.qg.ak.bb.i7.gn") or soup.select("li.np.nq.nr.ak.ns")
        if menu_items and len(menu_items) > max_items:
            print(f"Truncating menu items from {len(menu_items)} to {max_items} items")
            # Find the parent container
            if menu_items[0].parent:
                parent_container = menu_items[0].parent
                # Remove excess items
                for item in menu_items[max_items:]:
                    try:
                        if not item.decomposed:
                            item.decompose()
                    except Exception as e:
                        print(f"Error removing menu item: {e}")
                truncated_count += 1
        
        # Special handling for carousel sections
        carousel_sections = []
        
        # Find all section elements that might be carousels
        for section in soup.find_all("section"):
            if carousel_count >= max_carousels:
                break
            
            # Look for carousel indicators like navigation buttons or carousel slides
            carousel_indicators = section.select("button[data-testid='next-arrow-carousel']") or section.select("li[data-testid='carousel-slide']")
            if carousel_indicators:
                # Find all carousel slide lists (ul elements with carousel slides)
                slide_lists = section.select("ul:has(li[data-testid='carousel-slide'])") or section.select("ul.k8.nj.nk.nl.nm.nn.no.ae")
                if slide_lists and len(slide_lists) > max_items:  # If there are more than max_items carousel sections
                    carousel_sections.append((section, slide_lists))
                    carousel_count += 1
                    print(f"Found carousel section with {len(slide_lists)} lists")
        
        # Truncate carousel sections to show only the first max_items
        for section, slide_lists in carousel_sections:
            if len(slide_lists) > max_items:
                print(f"Truncating carousel section from {len(slide_lists)} lists to {max_items} lists")
                # Remove all slide lists after the first max_items
                for slide_list in slide_lists[max_items:]:
                    try:
                        if not slide_list.decomposed:
                            slide_list.decompose()
                    except Exception as e:
                        print(f"Error removing slide list: {e}")
                truncated_count += 1
        
        # Handle multiple carousel sections in a page
        all_carousel_sections = soup.find_all("section")
        if len(all_carousel_sections) > max_carousels:
            print(f"Found {len(all_carousel_sections)} carousel sections, truncating to {max_carousels}")
            for section in all_carousel_sections[max_carousels:]:
                try:
                    if not section.decomposed:
                        section.decompose()
                except Exception as e:
                    print(f"Error removing carousel section: {e}")
            truncated_count += 1
        
        # Look for any collection of elements with the same data-testid attribute
        data_testid_values = {}
        try:
            for element in soup.find_all(attrs={"data-testid": True}):
                try:
                    testid = element.get("data-testid")
                    if testid and testid not in data_testid_values:
                        data_testid_values[testid] = []
                    if testid:
                        data_testid_values[testid].append(element)
                except Exception as e:
                    print(f"Error processing data-testid element: {e}")
            
            # Check if any data-testid group has more than max_items
            for testid, elements in data_testid_values.items():
                if elements and len(elements) > max_items and testid not in ["carousel", "carousel-slide", "rich-text"]:  # Avoid duplicating carousel handling
                    print(f"Truncating elements with data-testid='{testid}' from {len(elements)} to {max_items}")
                    # Remove excess elements
                    for element in elements[max_items:]:
                        try:
                            if element and not element.decomposed:
                                element.decompose()
                        except Exception as e:
                            print(f"Error removing data-testid element: {e}")
                    truncated_count += 1
        except Exception as e:
            print(f"Error processing data-testid values: {e}")
        
        # Handle repeated UL elements that contain carousel slides
        carousel_ul_containers = []
        for container in soup.select("div.l7.al.l9.la.nn") or soup.select("div.av.nb.nc.hn.nd.al.ne.nf"):
            try:
                carousel_uls = container.select("ul.al.f4.cs.bh.no.gl.np") or container.select("ul.k8.nj.nk.nl.nm.nn.no.ae")
                if carousel_uls and len(carousel_uls) > max_items:
                    carousel_ul_containers.append((container, carousel_uls))
            except Exception as e:
                print(f"Error processing carousel UL container: {e}")
        
        for container, uls in carousel_ul_containers:
            if len(uls) > max_items:
                print(f"Truncating carousel UL container from {len(uls)} ULs to {max_items}")
                for ul in uls[max_items:]:
                    try:
                        if not ul.decomposed:
                            ul.decompose()
                    except Exception as e:
                        print(f"Error removing carousel UL: {e}")
                truncated_count += 1
        
        # Handle empty placeholder elements
        empty_li_elements = soup.select("li[style='position: relative; max-width: 95px;']:empty")
        if empty_li_elements and len(empty_li_elements) > 2:  # Keep fewer for layout purposes
            print(f"Removing {len(empty_li_elements) - 2} empty placeholder elements")
            for li in empty_li_elements[2:]:
                try:
                    if not li.decomposed:
                        li.decompose()
                except Exception as e:
                    print(f"Error removing empty placeholder: {e}")
            truncated_count += 1
        
        # Handle promotional banners/cards
        promo_cards = soup.select("a.ea.bh.bu.af.mu.iv.dk.mv") or soup.select("a[href*='mod=quickView']")
        if promo_cards and len(promo_cards) > max_items:
            print(f"Truncating promotional banners from {len(promo_cards)} to {max_items}")
            for card in promo_cards[max_items:]:
                try:
                    if not card.decomposed:
                        card.decompose()
                except Exception as e:
                    print(f"Error removing promo card: {e}")
            truncated_count += 1
        
        # Handle preload link tags
        preload_links = soup.select("link[rel='preload']")
        if preload_links and len(preload_links) > 5:  # Keep fewer essential preloads
            print(f"Truncating preload links from {len(preload_links)} to 5")
            for link in preload_links[5:]:
                try:
                    if not link.decomposed:
                        link.decompose()
                except Exception as e:
                    print(f"Error removing preload link: {e}")
            truncated_count += 1
        
        # Handle script tags with similar sources
        script_srcs = {}
        for script in soup.find_all("script", src=True):
            try:
                src_pattern = script['src'].split('/')[-1].split('-')[0]  # Group by filename pattern
                if src_pattern not in script_srcs:
                    script_srcs[src_pattern] = []
                script_srcs[src_pattern].append(script)
            except Exception as e:
                print(f"Error processing script: {e}")
        
        # Keep only a few scripts from each pattern group
        for pattern, scripts in script_srcs.items():
            if len(scripts) > 2:  # Keep fewer scripts from each pattern
                print(f"Truncating script tags with pattern '{pattern}' from {len(scripts)} to 2")
                for script in scripts[2:]:
                    try:
                        if not script.decomposed:
                            script.decompose()
                    except Exception as e:
                        print(f"Error removing script: {e}")
                    truncated_count += 1
        
        # Detect grid-like structures by looking for patterns
        potential_grids = []
        
        # Find elements that have many similar direct children
        for tag in ["div", "ul", "section"]:
            for element in soup.find_all(tag):
                try:
                    # Skip elements that are too deep in the DOM
                    if len(list(element.parents)) > 10:
                        continue
                    
                    # Get direct children
                    children = element.find_all(["div", "li", "article"], recursive=False)
                    
                    # If there are enough children, check if they're similar
                    if len(children) >= max_items + 1:  # At least one more than our max
                        # Check if children have similar structure (class names or tag structure)
                        class_sets = [set(child.get('class', [])) for child in children if child.get('class')]
                        
                        # If at least 70% of children have classes and they share some common classes
                        if class_sets and len(class_sets) >= 0.7 * len(children):
                            # Find common classes across children
                            common_classes = set.intersection(*class_sets) if class_sets else set()
                            
                            # If there are common classes or all children have the same tag
                            if common_classes or all(child.name == children[0].name for child in children):
                                potential_grids.append((element, children))
                except Exception as e:
                    print(f"Error detecting grid-like structure: {e}")
        
        # Truncate detected potential grids
        for element, children in potential_grids:
            if len(children) > max_items:
                print(f"Detected and truncating grid-like element from {len(children)} to {max_items} items")
                # Remove all items after max_items
                for child in children[max_items:]:
                    try:
                        if not child.decomposed:
                            child.decompose()
                    except Exception as e:
                        print(f"Error removing grid child: {e}")
                truncated_count += 1
        
        # Handle repeated elements with similar structure but different parent tags
        repeated_elements_by_structure = {}
        
        # Find elements with similar structure based on their tag and class attributes
        for tag in ["li", "div", "article", "a"]:
            elements = soup.find_all(tag)
            for element in elements:
                try:
                    # Create a key based on tag name and classes
                    classes = element.get('class', [])
                    if classes:
                        key = f"{tag}:{'.'.join(sorted(classes))}"
                        if key not in repeated_elements_by_structure:
                            repeated_elements_by_structure[key] = []
                        repeated_elements_by_structure[key].append(element)
                except Exception as e:
                    print(f"Error processing repeated element: {e}")
        
        # Check for groups of similar elements that exceed our threshold
        for key, elements in repeated_elements_by_structure.items():
            if len(elements) > max_items:
                try:
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
                                try:
                                    if not element.decomposed:
                                        element.decompose()
                                except Exception as e:
                                    print(f"Error removing repeated element: {e}")
                            truncated_count += 1
                            break
                except Exception as e:
                    print(f"Error processing repeated elements group: {e}")
        
        # Final fallback: Look for any parent with many similar children based on HTML structure
        for tag in ["div", "section", "main", "ul"]:
            for element in soup.find_all(tag):
                try:
                    # Skip if we've already processed this element
                    if element.decomposed or element in [grid[0] for grid in potential_grids]:
                        continue
                    
                    # Get all children with the same tag
                    for child_tag in ["div", "li", "article", "a"]:
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
                                    try:
                                        if not child.decomposed:
                                            child.decompose()
                                    except Exception as e:
                                        print(f"Error removing similar HTML structure element: {e}")
                                    truncated_count += 1
                                break  # Only process one child tag per parent
                except Exception as e:
                    print(f"Error processing parent with similar children: {e}")
        
        # Specific handling for Uber Eats menu tabs
        try:
            menu_tabs_container = soup.select_one("div[aria-orientation='horizontal'][role='tablist']")
            if menu_tabs_container:
                menu_tabs = menu_tabs_container.find_all("button", role="tab")
                if menu_tabs and len(menu_tabs) > max_menu_sections:
                    print(f"Truncating menu tabs from {len(menu_tabs)} to {max_menu_sections}")
                    for tab in menu_tabs[max_menu_sections:]:
                        try:
                            if tab and not tab.decomposed:
                                tab.decompose()
                        except Exception as e:
                            print(f"Error removing menu tab: {e}")
                    truncated_count += 1
        except Exception as e:
            print(f"Error processing menu tabs container: {e}")
        
        # Add a note about truncation if we truncated anything
        if truncated_count > 0:
            try:
                truncation_note = soup.new_tag("div")
                truncation_note["style"] = "padding: 10px; background-color: #f8f9fa; margin: 10px 0; border-radius: 4px;"
                truncation_note.string = f"Note: This page has been truncated to show only essential content. {truncated_count} sections were simplified."
                
                # Try to insert at the beginning of the body or as first child of a main container
                body = soup.find("body")
                if body:
                    body.insert(0, truncation_note)
                else:
                    main_container = soup.find("div", class_="gh") or soup.find("main") or soup.find("div", id="main-content")
                    if main_container:
                        main_container.insert(0, truncation_note)
            except Exception as e:
                print(f"Error adding truncation note: {e}")
        
        return truncated_count
    except Exception as e:
        print(f"Error in truncate_repeated_elements: {e}")
        return 0