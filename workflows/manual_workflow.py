import os
import time
import uuid
import asyncio
from data_models import Site, Page, Interaction
from utils import screenshot_page

# Custom classes to wrap Playwright request and response objects
class LoggedRequest:
    def __init__(self, request):
        self.id = str(uuid.uuid4())
        self.timestamp = time.time()
        self.url = request.url
        self.method = request.method
        self.headers = request.headers
        self.post_data = request.post_data
        self.resource_type = request.resource_type
        self.raw = request  # retain the original Playwright request

    def __repr__(self):
        return f"<LoggedRequest {self.method} {self.url} at {self.timestamp}. Post data:{self.post_data}>"

class LoggedResponse:
    def __init__(self, response, logged_request):
        self.timestamp = time.time()
        self.status = response.status
        self.headers = response.headers
        self.raw = response  # retain the original Playwright response
        self.request = logged_request  # the corresponding logged request

    def __repr__(self):
        return f"<LoggedResponse {self.status} for {self.request.url}. Response: {self.raw}>"

# The InteractionLogger maps user interactions with network events.
class InteractionLogger:
    def __init__(self):
        self.interactions = []
        self.request_backlog = []
        self.request_to_interaction = {}
        # Map raw Playwright requests (using id()) to our LoggedRequest instances.
        self.playwright_to_logged = {}

    async def log_interaction(self, interaction: Interaction):
        self.interactions.append(interaction)
        timestamp = interaction.timestamp  # expected to be a numeric timestamp

        # Process any requests that happened shortly before the interaction.
        # Use a slightly longer window to catch more related requests
        backlog_to_process = []
        for req in self.request_backlog:
            # Only process POST requests
            if req.method == "POST" and req.timestamp > timestamp - 1.0:  # Increased from 0.5 to 1.0
                backlog_to_process.append(req)
                
        for logged_request in backlog_to_process:
            self.request_backlog.remove(logged_request)
            self.request_to_interaction[logged_request.id] = interaction
            interaction.add_request(logged_request)

        # Don't clear remaining backlog - keep for potential future interactions

    async def add_request(self, logged_request: LoggedRequest):
        # Save mapping from the raw Playwright request to our logged request
        self.playwright_to_logged[id(logged_request.raw)] = logged_request

        timestamp = logged_request.timestamp

        # Attach to the most recent interaction if it's recent enough
        if self.interactions and self.interactions[-1].timestamp > timestamp - 2:
            current_interaction = self.interactions[-1]
            current_interaction.add_request(logged_request)
            self.request_to_interaction[logged_request.id] = current_interaction
        else:
            # Otherwise, add to backlog to be assigned later when an interaction occurs.
            self.request_backlog.append(logged_request)

    async def add_response(self, response):
        # Get the raw request from the response and look up its LoggedRequest.
        raw_req = response.request
        logged_request = self.playwright_to_logged.get(id(raw_req))
        if not logged_request:
            return
        logged_response = LoggedResponse(response, logged_request)

        # Look up the interaction associated with the logged request.
        interaction = self.request_to_interaction.get(logged_request.id)
        if interaction:
            interaction.add_response(logged_response)
        else:
            pass

# This function serves to instantiate a page with all the necessary information
# for the manual traversal workflow. If the page already exists, it will return
# the existing page.
def setup_page(site: Site, page_url: str):
    
    if page_url in site.pages:
        return site.pages[page_url]
    
    page = Page(page_url)
    site.pages[page_url] = page
    
    # Create the assets directory
    # Work on the assumption that we only do this cloning for one site
    # Therefore, assets is implicitly UberEats
    os.makedirs(os.path.join("assets", page.dir), exist_ok=True)
    return page

