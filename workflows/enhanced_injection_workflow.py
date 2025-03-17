import os
import re
import json
import shutil
import dotenv
import anthropic
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from data_models import Page, Site, Interaction

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert web developer specializing in creating interactive websites.
Your task is to implement functionality for HTML elements without changing the overall structure or design.
Focus only on making interactive elements work properly with JavaScript."""

# Prompt for implementing functionality for clickable elements
FUNCTIONALITY_PROMPT = """I have an HTML page with various interactive elements (buttons, filters, dropdowns, etc.).
I need you to implement JavaScript functionality for these elements so they work as expected.

For each interactive element:
1. Identify its purpose based on its context, text, and attributes
2. Implement appropriate event listeners and functions
3. For elements that would normally trigger backend requests, create mock functions that simulate the expected behavior
4. Ensure all interactions have a visible effect on the page (e.g., filtering, showing/hiding elements, etc.)

Specific implementation requirements:
- For filter buttons/dropdowns: Implement filtering functionality that shows/hides elements based on the selected filter
- For search inputs: Implement search functionality that filters content based on the search term
- For tabs/accordions: Implement show/hide functionality for the associated content
- For forms: Implement form validation and submission handling with mock data responses
- For navigation menus: Ensure proper highlighting of active items

Return ONLY the JavaScript code to be injected into the page. Do not include any HTML or explanations.
Your code should be wrapped in a self-executing function to avoid global scope pollution.
"""

# Prompt for fixing individual links
LINK_FIX_PROMPT = """I need to update a link in an HTML page to point to the correct local file.

Original link: {original_link}
Original page URL: {page_url}
Link text: {link_text}

Available local HTML files:
{available_files}

URL mapping information:
{url_mapping}

If this link points to a page that exists in our local collection, return the correct local filename.
If it's an external link or points to a page we don't have locally, return the original link.
For relative links (starting with / or without http), try to match them to our local files.

