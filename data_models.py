# data_models.py

from typing import List, Dict, Optional, Tuple
import json
from utils import get_sanitized_name_from_url

class Asset:
    def __init__(self, url: str, asset_type: str, text: str = None):
        self.url = url
        self.asset_type = asset_type
        self.text = text # For images, this is the alt text

class Assets:
    def __init__(self):
        self.imgs: List[Asset] = []
        self.styling: List[Asset] = []
        self.js: List[Asset] = []
        self.html: List[Asset] = []

class Interaction:
    def __init__(self, timestamp, element_selector: str = None, dom_path: str = None, coordinates: Tuple[int, int] = None):
        self.timestamp = timestamp
        self.element_selector = element_selector
        self.dom_path = dom_path
        self.coordinates = coordinates
        self.requests = []
        self.responses = []
        self.interaction_screenshot = None

    def set_interaction_screenshot(self, screenshot_path: str):
        self.interaction_screenshot = screenshot_path
    
    def add_request(self, request):
        self.requests.append(request)

    def add_response(self, response):
        self.responses.append(response)

    def __str__(self):
        return f"Interaction: {self.element_selector} at {self.coordinates}, {self.dom_path}. \nRequests: {self.requests}\nResponses: {self.responses}"

class Link:
    def __init__(self, url: str, text: str):
        self.url = url
        self.text = text

    def __str__(self):
        return f"Link(url={self.url}, text={self.text})"

class Page:
    def __init__(self, url: str):
        self.url = url
        self.assets = Assets()
        self.internal_links = []
        self.external_links = []
        self.interactions = []
        self.md: Optional[str] = None
        self.screenshot: Optional[str] = None
        self.html: Optional[str] = None
        self.dir = get_sanitized_name_from_url(url)

    def add_external_url(self, url: str, text: str):
        external_url = Link(url, text)
        self.external_links.append(external_url)

    def add_internal_url(self, url: str, text: str):
        internal_url = Link(url, text)
        self.internal_links.append(internal_url)

    def get_internal_links(self):
        return ("\n".join([(link.text) + " " + (link.url) for link in self.internal_links]))

    # Returns a formatted string of the interactions
    # for LLM input
    def synthesize_interactions(self):
        return "\n\n".join([str(interaction) for interaction in self.interactions])

class Site:
    # The manual traversal will fill out the page dictionary
    def __init__(self):
        self.pages: Dict[str, Page] = {}
        self.page_graph: Dict[str, List[str]] = {}
        self.construction: Dict[str, str] = {} 

    def get_pages(self):
        return self.pages.values()

    def to_json(self, file_path: str):        
        # Create a serializable representation of the site
        serializable_site = {}
        
        for url, page in self.pages.items():
            # Convert page object to dictionary
            page_dict = {
                "url": page.url,
                "dir": page.dir,
                "screenshot": page.screenshot,
                "html": page.html,
                "md": page.md,
                "internal_links": page.internal_links,
                "external_links": page.external_links,
                "interactions": []
            }
            
            # Convert interactions
            for interaction in page.interactions:
                interaction_dict = {
                    "timestamp": interaction.timestamp,
                    "element_selector": interaction.element_selector,
                    "dom_path": interaction.dom_path,
                    "coordinates": interaction.coordinates,
                    "interaction_screenshot": interaction.interaction_screenshot,
                    # Exclude requests and responses as they may contain complex objects
                    # that are not easily serializable
                    "request_count": len(interaction.requests),
                    "response_count": len(interaction.responses),
                    "first_request": str(interaction.requests[0]) if interaction.requests else None,
                    "first_response": str(interaction.responses[0]) if interaction.responses else None
                }
                page_dict["interactions"].append(interaction_dict)
            
            # Convert assets
            page_dict["assets"] = {
                "imgs": [{"url": asset.url, "asset_type": asset.asset_type} for asset in page.assets.imgs],
                "styling": [{"url": asset.url, "asset_type": asset.asset_type} for asset in page.assets.styling],
                "js": [{"url": asset.url, "asset_type": asset.asset_type} for asset in page.assets.js],
                "html": [{"url": asset.url, "asset_type": asset.asset_type} for asset in page.assets.html]
            }
            
            serializable_site[url] = page_dict
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_site, f, indent=2, default=str)
        
        print(f"Site structure written to {file_path}")

