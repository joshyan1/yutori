import dotenv
import anthropic
from data_models import Site, Page
import os
import json
import re

SYSTEM_PROMPT = """You are an intelligent web developer that specializes in producing websites from top tier design companies. 
Do your absolute best to create the page or else you will be fired.
Your sites are written in HTML, CSS, and JavaScript."""

INTERACTION_PROMPT = """I have a website that is currently implemented in HTML.
I have a list of interactions that I want to implement on this website. The interactions are provided with their element, backend requests, and response. 
Implement JavaScript functionality for every clickable element on the page. For any element that has a backend request, implement a that function mimics this backend request and returns the corresponding placeholder information.

For common elements like buttons and dropdown items, create the corresponding functionality.

Utilize the following schema to return the HTML output and descriptions of the functionality. Ensure that the function in the HTML corresponds to the functionality's function name exactly.  Do not return any other text in your response.

{
    html: str <html code>,
    functionality: [
        A list of descriptions in the format:
        function_name: {
            description: str <description of the functionality>, 
            element_selector: str <element selector>,
            dom_path: str <dom path>,
        },
    ]
}"""

FUNCTIONALITY_PROMPT = """I have a website that is currently implemented in HTML. The website contains mock functionality in JavaScript.
I have a list of functionalities that I want to implement on this website. The functionalities are provided with their element, and description.
Ensure that the functionality is implemented in the HTML file to its fullest extent. Do not change any of the existing HTML. Ensure that the
website is fully functional and each element works how it would be expected to work.

Return only the HTML output formatted in ```html and ``` tags. Do not return any other text in your response."""

LINKING_PROMPT = """I have a website that is currently implemented in HTML. The website currently contains many relative links. However,
the site will live in a static directory with many other pages. I need you to link the pages together. You will be provided the existing HTML,
and the list of current pages. In the directory. These will have their file paths as well as the original url it is representing. Replace all
relative links on this page with the corresponding absolute link.

Return only the final HTML output formatted in ```html and ``` tags. Do not return any other text in your response."""

# Helper function to sanitize filenames
def sanitize_filename(filename):
    # Replace slashes, backslashes, and other problematic characters with underscores
    # Also remove any characters that aren't alphanumeric, underscore, hyphen, or period
    sanitized = re.sub(r'[/\\?%*:|"<>]', '_', filename)
    # Replace any equals signs with underscores
    sanitized = sanitized.replace('=', '_')
    return sanitized