Return ONLY the corrected link path with no explanation or additional text.
"""

def enhanced_injection_workflow(site: Site):
    """
    Creates a local clone of the site with enhanced functionality:
    1. Copies original HTML to a 'source_html' folder
    2. Identifies and implements functionality for interactive elements
    3. Rewrites links to connect pages properly
    4. Saves final pages to 'cloned_injection' folder
    """
    print("Starting enhanced injection workflow...")
    
    # Setup directories
    base_dir = os.getcwd()
    source_dir = os.path.join(base_dir, "cloned_injection", "source_html")
    functionality_dir = os.path.join(base_dir, "cloned_injection", "with_functionality")
    final_dir = os.path.join(base_dir, "cloned_injection", "final")
    
    # Create directories
    for directory in [source_dir, functionality_dir, final_dir]:
        os.makedirs(directory, exist_ok=True)
    
    # Initialize Anthropic client
    try:
        client = anthropic.Anthropic(
            api_key=dotenv.get_key(".env", "ANTHROPIC_API_KEY")
        )
    except Exception as e:
        print(f"Error initializing Anthropic client: {e}")
        return site
    
    # Get total number of pages for progress tracking
    pages = list(site.get_pages())
    total_pages = len(pages)
    
    if total_pages == 0:
        print("No pages found in the site. Exiting workflow.")
        return site
        
    print(f"Found {total_pages} pages to process.")
    
    # Step 1: Copy all HTML files to source_html directory
    print("\nStep 1: Copying HTML files to source directory...")
    file_mapping = copy_html_to_source_dir(site, source_dir)
    
    # Check if we have any files to process
    if not file_mapping:
        print("No HTML files were copied. Exiting workflow.")
        return site
    
    # Step 2: Implement functionality for each page
    print("\nStep 2: Implementing functionality for interactive elements...")
    functionality_success = 0
    
    for i, page in enumerate(pages, 1):
        print(f"\nProcessing page {i}/{total_pages}: {page.url}")
        try:
            source_file = file_mapping.get(page.url)
            if not source_file:
                print(f"  Warning: No source file found for {page.url}")
                continue
                
            implement_page_functionality(client, page, source_file, functionality_dir)
            functionality_success += 1
        except Exception as e:
            print(f"  Error implementing functionality for {page.url}: {e}")
    
    print(f"\nFunctionality implementation complete. Successfully processed {functionality_success}/{total_pages} pages.")
    
    # Step 3: Fix links between pages
    print("\nStep 3: Fixing links between pages...")
    available_files = os.listdir(functionality_dir)
    link_fixing_success = 0
    
    for i, page in enumerate(pages, 1):
        print(f"\nFixing links for page {i}/{total_pages}: {page.url}")
        try:
            page_filename = sanitize_filename(page.dir) + ".html"
            functionality_file = os.path.join(functionality_dir, page_filename)
            
            if not os.path.exists(functionality_file):
                print(f"  Warning: No functionality file found for {page.url}")
                continue
                
            fix_page_links(client, page, functionality_file, final_dir, available_files, site)
            link_fixing_success += 1
        except Exception as e:
            print(f"  Error fixing links for {page.url}: {e}")
            # Try to copy the file anyway to ensure we have something in the final directory
            try:
                page_filename = sanitize_filename(page.dir) + ".html"
                functionality_file = os.path.join(functionality_dir, page_filename)
                final_file = os.path.join(final_dir, page_filename)
                shutil.copy(functionality_file, final_file)
                print(f"  Copied file without link fixing: {page_filename}")
            except Exception as copy_error:
                print(f"  Error copying file: {copy_error}")
    
    print(f"\nLink fixing complete. Successfully processed {link_fixing_success}/{total_pages} pages.")
    
    # Final summary
    print("\n=== Enhanced Injection Workflow Summary ===")
    print(f"Total pages: {total_pages}")
    print(f"Pages with functionality: {functionality_success}")
    print(f"Pages with fixed links: {link_fixing_success}")
    print(f"Site clone complete! All pages processed in {final_dir}")
    
    return site

def initialize_html(client, page: Page, directory: str):
    """
    Uses Anthropic to generate a clean HTML version of the page.
    Only used for specific pages like feed pages.
    """
    page_name = page.dir
    # Sanitize page name for use in filenames
    safe_page_name = sanitize_filename(page_name)
    html_path = os.path.join(directory, "v1", f"{safe_page_name}.html")

    # Create debug directory if it doesn't exist
    debug_dir = os.path.join(directory, "debug")
    os.makedirs(debug_dir, exist_ok=True)

    # Read the HTML content from the file
    with open(page.html, 'r', encoding='utf-8') as f:
        page_html = f.read()
        
    # Create the streaming request
    with client.messages.stream(
        model="claude-3-7-sonnet-20250219",
        max_tokens=40000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Clone this website. Return only the code nested in ```html and ``` tags. Do not provide any textual explanation in your response. {page_html}"
                    }
                ]
            }
        ]
    ) as stream:
        # Initialize variables to collect the full response
        message = None
        full_response_text = ""
        
        # Process each event in the stream
        for event in stream:
            if event.type == "message_start":
                message = event.message
            elif event.type == "content_block_start":
                current_block = event.content_block
            elif event.type == "content_block_delta":
                if event.delta.text:
                    full_response_text += event.delta.text
            elif event.type == "message_delta":
                if hasattr(event.delta, "usage"):
                    message.usage = event.delta.usage
            elif event.type == "message_stop":
                # Stream is complete
                pass
                
    print("Response received")

    # Create a directory to save Anthropic API responses for testing/debugging
    anthropic_dir = os.path.join(os.getcwd(), "anthropic")
    os.makedirs(anthropic_dir, exist_ok=True)
    
    # Save the raw API response to a file for reference
    response_path = os.path.join(anthropic_dir, f"response_{safe_page_name}.json")
    with open(response_path, "w", encoding="utf-8") as f:
        # Create a serializable message dict
        message_dict = {
            "id": message.id,
            "content": [{"type": "text", "text": full_response_text}],
            "model": message.model,
            "role": message.role,
            "type": message.type
        }
        
        # Add usage information if available
        if hasattr(message, "usage"):
            message_dict["usage"] = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens
            }
            
        json.dump(message_dict, f, indent=2)

    try:
        # Use the collected full response text
        output = full_response_text
        
        # Check if the response contains HTML code blocks
        if "```html" in output and "```" in output.split("```html", 1)[1]:
            html = output.split("```html")[1].split("```")[0]
        else:
            # If no HTML code blocks found, save the raw response for debugging
            debug_path = os.path.join(debug_dir, f"{safe_page_name}_raw_response.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Warning: No HTML code blocks found in response for page {page.url}")
            # Use the raw output as HTML (may not be ideal but prevents failure)
            html = output
    except (IndexError, AttributeError) as e:
        print(f"Error extracting HTML from response for page {page.url}: {e}")
        # Save the raw message for debugging
        debug_path = os.path.join(debug_dir, f"{safe_page_name}_error.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(message_dict, f, indent=2)
        # Return empty HTML as fallback
        html = "<html><body><p>Error extracting HTML from response</p></body></html>"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path

def copy_html_to_source_dir(site: Site, source_dir: str) -> dict:
    """
    Copies all HTML files to the source directory with sanitized filenames.
    For feed pages, uses Anthropic to generate a clean HTML version.
    Returns a mapping of URLs to their corresponding source files.
    """
    file_mapping = {}
    
    # Create v1 directory for initialized HTML
    v1_dir = os.path.join(source_dir, "v1")
    os.makedirs(v1_dir, exist_ok=True)
    
    # Initialize Anthropic client for feed pages
    try:
        client = anthropic.Anthropic(
            api_key=dotenv.get_key(".env", "ANTHROPIC_API_KEY")
        )
    except Exception as e:
        print(f"Error initializing Anthropic client for feed pages: {e}")
        client = None
    
    for page in site.get_pages():
        if not page.html or not os.path.exists(page.html):
            print(f"Warning: No HTML file found for {page.url}")
            continue
            
        safe_filename = sanitize_filename(page.dir) + ".html"
        dest_path = os.path.join(source_dir, safe_filename)
        
        # Check if this is a feed page
        is_feed_page = "ubereats.com/feed" in page.url
        
        if is_feed_page and client:
            print(f"Initializing feed page: {page.url}")
            try:
                # Use Anthropic to generate a clean HTML version
                html_path = initialize_html(client, page, source_dir)
                file_mapping[page.url] = html_path
                print(f"Initialized feed page {page.url} to {html_path}")
            except Exception as e:
                print(f"Error initializing feed page {page.url}: {e}")
                # Fall back to regular copying
                copy_regular_html(page, dest_path, file_mapping)
        else:
            # Regular copying for non-feed pages
            copy_regular_html(page, dest_path, file_mapping)
    
    return file_mapping

def copy_regular_html(page: Page, dest_path: str, file_mapping: dict):
    """Helper function to copy regular HTML files."""
    try:
        with open(page.html, "r", encoding="utf-8") as f_src:
            html_content = f_src.read()
            
        with open(dest_path, "w", encoding="utf-8") as f_dest:
            f_dest.write(html_content)
            
        file_mapping[page.url] = dest_path
        print(f"Copied {page.url} to {dest_path}")
    except Exception as e:
        print(f"Error copying HTML for {page.url}: {e}")

def implement_page_functionality(client, page: Page, source_file: str, output_dir: str):
    """
    Identifies interactive elements in the page and implements functionality for them.
    Uses Anthropic to generate JavaScript code for the functionality.
    """
    page_filename = os.path.basename(source_file)
    output_file = os.path.join(output_dir, page_filename)
    
    # Read the HTML content
    with open(source_file, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # Parse the HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Find all potentially interactive elements
    interactive_elements = find_interactive_elements(soup)
    
    if not interactive_elements:
        print(f"No interactive elements found in {page.url}")
        # Just copy the file to the output directory
        shutil.copy(source_file, output_file)
        return
    
    # Group elements by type for better context
    element_groups = {
        "buttons": [],
        "links": [],
        "forms": [],
        "inputs": [],
        "selects": [],
        "filters": [],
        "tabs": [],
        "other": []
    }
    
    for el in interactive_elements:
        el_type = el.name.lower()
        el_class = " ".join(el.get("class", [])) if el.get("class") else ""
        
        if el_type == "button" or "button" in el_class:
            element_groups["buttons"].append(el)
        elif el_type == "a":
            element_groups["links"].append(el)
        elif el_type == "form":
            element_groups["forms"].append(el)
        elif el_type in ["input", "textarea"]:
            element_groups["inputs"].append(el)
        elif el_type == "select":
            element_groups["selects"].append(el)
        elif "filter" in el_class or "search" in el_class:
            element_groups["filters"].append(el)
        elif "tab" in el_class or "accordion" in el_class:
            element_groups["tabs"].append(el)
        else:
            element_groups["other"].append(el)
    
    # Prepare the prompt with information about the interactive elements by group
    elements_info = []
    
    for group_name, elements in element_groups.items():
        if not elements:
            continue
            
        elements_info.append(f"\n--- {group_name.upper()} ({len(elements)}) ---")
        
        for el in elements[:10]:  # Limit to 10 elements per group to avoid token limits
            elements_info.append(
                f"Element: {el.name} (id={el.get('id', 'None')}, class={el.get('class', 'None')})"
                f"\nText: {el.get_text().strip()[:100]}"
                f"\nAttributes: {str(el.attrs)[:200]}"
            )
            
        if len(elements) > 10:
            elements_info.append(f"... and {len(elements) - 10} more {group_name}")
    
    elements_info_str = "\n".join(elements_info)
    
    # Include information about recorded interactions if available
    interactions_info = ""
    if page.interactions:
        interactions_info = "Recorded interactions:\n" + page.synthesize_interactions()
    
    # Get the page title for context
    page_title = soup.title.string if soup.title else page.url
    
    # Prepare the full prompt
    full_prompt = f"""
{FUNCTIONALITY_PROMPT}

