"""Default prompt templates for AI tasks.

Users can override any of these via app settings (Settings → AI → Prompts);
only overrides are stored, so deleting the setting row reverts to the default.

Templates use {placeholder} tokens that are substituted with render_prompt().
Substitution is a literal replace of known placeholders — NOT str.format() —
so templates may freely contain JSON braces and user edits can never crash a
call with a stray brace.
"""

# Placeholders available to each task's template. Shown in the settings UI.
PROMPT_PLACEHOLDERS: dict[str, list[str]] = {
    "ai_prompt_receipt_gate": [],
    "ai_prompt_receipt_extract": ["{categories}", "{today}"],
    "ai_prompt_nl_parse": ["{text}", "{categories}", "{today}"],
    "ai_prompt_suggest_category": ["{payee_name}", "{amount}", "{memo}", "{categories}"],
    "ai_prompt_normalize_payee": ["{payee_name}"],
}

DEFAULT_PROMPTS: dict[str, str] = {
    "ai_prompt_receipt_gate": (
        "Look at this image and decide whether it shows a purchase receipt, "
        "an invoice, or a bill — a document listing items or services and an "
        "amount paid or owed.\n\n"
        "Return ONLY a JSON object: "
        '{"is_receipt": true or false}\n\n'
        "Photos of people, pets, scenery, screenshots of apps, memes, or any "
        "other non-financial document are NOT receipts."
    ),
    "ai_prompt_receipt_extract": (
        "You are given a photo of a purchase receipt. Extract the transaction data.\n"
        "Today's date is {today}.\n\n"
        "Budget categories (name (group)):\n{categories}\n\n"
        "Return ONLY a JSON object with exactly these fields:\n"
        "{\n"
        '  "payee": "merchant name, cleaned up (e.g. \'Whole Foods\', not'
        " 'WHOLEFDS MKT 10847'), or null if unreadable\",\n"
        '  "total": 0.00,\n'
        '  "date": "YYYY-MM-DD or null if not visible",\n'
        '  "category": "the single best-matching category NAME from the list, or null",\n'
        '  "confidence": 0.0,\n'
        '  "memo": "short note if something is noteworthy, else null",\n'
        '  "line_items": [{"description": "item as printed", "amount": 0.00,'
        ' "category": "best category NAME or null"}],\n'
        '  "suggested_split": [{"category": "category NAME", "amount": 0.00}]\n'
        "}\n\n"
        "Rules:\n"
        "- total is the grand total actually paid, after tax and discounts.\n"
        "- Use category names exactly as they appear in the list. Never invent categories.\n"
        "- suggested_split: group the line items by category and distribute tax"
        " proportionally so the split amounts sum exactly to total. If everything"
        " belongs to one category, return an empty array.\n"
        "- confidence is your overall confidence in payee+total+date, from 0 to 1.\n"
        "- Amounts are positive numbers. Output only the JSON object."
    ),
    "ai_prompt_nl_parse": (
        "Parse this natural-language description of a financial transaction into JSON.\n"
        "Today's date is {today}.\n\n"
        "Description: {text}\n\n"
        "Budget categories (name (group)):\n{categories}\n\n"
        "Return ONLY a JSON object with exactly these fields:\n"
        "{\n"
        '  "payee": "merchant/person name or null",\n'
        '  "amount": 0.00,\n'
        '  "direction": "outflow or inflow (outflow = money spent, the usual case)",\n'
        '  "date": "YYYY-MM-DD — resolve relative dates like \'yesterday\' against'
        " today's date; use today when unstated\",\n"
        '  "category": "the single best-matching category NAME from the list, or null",\n'
        '  "memo": "leftover detail worth keeping, else null",\n'
        '  "confidence": 0.0\n'
        "}\n\n"
        "Rules:\n"
        "- amount is a positive number.\n"
        "- Use category names exactly as they appear in the list. Never invent categories.\n"
        "- Output only the JSON object."
    ),
    "ai_prompt_suggest_category": (
        "Transaction: payee='{payee_name}', amount={amount}, memo='{memo}'\n\n"
        "Budget categories (name (group)):\n{categories}\n\n"
        "Return ONLY a JSON object:\n"
        '{"category": "the single best-matching category NAME from the list, or null",'
        ' "confidence": 0.0}\n'
        "Use category names exactly as they appear in the list. Never invent categories."
    ),
    "ai_prompt_normalize_payee": (
        "Normalize this bank payee name to a clean, readable merchant name: '{payee_name}'\n"
        "Respond with only the normalized name, nothing else."
    ),
}


def render_prompt(template: str, values: dict[str, str]) -> str:
    """Substitute {key} placeholders by literal replacement.

    Unknown placeholders in the template are left as-is rather than raising,
    so a user-edited template can never break an AI call.
    """
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out
