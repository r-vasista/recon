import json
import re
import logging

from app.models import MasterCategoryMapping
from openai import OpenAI

from django.conf import settings
from django.utils.text import slugify

logger = logging.getLogger("ai_variation") 

client = OpenAI(api_key=settings.OPEN_AI_KEY)

def success_response(data, message = None):
    return {"status": True, "data":data, "message":message}

def error_response(message):
    return {"status": False, "message":message}

def generate_variation_with_gpt(title, short_desc, desc, prompt_text, meta_title=None, slug=None, portal_name=None):
    """
    Generate rephrased version of news fields using GPT with detailed logs.
    """
    logger.info("🧠 [AI START] Generating variation for portal: %s", portal_name)
    logger.info("[AI INPUT] title: %s | short_desc : %d | content : %d",
                title, short_desc or "", desc[:50] or "")

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=[
                {"role": "developer", "content": prompt_text},
                {"role": "user", "content": f"Title: {title}\nShort: {short_desc}\nDesc:\n{desc}"}
            ],
        )

        content = response.output_text.strip()
        logger.info("[AI OUTPUT] Raw GPT response (first 400 chars): %s", content[:400])

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                raise ValueError("No valid JSON found in GPT response")

        logger.info("[AI SUCCESS] Parsed GPT JSON for %s | Keys: %s", portal_name, list(data.keys()))
        return (
            data.get("title", title),
            data.get("short_description", short_desc),
            data.get("description", desc),
            data.get("meta_title", meta_title or title),
            data.get("slug", slug or slugify(meta_title or title)),
        )

    except Exception as e:
        logger.exception("💥 [AI ERROR] GPT generation failed for %s: %s", portal_name, str(e))
        return (title, short_desc, desc, meta_title or title, slug or slugify(meta_title or title))       
    
def get_portals_from_assignment(assignment):
    """
    Given a UserCategoryGroupAssignment, return all (portal, portal_category) pairs.
    """
    portals = []

    # Case 1: Assignment is for a single master_category
    if assignment.master_category:
        mappings = MasterCategoryMapping.objects.filter(
            master_category=assignment.master_category
        ).select_related("portal_category__portal")
        for mapping in mappings:
            portals.append((mapping.portal_category.portal, mapping.portal_category))

    # Case 2: Assignment is for a group (iterate over its master categories)
    if assignment.group:
        for mc in assignment.group.master_categories.all():
            mappings = MasterCategoryMapping.objects.filter(
                master_category=mc
            ).select_related("portal_category__portal")
            for mapping in mappings:
                portals.append((mapping.portal_category.portal, mapping.portal_category))

    return portals