async def manual_workflow(playwright_page, start_url):
    with open(os.path.join("scripts", "click_listener.js"), "r") as f:
        click_listener_js = f.read()
    await playwright_page.add_init_script(click_listener_js)

    site = Site()
    await playwright_page.goto(start_url)
    await playwright_page.wait_for_load_state('networkidle')

    # Go to any automated redirects
    current_page_url = playwright_page.url
    logger = InteractionLogger()

    current_page = setup_page(site, current_page_url)

    # Wait for the page to load before taking the screenshot
    screenshot_filename = f"initial_{time.strftime('%Y%m%d-%H%M%S')}.png"
    screenshot_path = os.path.join("assets", current_page.dir, screenshot_filename)
    await playwright_page.screenshot(path=screenshot_path)
    current_page.screenshot = screenshot_path

    # In a manual session, we'll let the user navigate the site
    # and collect information about the pages they visit
    async def on_frame_navigated(frame):
        nonlocal current_page, current_page_url
        if frame == playwright_page.main_frame:
            current_url = frame.url
            current_page_url = current_url

            # Add this new page to the site
            # Otherwise, retrieve the existing page
            if current_url not in site.pages:
                current_page = setup_page(site, current_url)
            else:
                current_page = site.pages[current_url]

            await screenshot_page(playwright_page, current_page)

    # We'll first track user interactions on the page
    async def on_page_interaction(event_data: dict):
        # Use numeric timestamp for better comparison
        timestamp = time.time()
        screenshot_filename = f"{time.strftime('%Y%m%d-%H%M%S')}.png"

        interaction = Interaction(
            timestamp=timestamp,
            element_selector=event_data.get("selector"),
            dom_path=event_data.get("domPath"),
            coordinates=(event_data.get("x"), event_data.get("y")),
        )
        
        # Take screenshot immediately after interaction
        await playwright_page.wait_for_load_state('networkidle')
        screenshot_path = os.path.join("assets", current_page.dir, screenshot_filename)
        await playwright_page.screenshot(path=screenshot_path)
        
        interaction.set_interaction_screenshot(screenshot_path)
        current_page.interactions.append(interaction)
        
        # Log the interaction after screenshot is taken
        await logger.log_interaction(interaction)
    
    async def on_request(request):
        # Only process POST requests
        if request.method != "POST":
            return
            
        # Wrap the raw request in a LoggedRequest
        logged_request = LoggedRequest(request)
        
        # Process immediately
        await logger.add_request(logged_request)
        
        # If we have a current interaction, add it directly
        if logger.interactions and time.time() - logger.interactions[-1].timestamp < 2:
            logger.interactions[-1].add_request(logged_request)
            logger.request_to_interaction[logged_request.id] = logger.interactions[-1]

    async def on_response(response):
        # Get the raw request from the response
        raw_req = response.request
        
        # Only process responses for POST requests
        if raw_req.method != "POST":
            return
            
        await logger.add_response(response)
        
    await playwright_page.expose_function("notify_click", on_page_interaction)
    
    # Create wrapper functions that can be referenced for both adding and removing listeners
    def frame_navigated_handler(frame):
        try:
            # Instead of creating a task, run the function directly
            # This will prevent tasks from running after the browser is closed
            asyncio.create_task(on_frame_navigated(frame))
        except Exception as e:
            print(f"Error in frame navigation handler: {e}")
    
    def request_handler(request):
        try:
            asyncio.create_task(on_request(request))
        except Exception as e:
            print(f"Error in request handler: {e}")
    
    def response_handler(response):
        try:
            asyncio.create_task(on_response(response))
        except Exception as e:
            print(f"Error in response handler: {e}")
    
    # Register event handlers with proper async wrappers
    playwright_page.on("framenavigated", frame_navigated_handler)
    playwright_page.on("request", request_handler)
    playwright_page.on("response", response_handler)

    try:
        # Wait for user to press Enter in the terminal
        print("Manual session started. Press Enter to stop and continue...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        print("Manual session ended by user.")
    except Exception as e:
        print(f"Error in manual workflow: {e}")
    finally:
        playwright_page.remove_listener("framenavigated", frame_navigated_handler)
        playwright_page.remove_listener("request", request_handler)
        playwright_page.remove_listener("response", response_handler)
        
        print("Manual workflow completed and cleaned up.")

    return site
