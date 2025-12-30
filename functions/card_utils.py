import re

CARD_PATTERN = re.compile(
    r'(\d{15,19})\s*[|:/\\\-\s]\s*(\d{1,2})\s*[|:/\\\-\s]\s*(\d{2,4})\s*[|:/\\\-\s]\s*(\d{3,4})'
)

def parse_card(line: str) -> dict:
    line = line.strip()
    if not line:
        return None
    
    match = CARD_PATTERN.search(line)
    if not match:
        return None
    
    cc, mm, yy, cvv = match.groups()
    
    mm = mm.zfill(2)
    if int(mm) < 1 or int(mm) > 12:
        return None
    
    if len(yy) == 2:
        yy = "20" + yy
    if len(yy) != 4:
        return None
    
    return {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}

def parse_cards(text: str) -> list:
    cards = []
    for line in text.strip().split("\n"):
        card = parse_card(line)
        if card:
            cards.append(card)
    return cards

def format_card(card: dict) -> str:
    return f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