Page URL: {page.url}
Page Title: {page_title}

Interactive elements found:
{elements_info_str}

{interactions_info}

HTML structure (truncated):
{soup.prettify()[:5000]}
"""
    
    # Call Anthropic to generate JavaScript code
    try:
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=4000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": full_prompt
                }
            ]
        )
        
        js_code = response.content[0].text
        
        # Extract JavaScript code from code blocks if present
        if "```javascript" in js_code or "```js" in js_code:
            # Extract code from JavaScript code blocks
            import re
            js_blocks = re.findall(r'```(?:javascript|js)(.*?)```', js_code, re.DOTALL)
            if js_blocks:
                js_code = "\n\n".join(js_blocks)
        
        # Wrap the code in a self-executing function if it's not already
        if not js_code.strip().startswith("(function") and not js_code.strip().startswith("(() =>"):
            js_code = f"""
(function() {{
    // Auto-wrapped code
    {js_code}
    
    // Add DOMContentLoaded event to ensure the DOM is fully loaded
    document.addEventListener('DOMContentLoaded', function() {{
        console.log('DOM fully loaded and parsed with injected functionality');
    }});
}})();
"""
        
        # Inject the JavaScript code into the HTML
        inject_javascript(soup, js_code)
        
        # Write the updated HTML to the output file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(str(soup))
            
        print(f"Implemented functionality for {page.url}")
    except Exception as e:
        print(f"Error calling Anthropic for {page.url}: {e}")
        # In case of error, just copy the original file
        shutil.copy(source_file, output_file)

def find_interactive_elements(soup: BeautifulSoup) -> list:
    """
    Finds all potentially interactive elements in the HTML.
    """
    interactive_elements = []
    
    # Find all buttons
    buttons = soup.find_all("button") + soup.find_all(attrs={"type": "button"})
    interactive_elements.extend(buttons)
    
    # Find all links that might be interactive (e.g., have onclick attributes or specific classes)
    interactive_link_classes = ["btn", "button", "nav", "menu", "tab", "filter", "toggle", "dropdown", 
                               "accordion", "collapse", "expand", "modal", "popup", "dialog"]
    links = soup.find_all("a", attrs={"onclick": True}) + soup.find_all("a", class_=lambda c: c and any(cls in str(c).lower() for cls in interactive_link_classes))
    interactive_elements.extend(links)
    
    # Find all form elements
    forms = soup.find_all("form")
    interactive_elements.extend(forms)
    
    # Find all inputs, selects, and textareas
    inputs = soup.find_all(["input", "select", "textarea"])
    interactive_elements.extend(inputs)
    
    # Find elements with common interactive class names or attributes
    interactive_classes = ["clickable", "dropdown", "accordion", "toggle", "modal", "popup", "slider", 
                          "carousel", "tab", "filter", "sort", "pagination", "search", "checkbox", 
                          "radio", "switch", "menu", "submenu", "nav-item", "collapsible"]
    
    for cls in interactive_classes:
        elements = soup.find_all(class_=lambda c: c and cls.lower() in str(c).lower())
        interactive_elements.extend(elements)
    
    # Find elements with data attributes that suggest interactivity
    interactive_data_attrs = ["data-toggle", "data-target", "data-dismiss", "data-action", 
                             "data-slide", "data-filter", "data-sort", "data-role", "data-bind"]
    
    for attr in interactive_data_attrs:
        elements = soup.find_all(attrs={attr: True})
        interactive_elements.extend(elements)
    
    # Find elements with onclick, onchange, or other event attributes
    event_attrs = ["onclick", "onchange", "onsubmit", "onmouseover", "onmouseout", 
                  "onfocus", "onblur", "onkeyup", "onkeydown", "onload"]
    
    for attr in event_attrs:
        elements = soup.find_all(attrs={attr: True})
        interactive_elements.extend(elements)
    
    # Find elements with ARIA roles that suggest interactivity
    interactive_roles = ["button", "link", "checkbox", "radio", "tab", "tabpanel", 
                        "menu", "menuitem", "combobox", "slider", "switch"]
    
    for role in interactive_roles:
        elements = soup.find_all(attrs={"role": role})
        interactive_elements.extend(elements)
    
    # Remove duplicates while preserving order
    seen = set()
    return [el for el in interactive_elements if not (id(el) in seen or seen.add(id(el)))]

def inject_javascript(soup: BeautifulSoup, js_code: str):
    """
    Injects JavaScript code into the HTML.
    """
    # Check if there's an existing script with our ID
    existing_script = soup.find("script", {"id": "injected-functionality"})
    
    if existing_script:
        # Update existing script
        existing_script.string = js_code
    else:
        # Create a new script tag
        script_tag = soup.new_tag("script")
        script_tag["id"] = "injected-functionality"
        script_tag.string = js_code
        
        # Add it to the end of body or html if body doesn't exist
        if soup.body:
            soup.body.append(script_tag)
        elif soup.html:
            soup.html.append(script_tag)
        else:
            soup.append(script_tag)

def fix_page_links(client, page: Page, functionality_file: str, final_dir: str, available_files: list, site: Site):
    """
    Fixes links in the page to point to the correct local files by processing each link individually.
    """
    page_filename = os.path.basename(functionality_file)
    output_file = os.path.join(final_dir, page_filename)
    
    # Read the HTML content
    with open(functionality_file, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # Parse the HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Get a list of all available pages for linking
    available_files_str = "\n".join(available_files)
    
    # Create a mapping of original URLs to local filenames
    url_to_file_map = {}
    for p in site.get_pages():
        safe_filename = sanitize_filename(p.dir) + ".html"
        url_to_file_map[p.url] = safe_filename
        
        # Also add the path component as a key
        parsed_url = urlparse(p.url)
        if parsed_url.path:
            url_to_file_map[parsed_url.path] = safe_filename
            # Add with and without trailing slash
            path = parsed_url.path
            url_to_file_map[path.rstrip('/')] = safe_filename
            url_to_file_map[path + '/'] = safe_filename
    
    # Add the URL mapping to the available files info
    url_mapping_info = "\n".join([f"Original URL: {url} -> Local file: {filename}" 
                                 for url, filename in url_to_file_map.items()])
    
    # Parse the current page URL for relative link resolution
    current_url_parsed = urlparse(page.url)
    current_domain = f"{current_url_parsed.scheme}://{current_url_parsed.netloc}"
    
    # Find all links in the page
    links = soup.find_all("a", href=True)
    
    if not links:
        print(f"No links found in {page.url}")
        # Just copy the file to the output directory
        shutil.copy(functionality_file, output_file)
        return
    
    print(f"Found {len(links)} links in {page.url}")
    links_updated = 0
    
    # Process each link individually
    for link in links:
        original_href = link.get("href", "")
        link_text = link.get_text().strip()
        
        if not original_href:
            continue
        
        # Skip links that are just anchors
        if original_href.startswith("#"):
            continue
            
        # Skip links that are already fixed (pointing to local HTML files)
        if original_href.endswith(".html") and any(original_href == file for file in available_files):
            continue
            
        # Skip links that are clearly external and not in our site
        if (original_href.startswith("http") and 
            not any(domain in original_href for domain in [current_domain] + 
                   [urlparse(url).netloc for url in url_to_file_map.keys() if '://' in url])):
            continue
        
        # Try to resolve relative links to absolute URLs for better matching
        if not original_href.startswith(('http://', 'https://', 'mailto:', 'tel:')):
            # Handle root-relative links (starting with /)
            if original_href.startswith('/'):
                absolute_href = f"{current_domain}{original_href}"
            else:
                # Handle relative links (not starting with /)
                base_path = '/'.join(current_url_parsed.path.split('/')[:-1])
                if not base_path.endswith('/'):
                    base_path += '/'
                absolute_href = f"{current_domain}{base_path}{original_href}"
                
            # Check if we already have a mapping for this resolved URL
            if absolute_href in url_to_file_map:
                link["href"] = url_to_file_map[absolute_href]
                print(f"Direct mapping found: {original_href} -> {url_to_file_map[absolute_href]}")
                links_updated += 1
                continue
        
        # Prepare the prompt for this specific link
        link_prompt = LINK_FIX_PROMPT.format(
            original_link=original_href,
            page_url=page.url,
            link_text=link_text,
            available_files=available_files_str,
            url_mapping=url_mapping_info
        )
        
        try:
            # Call Anthropic to fix this specific link
            response = client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=100,  # Small token limit since we only need a simple response
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": link_prompt
                    }
                ]
            )
            
            # Get the corrected link
            corrected_link = response.content[0].text.strip()
            
            # Update the link in the soup
            if corrected_link and corrected_link != original_href:
                link["href"] = corrected_link
                print(f"Updated link: {original_href} -> {corrected_link}")
                links_updated += 1
                
        except Exception as e:
            print(f"Error fixing link {original_href}: {e}")
            # Continue with the next link
    
    # Write the updated HTML to the output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(str(soup))
        
    print(f"Fixed {links_updated} links for {page.url}")

def sanitize_filename(filename: str) -> str:
    """Replace any problematic filesystem characters."""
    sanitized = re.sub(r'[\\/*?:"<>|]', '_', filename)
    return sanitized 