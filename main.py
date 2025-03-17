# main.py

import os
import sys
import dotenv
import asyncio
from playwright.async_api import async_playwright
from data_models import Site
from workflows.manual_workflow import manual_workflow
from workflows.automated_workflow import automated_workflow
from workflows.clone_workflow import clone_workflow
from workflows.enhanced_injection_workflow import enhanced_injection_workflow
#from logger import SiteLogger
#from cloner.clone_builder import CloneBuilder

async def main():
    start_url ="https://www.ubereats.com"
    user_data_dir = os.path.join(os.getcwd(), "persistent_user_data")

    # Create assets directory if it doesn't exist
    assets_dir = os.path.join(os.getcwd(), "assets")
    os.makedirs(assets_dir, exist_ok=True)

    site_data_dir = os.path.join(os.getcwd(), "site_data")
    os.makedirs(site_data_dir, exist_ok=True)

    # Load browser scripts
    with open(os.path.join("scripts", "navigator_overrider.js"), "r") as f:
        navigator_overrider_js = f.read()
    
    async with async_playwright() as p:
        # Initialize playwright context
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False
        )

        page = await context.new_page()
        await page.add_init_script(navigator_overrider_js)
        
        site = None
        try:
            # The manual traversal workflow will return a Site object, which should 
            # initialize the site object with a map from each page to its Page object
            site = await manual_workflow(page, start_url)
            site.to_json(os.path.join(site_data_dir, "site.json"))
        except Exception as e:
            print(f"Error in manual workflow: {e}")
        
        # Close context outside the try/except to avoid nested exceptions
        try:
            await context.close()
        except Exception as e:
            print(f"Warning: Could not close browser context properly: {e}")
        
        # Only continue if we have a valid site object
        if site:
            try:
                # Step 2: Automate the scraping
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False
                )

                page = await context.new_page()
                
                try:
                    site = await automated_workflow(page, site)
                    site.to_json(os.path.join(site_data_dir, "automated_site.json"))
                    print("Automated workflow completed successfully.")
                except Exception as e:
                    print(f"Error in automated workflow: {e}")
                    # Still save what we have
                    site.to_json(os.path.join(site_data_dir, "automated_site_partial.json"))
                    print("Saved partial automated site data.")
                finally:
                    # Always try to close the context properly
                    try:
                        await context.close()
                    except Exception as e:
                        print(f"Warning: Could not close browser context properly: {e}")

            except Exception as e:
                print(f"Fatal error in automated workflow setup: {e}")

        if site:
            # Step 3: Build clone using the enhanced injection workflow
            try:
                site = enhanced_injection_workflow(site)
                print("Enhanced cloning complete! Check the 'cloned_injection' folder for results.")
            except Exception as e:
                print(f"Error in enhanced injection workflow: {e}")

if __name__ == "__main__":
    asyncio.run(main())