def clone_workflow(site: Site):
    print("Cloning workflow started")

    try:
        client = anthropic.Anthropic(
            api_key=dotenv.get_key(".env", "ANTHROPIC_API_KEY")
        )

        pages = site.get_pages()

        # The cloned site will store the pages of each page
        cloned_site_dir = os.path.join(os.getcwd(), "cloned_site")
        os.makedirs(cloned_site_dir, exist_ok=True)
        
        # Create all necessary directories
        v1_dir = os.path.join(cloned_site_dir, "v1")
        v2_dir = os.path.join(cloned_site_dir, "v2")
        v3_dir = os.path.join(cloned_site_dir, "v3")
        final_dir = os.path.join(cloned_site_dir, "final")
        debug_dir = os.path.join(cloned_site_dir, "debug")
        anthropic_dir = os.path.join(os.getcwd(), "anthropic")
        
        for directory in [v1_dir, v2_dir, v3_dir, final_dir, debug_dir, anthropic_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # Initialize the construction dictionary for each page
        for page in pages:
            if not hasattr(site, 'construction'):
                site.construction = {}
            if page.url not in site.construction:
                site.construction[page.url] = {}

        # The site cloning workflow happens in many different parts.
        # Each part typically occurs once for each page.

        # First, we have an LLM call that recreates the general structure of the page
        # using the HTML as a guide. What I've now realized is that the HTML for this
        # site is actually extremely accurate. 

        print("Initializing HTML")
        for page in pages:
            try:
                page_html_path = initialize_html(client, page, cloned_site_dir)
                site.construction[page.url]['v1'] = page_html_path
            except Exception as e:
                print(f"Error initializing HTML for page {page.url}: {e}")
                # Continue with next page
                continue

        # Then, we include the assets of the page, allowing the
        # LLM to ensure the assets in the HTML link to the correct static asset.
        # A lot of public assets are already included so we try to fill in the blanks

        # Then, we style the page. We ask the LLM to style the page using the image and
        # existing HTML as a guid. 

        # This is the hardest step. We ask the LLM to now include the functionalities of 
        # the page based on the general style of the element, as well as the interactions
        # that we've recorded. 

        print("Implementing interactions")
        for page in pages:
            try:
                # Skip pages that failed in the HTML initialization step
                if page.url not in site.construction or 'v1' not in site.construction[page.url]:
                    print(f"Skipping interactions for page {page.url} due to previous errors")
                    continue
                    
                html_path, functionality = implement_interactions(client, site, page, cloned_site_dir)
                site.construction[page.url]['v2'] = html_path
                site.construction[page.url]['functionality'] = functionality
            except Exception as e:
                print(f"Error implementing interactions for page {page.url}: {e}")
                # Continue with next page
                continue

        print("Implementing functionality")
        for page in pages:
            try:
                # Skip pages that failed in previous steps
                if page.url not in site.construction or 'v2' not in site.construction[page.url]:
                    print(f"Skipping functionality for page {page.url} due to previous errors")
                    continue
                    
                html_path = implement_functionality(client, site, page, cloned_site_dir)
                site.construction[page.url]['v3'] = html_path
            except Exception as e:
                print(f"Error implementing functionality for page {page.url}: {e}")
                # Continue with next page
                continue

        print("Linking pages")
        for page in pages:
            try:
                # Skip pages that failed in previous steps
                if page.url not in site.construction or 'v3' not in site.construction[page.url]:
                    print(f"Skipping linking for page {page.url} due to previous errors")
                    continue
                    
                html_path = link_pages(client, site, page, cloned_site_dir)
                site.construction[page.url]['v4'] = html_path
            except Exception as e:
                print(f"Error linking pages for page {page.url}: {e}")
                # Continue with next page
                continue

        # Finally, we link the pages together using the model to input the URLS, connecting 
        # to other pages

        return site
        
    except Exception as e:
        print(f"Error in cloning workflow: {e}")
        # Return the site with whatever progress was made
        return site

def link_pages(client, site: Site, page: Page, directory: str):
    html_path = site.construction[page.url]['v3']

    with open(html_path, "r") as f:
        html = f.read()

    page_name = page.dir
    # Sanitize page name for use in filenames
    safe_page_name = sanitize_filename(page_name)
    html_path = os.path.join(directory, "final", f"{safe_page_name}.html")

    internal_links = page.get_internal_links()

    # Get a list of all HTML files in the v3 directory to provide as context for linking
    v3_directory = os.path.join(directory, "v3")
    available_pages = []
    
    if os.path.exists(v3_directory):
        for filename in os.listdir(v3_directory):
            if filename.endswith(".html"):
                # Add the filename to the list of available pages
                available_pages.append(filename)
    
    available_pages_str = "\n".join(available_pages)
    
    # Create the final directory if it doesn't exist
    final_directory = os.path.join(directory, "final")
    os.makedirs(final_directory, exist_ok=True)
    
    # Prepare context about available pages for the LLM
    linking_context = f"""
Available HTML files in the cloned site:
{available_pages_str}

Internal links found on this page:
{internal_links}
"""

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
                        "text": f"{LINKING_PROMPT}\n\n{html}\n\n{linking_context}"
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
    
    try:
        # Use the collected full response text
        output = full_response_text
        
        # Check if the response contains HTML code blocks
        if "```html" in output and "```" in output.split("```html", 1)[1]:
            html = output.split("```html")[1].split("```")[0]
        else:
            # If no HTML code blocks found, save the raw response for debugging
            debug_path = os.path.join(directory, "debug", f"{safe_page_name}_linking_raw_response.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Warning: No HTML code blocks found in linking response for page {page.url}")
            # Use the raw output as HTML (may not be ideal but prevents failure)
            html = output
    except (IndexError, AttributeError) as e:
        print(f"Error extracting HTML from linking response for page {page.url}: {e}")
        # Return original HTML as fallback
        with open(site.construction[page.url]['v3'], "r") as f:
            html = f.read()

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path

def implement_functionality(client, site: Site, page: Page, directory: str):
    if page.url in site.construction and 'functionality' in site.construction[page.url]:
        functionality = site.construction[page.url]['functionality']
    else:
        raise ValueError(f"Functionality not found for page {page.url}")
    
    functionality_input = ""
    for functionality in functionality:
        functionality_input += f"Function name: {functionality['function_name']}\n"
        functionality_input += f"{functionality['description']}\n"
        functionality_input += f"Element selector: {functionality['element_selector']}\n"
        functionality_input += f"DOM path: {functionality['dom_path']}\n"

    html_path = site.construction[page.url]['v2']
    with open(html_path, "r") as f:
        html = f.read()

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
                        "text": f"{FUNCTIONALITY_PROMPT}\n\n{html}\n\n{functionality_input}"
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
                
    page_name = page.dir
    # Sanitize page name for use in filenames
    safe_page_name = sanitize_filename(page_name)
    html_path = os.path.join(directory, "v3", f"{safe_page_name}.html")

    try:
        # Use the collected full response text
        output = full_response_text
        
        # Check if the response contains HTML code blocks
        if "```html" in output and "```" in output.split("```html", 1)[1]:
            html = output.split("```html")[1].split("```")[0]
        else:
            # If no HTML code blocks found, save the raw response for debugging
            debug_path = os.path.join(directory, "debug", f"{safe_page_name}_raw_response.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Warning: No HTML code blocks found in response for page {page.url}")
            # Use the raw output as HTML (may not be ideal but prevents failure)
            html = output
    except (IndexError, AttributeError) as e:
        print(f"Error extracting HTML from response for page {page.url}: {e}")
        # Return empty HTML as fallback
        html = "<html><body><p>Error extracting HTML from response</p></body></html>"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


def implement_interactions(client, site: Site, page: Page, directory: str):
    # Get the HTML path from site.construction
    if page.url in site.construction and 'v1' in site.construction[page.url]:
        html_path = site.construction[page.url]['v1']
    else:
        raise ValueError(f"HTML path not found for page {page.url}")
        
    with open(html_path, "r") as f:
        html = f.read()

    interactions = page.synthesize_interactions()
    
    # Create the streaming request
    with client.messages.stream(
        model="claude-3-7-sonnet-20250219",
        max_tokens=20000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{INTERACTION_PROMPT}\n\n{html}\n\n{interactions}"
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

    page_name = page.dir
    # Sanitize page name for use in filenames
    safe_page_name = sanitize_filename(page_name)
    html_path = os.path.join(directory, "v2", f"{safe_page_name}.html")

    # Extract the HTML content from the message
    # Use the collected full response text
    response_text = full_response_text
    
    try:
        output = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response for page {page.url}: {e}")
        print(f"Response text: {response_text[:500]}...")  # Print first 500 chars for debugging
        
        # Save the raw response for debugging
        debug_path = os.path.join(directory, "debug", f"{safe_page_name}_raw_response.txt")
        os.makedirs(os.path.join(directory, "debug"), exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(response_text)

        os.makedirs(os.path.join(directory, "v2"), exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)  # Write the original HTML content
        
        print(f"JSON parsing failed for {page.url}, using original HTML as fallback")
            
        # Return empty values as fallback
        return html_path, []

    # Write the HTML content to the file
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(output["html"])
    except KeyError:
        print(f"Error: 'html' key not found in output for page {page.url}")
        # Save the parsed output for debugging
        debug_path = os.path.join(directory, "debug", f"{safe_page_name}_parsed_output.json")
        os.makedirs(os.path.join(directory, "debug"), exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        return html_path, []
    
    # Optionally save the JSON for reference
    json_path = os.path.join(directory, "v2", f"{safe_page_name}_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    if "functionality" in output:
        return html_path, output["functionality"]
    else:
        return html_path, []

# Given a page, initialiaze the HTML for the page
# Returns the path to the HTML file
def initialize_html(client, page: Page, directory: str):
    page_name = page.dir
    # Sanitize page name for use in filenames
    safe_page_name = sanitize_filename(page_name)
    html_path = os.path.join(directory, "v1", f"{safe_page_name}.html")

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
            debug_path = os.path.join(directory, "debug", f"{safe_page_name}_raw_response.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Warning: No HTML code blocks found in response for page {page.url}")
            # Use the raw output as HTML (may not be ideal but prevents failure)
            html = output
    except (IndexError, AttributeError) as e:
        print(f"Error extracting HTML from response for page {page.url}: {e}")
        # Save the raw message for debugging
        debug_path = os.path.join(directory, "debug", f"{safe_page_name}_error.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(message_dict, f, indent=2)
        # Return empty HTML as fallback
        html = "<html><body><p>Error extracting HTML from response</p></body></html>"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path