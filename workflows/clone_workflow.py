import dotenv
import anthropic

client = anthropic.Anthropic(
    api_key=dotenv.get_key(".env", "ANTHROPIC_API_KEY")
)

def clone_workflow(site):
    # The site cloning workflow happens in many different parts.
    # Each part typically occurs once for each page.

    # First, we have an LLM call that recreates the general structure of the page
    # using the HTML as a guide. 
    # 
    # Then, we include the assets of the page, allowing the
    # LLM to ensure the assets in the HTML link to the correct static asset.
    #
    # Then, we include the styling of the page 

    return site