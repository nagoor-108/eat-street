"""
Ollama RAG Chatbot Engine — Kakinada Eat Street
* Connects to Ollama (/api/generate) with streaming when Ollama is online
* Strictly scoped to Kakinada Eat Street food, shops, menu, orders, and table bookings
* Irrelevant queries receive the exact Telugu refusal message
* Never invents dishes or prices — strictly grounded in database context
* Features an intelligent DB-aware assistant fallback when Ollama is offline
* Auto-detects installed models (llama3, llama3.2, mistral, gemma, etc.)
"""
import re
import time
import requests
import json
from collections import defaultdict
from models import Shop, MenuItem
from config import Config

SCOPE_REFUSAL_MESSAGES = {
    'te': "క్షమించండి, నేను Kakinada Eat Street food, shops, menu, orders, and table bookings గురించి మాత్రమే సహాయం చేయగలను.",
    'teluglish': "Kshaminchandi, nenu Kakinada Eat Street food, shops, menu, orders, and table bookings gurinchi matrame sahayapadagalanu.",
    'hi': "क्षमा करें, मैं केवल काकीनाडा ईट स्ट्रीट भोजन, दुकानों, मेनू, ऑर्डर और टेबल बुकिंग के बारे में ही सहायता कर सकता हूँ।",
    'en': "Sorry, I can only help you with Kakinada Eat Street food, shops, menu, orders, and table bookings."
}
SCOPE_REFUSAL_MESSAGE = SCOPE_REFUSAL_MESSAGES['te']

LANG_INSTRUCTIONS = {
    'en': "Respond in clear, friendly English.",
    'te': "Respond entirely in natural, fluent Telugu (తెలుగు లిపి). Provide all food names, prices, stalls, and explanations in Telugu.",
    'teluglish': "Respond in conversational Teluglish (Telugu language written in English alphabet / Roman script). E.g. 'Kakinada Eat Street lo Dum Biryani Biryani House daggara dorukutundi, price ₹180.'",
    'hi': "Respond entirely in natural, fluent Hindi (हिंदी भाषा और लिपि). Provide all food names, prices, and stall details in Hindi."
}

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the friendly AI assistant for Kakinada Eat Street — "The Taste of Kakinada".
Help customers find food, shops, prices, dietary options, table bookings, and orders.
Answer ONLY based on the Eat Street database context provided below.

LANGUAGE DIRECTIVE:
{lang_instruction}

CRITICAL RULES:
1. Never invent dishes, prices, shops, availability, or offers.
2. If a customer asks about a dish not present in the Eat Street data, clearly state that it is not currently available at Eat Street and suggest real alternatives from the data in the selected language.
3. If the customer asks ANY question unrelated to Kakinada Eat Street food, shops, menu, orders, or table bookings (e.g. coding, programming, politics, history, general knowledge, math, personal advice), you MUST respond with the exact scope refusal message.
4. Keep food responses friendly and concise (2-4 sentences max).

=== KAKINADA EAT STREET DATA ===
{context}
=== END DATA ===
"""


# ─── CONTEXT BUILDER ──────────────────────────────────────────────────────────
def build_context(app) -> str:
    """Build a compact, richly-annotated RAG context string from the database."""
    with app.app_context():
        lines = []
        shops = Shop.query.filter_by(is_active=True).all()
        for shop in shops:
            services = "/".join(filter(None, [
                "DineIn"   if shop.dine_in  else "",
                "Takeaway" if shop.takeaway else "",
                "Delivery" if shop.delivery else "",
            ]))
            lines.append(
                f"SHOP:{shop.name}|Code:{shop.shop_code}|Cat:{shop.category}|"
                f"Rating:{shop.rating}|Hours:{shop.opening_time}-{shop.closing_time}|"
                f"Loc:{shop.location}|Services:{services}"
            )
            for item in shop.menu_items:
                if item.is_available:
                    vt = "V" if item.veg_nonveg == "veg" else ("E" if item.veg_nonveg == "egg" else "N")
                    q  = f" ({item.quantity_desc})" if item.quantity_desc else ""
                    lines.append(f"  ITEM:{item.name}{q}|Rs.{int(item.price)}|[{vt}]|Shop:{shop.name}|ShopCode:{shop.shop_code}")
        return "\n".join(lines)


# ─── RELEVANCE CLASSIFIER ─────────────────────────────────────────────────────
def is_relevant_query(user_message: str, context: str = "") -> bool:
    """
    Classify whether a user's question is relevant to Kakinada Eat Street.
    Returns True if relevant (food, menu, shops, orders, tables, reservations, greetings).
    Returns False if unrelated (coding, politics, history, trivia, personal advice, etc.).
    """
    if not user_message or not user_message.strip():
        return False

    msg = user_message.lower().strip()

    # Explicit unrelated patterns
    unrelated_patterns = [
        r'\b(python|java|javascript|c\+\+|golang|rust|typescript|html|css|sql|php|swift|kotlin)\b',
        r'\b(code|coding|programming|algorithm|function|class|loop|debug|compiler|regex|git|docker|kubernetes)\b',
        r'\b(modi|bjp|congress|tdp|ysrcp|janasena|pawan\s*kalyan|jagan|chandrababu|election|parliament|politics|political|government|democracy)\b',
        r'\b(war|russia|ukraine|israel|gaza|nato|military|army)\b',
        r'\b(quantum|physics|gravity|relativity|planet|solar\s*system|galaxy|black\s*hole)\b',
        r'\b(who\s+(is|was)\s+(the\s+)?(president|prime\s*minister|king|queen|ceo|founder))\b',
        r'\b(capital\s+of|distance\s+between|speed\s+of\s+light|calculate|formula\s+for|integral|derivative|algebra)\b',
        r'\b(headache|fever|diagnose|prescription|symptoms|cure|disease|medicine|doctor)\b',
        r'\b(bitcoin|cryptocurrency|crypto|stock\s*market|invest\s*money|mutual\s*fund)\b',
        r'\b(dating\s*advice|relationship\s*advice|essay\s+on|homework|write\s+(a\s+)?(poem|story|song|essay|script))\b',
    ]

    for pat in unrelated_patterns:
        if re.search(pat, msg):
            return False

    # Check for relevant keywords (English, Telugu, Hindi)
    relevant_keywords = [
        # Greetings & Help
        'hi', 'hello', 'hey', 'namaste', 'greetings', 'morning', 'evening', 'help', 'what can you do', 'who are you',
        'నమస్కారం', 'హలో', 'హాయ్', 'సహాయం', 'नमस्ते', 'प्रणाम', 'हैलो', 'हाय', 'मदद',
        # Food & Cuisines (English)
        'food', 'dish', 'dishes', 'menu', 'item', 'items', 'eat', 'hungry', 'craving', 'order', 'cart',
        'price', 'cost', 'rs', 'inr', 'rupees', '₹', 'cheap', 'budget', 'under', 'below', 'rate', 'rates',
        'veg', 'vegetarian', 'nonveg', 'non-veg', 'egg', 'chicken', 'mutton', 'fish', 'prawns', 'meat',
        'biryani', 'bbq', 'barbeque', 'shawarma', 'momos', 'momo', 'waffle', 'waffles', 'chaat', 'chat',
        'noodles', 'fried rice', 'rice', 'manchurian', 'frankie', 'roll', 'rolls', 'kabab', 'kebab',
        'wings', 'lollipop', 'lollipops', 'burger', 'pizza', 'fries', 'mushroom', 'paneer', 'ice cream', 'shake', 'shakes',
        'beverage', 'drink', 'drinks', 'tea', 'coffee', 'snack', 'snacks', 'starter', 'starters',
        'sweet', 'dessert', 'desserts', 'spicy', 'taste', 'recommend', 'recommendation', 'suggest',
        'best', 'top', 'popular', 'special', 'combo', 'pakodi', 'pakoda', 'pani puri', 'sev puri', 'bhel', 'pav bhaji',
        'samosa', 'chilli', 'crispy', 'tandoori', 'tikka', 'malai', 'gravy', 'curry', 'pottikalu', 'idly', 'idli', 'ragi',
        # Food & Cuisines (Telugu)
        'ఫుడ్', 'వంటకం', 'వంటకాలు', 'మెనూ', 'ఐటమ్', 'ఐటమ్స్', 'ఆర్డర్', 'ధర', 'ధరలు', 'రేటు', 'రేట్లు', 'ఎంత', 'ఖర్చు', 'రూపాయలు', 'లోపు', 'బడ్జెట్',
        'వెజ్', 'శాకాహార', 'శాకాహారి', 'నాన్-వెజ్', 'నాన్‌వెజ్', 'మాంసాహార', 'గుడ్డు', 'ఎగ్', 'చికెన్', 'మటన్',
        'బిర్యాని', 'బిర్యానీ', 'బార్బెక్యూ', 'షవర్మా', 'షావర్మా', 'మోమోస్', 'మోమో', 'వాఫుల్స్', 'వాఫుల్', 'చాట్',
        'నూడుల్స్', 'నూడిల్స్', 'ఫ్రైడ్ రైస్', 'ఫ్రైడ్‌రైస్', 'రైస్', 'మంచూరియా', 'మంచూరియన్', 'ఫ్రాంకీ', 'రోల్స్', 'కబాబ్', 'కబాబ్స్',
        'లాలీపాప్', 'లాలీపాప్స్', 'వింగ్స్', 'మష్రూమ్', 'పనీర్', 'ఐస్ క్రీమ్', 'షేక్స్', 'స్నాక్స్', 'పకోడి', 'పకోడీ',
        'పానీ పూరి', 'పానీపూరి', 'సేవ్ పూరి', 'భేల్ పూరి', 'సమోసా', 'చోలే భటూరే', 'పొట్టిక్కలు', 'పొట్టికలు', 'ఇడ్లీ', 'రాగి సంగటి', 'నాటుకోడి పులుసు',
        # Food & Cuisines (Hindi)
        'खाना', 'व्यंजन', 'भोजन', 'मेनू', 'आइटम', 'ऑर्डर', 'दाम', 'कीमत', 'दर', 'रुपये', 'अंदर', 'कम', 'सस्ता', 'बजट',
        'शाकाहारी', 'वेज', 'मांसाहारी', 'नॉन-वेज', 'अंडा', 'चिकन', 'मटन',
        'बिरयानी', 'बारबेक्यू', 'शवर्मा', 'शावर्मा', 'मोमोज', 'मोमो', 'वाफल्स', 'वाफल', 'चाट',
        'नूडल्स', 'फ्राइड राइस', 'चावल', 'मंचूरियन', 'फ्रैंकी', 'रोल', 'कबाब', 'टिक्का',
        'लॉलीपॉप', 'विंग्स', 'मशरूम', 'पनीर', 'आइसक्रीम', 'शेक्स', 'स्नैक्स', 'पकोड़ा', 'पकोड़ी',
        'पानी पूरी', 'पानीपूरी', 'सेव पूरी', 'भेल पूरी', 'समोसा', 'समोसे', 'छोले भटूरे', 'इडली',
        # Shops & Places
        'shop', 'shops', 'stall', 'stalls', 'restaurant', 'restaurants', 'outlet', 'eat street', 'eatstreet',
        'kakinada', 'timing', 'timings', 'hours', 'opening', 'closing', 'open', 'close', 'rating', 'ratings',
        'review', 'reviews', 'location', 'address', 'bhanugudi', 'rama rao peta',
        'షాపు', 'షాపులు', 'స్టాల్', 'స్టాల్స్', 'కాకినాడ', 'సమయం', 'రేటింగ్', 'లొకేషన్',
        'दुकान', 'दुकानें', 'स्टॉल', 'स्टॉल्स', 'काकीनाडा', 'समय', 'रेटिंग', 'स्थान',
        # Dine In & Reservations
        'table', 'tables', 'seat', 'seats', 'book', 'booking', 'reserve', 'reservation', 'reservations',
        'dine-in', 'dine in', 'dinein', 'qr', 'waiter', 'water', 'bill', 'service',
        'టేబుల్', 'బుకింగ్', 'రిజర్వేషన్', 'డైన్-ఇన్', 'టేబుల్స్',
        'टेबल', 'बुकिंग', 'रिजर्वेशन', 'डाइन-इन',
        # Delivery & Takeaway
        'delivery', 'deliver', 'takeaway', 'pickup', 'takeout', 'track', 'tracking', 'order status',
        'డెలివరీ', 'టేక్‌అవే', 'డెలివరి', 'పార్సిల్', 'डिलीवरी', 'टेकअवे', 'पार्सल',
        # Known food terms to handle not-available responses
        'sushi', 'taco', 'tacos', 'pasta', 'ramen', 'steak', 'croissant', 'lasagna',
        'సుషీ', 'పిజ్జా', 'బర్గర్', 'పాస్తా', 'సుషి', 'టాకో',
        'सुशी', 'पिज्जा', 'बर्गर', 'पास्ता', 'टाको'
    ]

    if any(k in msg for k in relevant_keywords):
        return True

    # Check against items and shops in context
    if context:
        for line in context.splitlines():
            line_clean = line.lower()
            if 'item:' in line_clean or 'shop:' in line_clean:
                for word in re.findall(r'[\w]{3,}', msg):
                    if word in line_clean:
                        return True

    return False


# ─── CHECK OLLAMA ONLINE ──────────────────────────────────────────────────────
def is_ollama_online() -> tuple[bool, str]:
    """Check if Ollama is reachable and return (is_online, model_name)."""
    try:
        r = requests.get(f"{Config.OLLAMA_URL}/api/tags", timeout=0.8)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if models:
                configured = Config.OLLAMA_MODEL
                cfg_base = configured.split(":")[0].lower()
                for m in models:
                    if m.split(":")[0].lower() == cfg_base or m == configured:
                        return True, m
                return True, models[0]
            return True, Config.OLLAMA_MODEL
    except Exception:
        pass
    return False, ""


# ─── PROMPT BUILDER ───────────────────────────────────────────────────────────
def _build_prompt(user_message: str, context: str, chat_history: list = None, lang: str = 'en') -> str:
    """Assemble system + history + user question into one prompt string."""
    lang_inst = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS['en'])
    sys_prompt = SYSTEM_PROMPT.format(context=context, lang_instruction=lang_inst)
    parts = [sys_prompt]
    if chat_history:
        for msg in chat_history[-6:]:
            role = "Customer" if msg["role"] == "user" else "EatStreet AI"
            parts.append(f"{role}: {msg['content']}")
    parts.append(f"Customer: {user_message}")
    parts.append("EatStreet AI:")
    return "\n".join(parts)


# ─── INTELLIGENT LOCAL DIRECT-ANSWER ENGINE ──────────────────────────────────
FOOD_PATTERNS = [
    (r'(?:biryani|biriyani|dum biryani|బిర్యాని|బిర్యానీ|बिरयानी)', 'biryani'),
    (r'(?:pakodi|pakoda|pakora|bhaji|bhajji|పకోడి|పకోడీ|భజ్జి|पकोड़ा|पकोड़ी|भजिया)', 'pakodi'),
    (r'(?:lollipop|lollipops|లాలీపాప్|లాఠీపాప్|लॉलीपॉप)', 'lollipop'),
    (r'(?:wing|wings|bbq wings|వింగ్స్|వिंग्स)', 'wings'),
    (r'(?:momo|momos|మోమోస్|మోమో|मोमोज|मोमो)', 'momos'),
    (r'(?:shawarma|shawarma plate|షవర్మా|షావర్మా|शवर्मा|शावर्मा)', 'shawarma'),
    (r'(?:waffle|waffles|వాఫుల్స్|వాఫుల్|वाफल्स|वाफल)', 'waffle'),
    (r'(?:shake|shakes|milkshake|షేక్|షేక్స్|मिल्कशेक|शेक)', 'shake'),
    (r'(?:ice cream|icecream|vanilla|ఐస్ క్రీమ్|ఐస్‌క్రీమ్|आइसक्रीम)', 'ice cream'),
    (r'(?:noodle|noodles|chowmein|నూడుల్స్|నూడిల్స్|नूडल्स|चाउमीन)', 'noodles'),
    (r'(?:fried rice|rice|ఫ్రైడ్ రైస్|రైస్|ఫ్రైడ్‌రైస్|चावल|फ्राइड राइस|राइस)', 'fried rice'),
    (r'(?:manchurian|మంచూరియా|మంచూరియన్|मंचूरियन)', 'manchurian'),
    (r'(?:spring roll|spring rolls|స్ప్రింగ్ రోల్స్|స్ప్రంగ్ రోల్|स्प्रिंग रोल)', 'spring rolls'),
    (r'(?:frankie|roll|rolls|ఫ్రాంకీ|రోల్స్|రోల్|फ्रैंकी|रोल)', 'frankie'),
    (r'(?:kabab|kebab|kebabs|seekh|కబాబ్|కబాబ్స్|సీక్|कबाब|सीख)', 'kabab'),
    (r'(?:tikka|malai tikka|టిక్కా|మలై టిక్కా|टिक्का|मलाई टिक्का)', 'tikka'),
    (r'(?:chaat|chat|చాట్|चाट)', 'chaat'),
    (r'(?:pani puri|panipuri|golgappa|పానీ పూరి|పానీపూరి|గోల్గప్పా|पानी पूरी|पानीपूरी|गोलगप्पा)', 'pani puri'),
    (r'(?:bhel puri|bhelpuri|భేల్ పూరి|భేల్‌పూరి|भेल पूरी|भेलपूरी)', 'bhel puri'),
    (r'(?:sev puri|sevpuri|సేవ్ పూరి|సేవ్‌పూరి|सेव पूरी|सेवपूरी)', 'sev puri'),
    (r'(?:samosa|samosas|సమోసా|సమోసాలు|समोसा|समोसे)', 'samosa'),
    (r'(?:chole bhature|bhature|చోలే భటూరే|భటూరే|छोले भटूरे|भटूरे)', 'chole bhature'),
    (r'(?:pottikalu|pottikkalu|పొట్టిక్కలు|పొట్టికలు|पोट्टीकलु)', 'pottikalu'),
    (r'(?:idly|idli|millet idly|ఇడ్లీ|మిల్లెట్ ఇడ్లీ|इडली)', 'idly'),
    (r'(?:ragi sangati|sangati|mudda|రాగి సంగటి|సంగటి|ముద్ద|रागी संगति)', 'ragi sangati'),
    (r'(?:natukodi|pulusu|నాటుకోడి|పులుసు|నాటుకోడి పులుసు|नाटुकॉडी)', 'natukodi pulusu'),
    (r'(?:mushroom|mushrooms|మష్రూమ్|మష్రూమ్స్|పుట్టగొడుగులు|मशरूम)', 'mushroom'),
    (r'(?:paneer|పనీర్|पनीर)', 'paneer'),
    (r'(?:egg|double egg|గుడ్డు|ఎగ్|అండా|अंडा|एग)', 'egg'),
    (r'(?:chicken|చికెన్|కోడి|चिकन|मुर्गा)', 'chicken'),
    (r'(?:mutton|మటన్|మేక|मटन|गोश्त)', 'mutton'),
    (r'(?:65|chicken 65|mushroom 65|చికెన్ 65|మష్రూమ్ 65|चिकन 65|मशरूम 65)', '65'),
]


def _parse_context_items(context: str) -> tuple[list, list]:
    """Parse raw RAG context into structured items and shops."""
    items = []
    shops = []
    current_shop = None

    for line in context.splitlines():
        line = line.strip()
        if line.startswith('SHOP:'):
            parts = line.replace('SHOP:', '').split('|')
            s_dict = {'name': parts[0]}
            for p in parts[1:]:
                if ':' in p:
                    k, v = p.split(':', 1)
                    s_dict[k.strip().lower()] = v.strip()
            shops.append(s_dict)
            current_shop = s_dict
        elif line.startswith('ITEM:'):
            parts = line.replace('ITEM:', '').split('|')
            iname_raw = parts[0].strip()
            price_raw = parts[1].strip() if len(parts) > 1 else 'Rs.0'
            vt_raw    = parts[2].strip() if len(parts) > 2 else '[V]'
            sname_raw = parts[3].replace('Shop:', '').strip() if len(parts) > 3 else (current_shop['name'] if current_shop else '')
            
            price_m = re.search(r'Rs\.(\d+)', price_raw)
            price = int(price_m.group(1)) if price_m else 0
            
            vt = 'veg' if '[V]' in vt_raw else ('egg' if '[E]' in vt_raw else 'non-veg')
            
            items.append({
                'name': iname_raw,
                'price': price,
                'veg': vt,
                'shop_name': sname_raw
            })
            
    return items, shops


def generate_smart_fallback(user_message: str, context: str = "", lang: str = "en") -> str:
    """
    Intelligent built-in assistant engine strictly grounded in database context.
    Provides precise, direct answers in the user's selected language (English, Telugu, Teluglish, Hindi).
    """
    msg = user_message.lower().strip()
    refusal_msg = SCOPE_REFUSAL_MESSAGES.get(lang, SCOPE_REFUSAL_MESSAGES['en'])

    # 1. Scope check
    if not is_relevant_query(user_message, context):
        return refusal_msg

    # 2. Greetings
    if re.match(r'^(hi|hello|hey|hola|namaste|greetings|good\s+(morning|afternoon|evening)|howdy|namaskaram)\b', msg) or msg in ['hi', 'hello', 'hey', 'namaste']:
        if lang == 'te':
            return (
                "👋 నమస్కారం! **కాకినాడ ఈట్ స్ట్రీట్** (@EATSTREET) కి స్వాగతం! 🍴\n\n"
                "నేను మీ ఈట్ స్ట్రీట్ AI సహాయకుడిని. మా మెనూ గురించి నన్ను నేరుగా ఏదైనా అడగండి:\n"
                "• 🍗 *\"చికెన్ లాలీపాప్ ధర ఎంత?\"* లేదా *\"చికెన్ వింగ్స్ కాంబోస్\"*\n"
                "• 🥦 *\"వెజ్ పకోడి ధర\"* లేదా *\"మష్రూమ్ 65\"*\n"
                "• 🍚 *\"బిర్యానీ రకాలు మరియు రేట్లు\"*\n"
                "• 🥟 *\"మోమోస్ / షవర్మా / వాఫుల్స్\"*\n"
                "• 🪑 *\"4 మందికి టేబుల్ బుకింగ్\"*\n\n"
                "మీకు ఏ వివరాలు కావాలో అడగండి!"
            )
        elif lang == 'teluglish':
            return (
                "👋 Namaste! **@EATSTREET Kakinada** ki swagatham! 🍴\n\n"
                "Nenu mee Eat Street food assistant. Mana menu gurinchi edaina adagandi:\n"
                "• 🍗 *\"Chicken lollipop price entha?\"* leda *\"Chicken wings combos\"*\n"
                "• 🥦 *\"Veg pakodi rate\"* leda *\"Mushroom 65\"*\n"
                "• 🍚 *\"Biryani varieties and rates\"*\n"
                "• 🥟 *\"Momos / Shawarma / Waffles\"*\n"
                "• 🪑 *\"Book a table for 4 persons\"*\n\n"
                "Miku em details kavali?"
            )
        elif lang == 'hi':
            return (
                "👋 नमस्ते! **काकीनाडा ईट स्ट्रीट** (@EATSTREET) में आपका स्वागत है! 🍴\n\n"
                "मैं आपका ईट स्ट्रीट फूड असिस्टेंट हूँ। हमारे मेनू के बारे में कुछ भी पूछें:\n"
                "• 🍗 *\"चिकन लॉलीपॉप की कीमत\"* या *\"चिकन विंग्स कॉम्बो\"*\n"
                "• 🥦 *\"वेज पकोड़ी की कीमत\"* या *\"मशरूम 65\"*\n"
                "• 🍚 *\"बिरयानी की किस्में और दाम\"*\n"
                "• 🥟 *\"मोमोज / शवर्मा / वाफल्स\"*\n"
                "• 🪑 *\"4 लोगों के लिए टेबल बुकिंग\"*\n\n"
                "आप क्या जानना चाहते हैं?"
            )
        else:
            return (
                "👋 Hello! Welcome to **@EATSTREET Kakinada** — *The Taste of Kakinada*! 🍴\n\n"
                "I'm your Eat Street food assistant. Ask me anything directly about our menu:\n"
                "• 🍗 *\"Chicken lollipop price\"* or *\"Chicken wings combos\"*\n"
                "• 🥦 *\"Veg pakodi price\"* or *\"Mushroom 65\"*\n"
                "• 🍚 *\"Biryani varieties and rates\"*\n"
                "• 🥟 *\"Momos / Shawarma / Waffles\"*\n"
                "• 🪑 *\"Book a table for 4 persons\"*\n\n"
                "What would you like to know today?"
            )

    # 3. Table Booking / Dine-In / QR
    if any(w in msg for w in ['table', 'book', 'reserve', 'dine in', 'dine-in', 'qr', 'seat', 'seating', 'టేబుల్', 'బుకింగ్', 'రిజర్వేషన్', 'డైన్-ఇన్', 'టేబుల్స్', 'टेबल', 'बुकिंग', 'बुक', 'रिजर्वेशन', 'डाइन-इन']):
        if lang == 'te':
            return (
                "🪑 **కాకినాడ ఈట్ స్ట్రీట్ లో స్మార్ట్ టేబుల్ రిజర్వేషన్:**\n\n"
                "మీరు తేదీ, సమయం, వ్యక్తుల సంఖ్య (2, 4, 6, 8), మరియు సీటింగ్ ప్రిఫరెన్స్ (*విండో, ఎంట్రన్స్ దగ్గర, ఫ్యామిలీ ఏరియా, ప్రశాంతమైన ఏరియా*) ఎంచుకుని బుక్ చేసుకోవచ్చు:\n"
                "• 🍗 **Chicken Corner** (⭐ 4.3 — ఫాస్ట్ ఫుడ్ & క్రిస్పీ చికెన్)\n"
                "• 🍔 **Fast Food Plaza** (⭐ 4.2 — నూడుల్స్ & ఫ్రైడ్ రైస్)\n"
                "• 🍢 **Bullet BBQ** (⭐ 4.6 — తందూరి & బార్బెక్యూ ప్లాటర్స్)\n"
                "• 🍚 **Biryani House** (⭐ 4.5 — దమ్ బిర్యానీలు)\n"
                "• 🧇 **Waffle World** (⭐ 4.4 — వాఫుల్స్ & షేక్స్)\n\n"
                "👉 లైవ్ లభ్యతతో స్లాట్ ఎంచుకోవడానికి **Book Table** పేజీని సందర్శించండి!"
            )
        elif lang == 'teluglish':
            return (
                "🪑 **Eat Street Kakinada Smart Table Reservation:**\n\n"
                "Miku kavalasina Date, Time, Person Count (2, 4, 6, 8) mariyu Seating Preference select chesukoni table book chesukovachu:\n"
                "• 🍗 **Chicken Corner** (⭐ 4.3 — Crispy Chicken & Snacks)\n"
                "• 🍔 **Fast Food Plaza** (⭐ 4.2 — Noodles & Fried Rice)\n"
                "• 🍢 **Bullet BBQ** (⭐ 4.6 — Tandoori & BBQ Platters)\n"
                "• 🍚 **Biryani House** (⭐ 4.5 — Dum Biryani varieties)\n"
                "• 🧇 **Waffle World** (⭐ 4.4 — Belgian Waffles & Shakes)\n\n"
                "👉 Real-time table booking kosam **Book Table** tab open cheyandi!"
            )
        elif lang == 'hi':
            return (
                "🪑 **काकीनाडा ईट स्ट्रीट में स्मार्ट टेबल बुकिंग:**\n\n"
                "आप तारीख, समय, लोगों की संख्या (2, 4, 6, 8) और सीटिंग प्राथमिकता के अनुसार टेबल बुक कर सकते हैं:\n"
                "• 🍗 **Chicken Corner** (⭐ 4.3 — क्रिस्पी चिकन)\n"
                "• 🍔 **Fast Food Plaza** (⭐ 4.2 — नूडल्स और फ्राइड राइस)\n"
                "• 🍢 **Bullet BBQ** (⭐ 4.6 — तंदूरी और बारबेक्यू)\n"
                "• 🍚 **Biryani House** (⭐ 4.5 — दम बिरयानी)\n"
                "• 🧇 **Waffle World** (⭐ 4.4 — वाफल्स और शेक्स)\n\n"
                "👉 रियल-टाइम टेबल बुकिंग के लिए **Book Table** टैब पर जाएँ!"
            )
        else:
            return (
                "🪑 **Smart Table Reservation at Eat Street Kakinada:**\n\n"
                "You can reserve tables by Date, Time, Person Count (2, 4, 6, 8), and Seating Preference (*Window, Near entrance, Family area, Quiet area*) at:\n"
                "• 🍗 **Chicken Corner** (⭐ 4.3 — Fast Food & Crispy Chicken)\n"
                "• 🍔 **Fast Food Plaza** (⭐ 4.2 — Noodles & Fried Rice)\n"
                "• 🍢 **Bullet BBQ** (⭐ 4.6 — Tandoori & BBQ Platters)\n"
                "• 🍚 **Biryani House** (⭐ 4.5 — Dum Biryanis)\n"
                "• 🧇 **Waffle World** (⭐ 4.4 — Waffles & Shakes)\n\n"
                "👉 Visit the **Book Table** tab to pick your time slot with real-time availability!"
            )

    # 4. Best / Top Rated Shops
    if any(w in msg for w in ['best rated', 'top rated', 'highest rated', 'popular shop', 'best shop', 'all shops', 'list shops', 'stalls', 'shops', 'స్టాల్స్', 'షాపులు', 'షాపు', 'స్టాల్', 'दुकानें', 'स्टॉल्स', 'दुकान']):
        if lang == 'te':
            return (
                "⭐ **కాకినాడ ఈట్ స్ట్రీట్ స్టాల్స్ & స్పెషాలిటీస్:**\n\n"
                "1. 🍢 **Bullet BBQ** (⭐ 4.6) — బార్బెక్యూ వింగ్స్, సీక్ కబాబ్స్\n"
                "2. 🍚 **Biryani House** (⭐ 4.5) — చికెన్ & మటన్ దమ్ బిర్యానీలు\n"
                "3. 🥟 **Momos & More** (⭐ 4.5) — స్టీమ్డ్, ఫ్రైడ్ మరియు తందూరి మోమోస్\n"
                "4. 🌯 **Shawarma Street** (⭐ 4.4) — చికెన్, ఎగ్ & పనీర్ షవర్మాస్\n"
                "5. 🧇 **Waffle World** (⭐ 4.4) — బెల్జియం చాక్లెట్ వాఫుల్స్ & మిల్క్‌షేక్స్\n"
                "6. 🍗 **Chicken Corner** (⭐ 4.3) — చికెన్ లాలీపాప్స్, వింగ్స్ & కాంబోస్\n"
                "7. 🍲 **Mushroom Magic** (⭐ 4.3) — 100% వెజ్ పకోడీలు & మష్రూమ్ 65\n"
                "8. 🥪 **Frankie Corner** (⭐ 4.2) — ఎగ్, చికెన్ & పనీర్ రోల్స్\n"
                "9. 🍜 **Fast Food Plaza** (⭐ 4.2) — నూడుల్స్, ఫ్రైడ్ రైస్ & మంచూరియా\n"
                "10. 🧆 **Chaat & Chat** (⭐ 4.3) — పానీ పూరి, భేల్, పొట్టిక్కలు & సమోసాలు\n\n"
                "📍 **లొకేషన్:** రామా రావు పేట, కాకినాడ · 🕐 **సమయం:** 11:00 AM – 11:00 PM"
            )
        elif lang == 'teluglish':
            return (
                "⭐ **Eat Street Kakinada Top Stalls & Specialities:**\n\n"
                "1. 🍢 **Bullet BBQ** (⭐ 4.6) — Smoky BBQ wings, Seekh Kebabs\n"
                "2. 🍚 **Biryani House** (⭐ 4.5) — Dum Biryani varieties\n"
                "3. 🥟 **Momos & More** (⭐ 4.5) — Steamed, Fried & Tandoor Momos\n"
                "4. 🌯 **Shawarma Street** (⭐ 4.4) — Chicken, Egg & Paneer Shawarma\n"
                "5. 🧇 **Waffle World** (⭐ 4.4) — Belgian Waffles & Milkshakes\n"
                "6. 🍗 **Chicken Corner** (⭐ 4.3) — Chicken Lollipops, Wings & Combos\n"
                "7. 🍲 **Mushroom Magic** (⭐ 4.3) — 100% Veg Pakodi & Mushroom 65\n"
                "8. 🥪 **Frankie Corner** (⭐ 4.2) — Rolls & Frankies\n"
                "9. 🍜 **Fast Food Plaza** (⭐ 4.2) — Noodles, Fried Rice & Manchurian\n"
                "10. 🧆 **Chaat & Chat** (⭐ 4.3) — Pani Puri, Pottikalu & Snacks\n\n"
                "📍 **Location:** Rama Rao Peta, Kakinada · 🕐 **Timings:** 11:00 AM – 11:00 PM"
            )
        elif lang == 'hi':
            return (
                "⭐ **काकीनाडा ईट स्ट्रीट की प्रमुख दुकानें व विशेषताएँ:**\n\n"
                "1. 🍢 **Bullet BBQ** (⭐ 4.6) — बारबेक्यू विंग्स, कबाब व प्लेटर\n"
                "2. 🍚 **Biryani House** (⭐ 4.5) — चिकन और मटन दम बिरयानी\n"
                "3. 🥟 **Momos & More** (⭐ 4.5) — स्टीम्ड, फ्राइड और तंदूरी मोमोज\n"
                "4. 🌯 **Shawarma Street** (⭐ 4.4) — चिकन, एग और पनीर शवर्मा\n"
                "5. 🧇 **Waffle World** (⭐ 4.4) — चॉकलेट वाफल्स और मिल्कशेक\n"
                "6. 🍗 **Chicken Corner** (⭐ 4.3) — चिकन लॉलीपॉप और विंग्स\n"
                "7. 🍲 **Mushroom Magic** (⭐ 4.3) — 100% वेज पकोड़े और मशरूम 65\n"
                "8. 🥪 **Frankie Corner** (⭐ 4.2) — एग, चिकन और पनीर रोल्स\n"
                "9. 🍜 **Fast Food Plaza** (⭐ 4.2) — नूडल्स, फ्राइड राइस और मंचूरियन\n"
                "10. 🧆 **Chaat & Chat** (⭐ 4.3) — पानी पूरी, भेल और समोसे\n\n"
                "📍 **स्थान:** रामा राव पेटा, काकीनाडा · 🕐 **समय:** 11:00 AM – 11:00 PM"
            )
        else:
            return (
                "⭐ **Stalls & Specialities at Eat Street Kakinada:**\n\n"
                "1. 🍢 **Bullet BBQ** (⭐ 4.6) — Smoky BBQ wings, Seekh Kebabs & Platters\n"
                "2. 🍚 **Biryani House** (⭐ 4.5) — Chicken & Mutton Dum Biryanis\n"
                "3. 🥟 **Momos & More** (⭐ 4.5) — Steamed, Fried, and Tandoor Momos\n"
                "4. 🌯 **Shawarma Street** (⭐ 4.4) — Chicken, Egg & Paneer Shawarmas\n"
                "5. 🧇 **Waffle World** (⭐ 4.4) — Belgian Chocolate Waffles & Milkshakes\n"
                "6. 🍗 **Chicken Corner** (⭐ 4.3) — Chicken Lollipops, Wings & Combos\n"
                "7. 🍲 **Mushroom Magic** (⭐ 4.3) — 100% Veg Pakodis, Fry & Mushroom 65\n"
                "8. 🥪 **Frankie Corner** (⭐ 4.2) — Egg, Chicken & Paneer Rolls\n"
                "9. 🍜 **Fast Food Plaza** (⭐ 4.2) — Noodles, Fried Rice & Manchurian\n"
                "10. 🧆 **Chaat & Chat** (⭐ 4.3) — Pani Puri, Bhel, Pottikalu & Samosas\n\n"
                "📍 **Location:** Rama Rao Peta, Kakinada (533001) · 🕐 **Timings:** 11:00 AM – 11:00 PM"
            )

    items, shops = _parse_context_items(context)
    if not items:
        if lang == 'te':
            return "🍽️ కాకినాడ ఈట్ స్ట్రీట్ కి స్వాగతం! రామా రావు పేట, కాకినాడ లో బిర్యానీ, బార్బెక్యూ, మోమోస్, షవర్మా, వాఫుల్స్ అందుబాటులో ఉన్నాయి."
        elif lang == 'teluglish':
            return "🍽️ Kakinada Eat Street ki swagatham! Biryani, BBQ, Momos, Shawarma, Waffles Rama Rao Peta lo dorukutayi."
        elif lang == 'hi':
            return "🍽️ काकीनाडा ईट स्ट्रीट में आपका स्वागत है! बिरयानी, बारबेक्यू, मोमोज, शवर्मा और वाफल्स उपलब्ध हैं।"
        else:
            return "🍽️ Welcome to Kakinada Eat Street! We offer Biryani, BBQ, Momos, Shawarma, Waffles, Chaat, and Pakodis at Rama Rao Peta, Kakinada (11:00 AM – 11:00 PM)."

    # 5. Budget / Price Filtering (e.g. "under 100", "under Rs 50", "₹100 లోపు", "₹100 के अंदर")
    budget_match = (
        re.search(r'(?:under|below|less than|<|within|లోపు|lopala|అండర్|వరకు|के अंदर|से कम|तक)\s*(?:rs\.?|inr|₹)?\s*(\d+)', msg) or
        re.search(r'(?:rs\.?|inr|₹)?\s*(\d+)\s*(?:under|below|less than|<|within|లోపు|lopala|అండర్|వరకు|రూపాయల లోపు|రూపాయలు లోపు|రూ\.?\s*లోపు|రూ\b|కే అందర్|సె కమ్|के अंदर|से कम|तक)', msg) or
        re.search(r'(\d+)\s*(?:రూ|రూపాయలు|rs|inr|₹)\s*(?:లోపు|lopala|వరకు|के अंदर|से कम)', msg)
    )
    is_veg_req = (
        'veg' in msg or 'vegetarian' in msg or 'వెజ్' in msg or 'శాకాహార' in msg or 'శాకాహారి' in msg
        or 'शाकाहारी' in msg or 'वेज' in msg
    ) and not any(nw in msg for nw in ['non', 'nonveg', 'non-veg', 'నాన్', 'మాంసాహార', 'మాంసం', 'नॉन', 'मांसाहारी', 'मांसाहार'])

    is_nonveg_req = (
        'nonveg' in msg or 'non-veg' in msg or ('non' in msg and 'veg' in msg)
        or 'నాన్' in msg or 'నాన్‌వెజ్' in msg or 'మాంసాహార' in msg or 'మాంసం' in msg
        or 'नॉन' in msg or 'मांसाहारी' in msg or 'मांसाहार' in msg or 'చికెన్' in msg or 'మటన్' in msg
    )

    if budget_match:
        limit = int(budget_match.group(1))
        budget_items = []
        for it in items:
            if it['price'] <= limit:
                if is_veg_req and it['veg'] != 'veg':
                    continue
                if is_nonveg_req and it['veg'] != 'non-veg':
                    continue
                type_str = "🥦 Veg" if it['veg'] == 'veg' else ("🥚 Egg" if it['veg'] == 'egg' else "🍗 Non-Veg")
                budget_items.append(f"• **{it['name']}** — ₹{it['price']} ({type_str}) — *{it['shop_name']}*")
        
        if budget_items:
            sample = budget_items[:8]
            if lang == 'te':
                diet_label = "వెజిటేరియన్ " if is_veg_req else ("నాన్-వెజ్ " if is_nonveg_req else "")
                return (
                    f"💰 **కాకినాడ ఈట్ స్ట్రీట్ లో ₹{limit} లోపు లభించే {diet_label}ఐటమ్స్:**\n\n" +
                    "\n".join(sample) +
                    f"\n\n✨ మొత్తం {len(budget_items)} ఐటమ్స్ అందుబాటులో ఉన్నాయి!"
                )
            elif lang == 'teluglish':
                diet_label = "Veg " if is_veg_req else ("Non-Veg " if is_nonveg_req else "")
                return (
                    f"💰 **Eat Street lo ₹{limit} lopala unna {diet_label}items:**\n\n" +
                    "\n".join(sample) +
                    f"\n\n✨ Total {len(budget_items)} items unnay!"
                )
            elif lang == 'hi':
                diet_label = "शाकाहारी " if is_veg_req else ("मांसाहारी " if is_nonveg_req else "")
                return (
                    f"💰 **काकीनाडा ईट स्ट्रीट में ₹{limit} के अंदर {diet_label}व्यंजन:**\n\n" +
                    "\n".join(sample) +
                    f"\n\n✨ कुल {len(budget_items)} व्यंजन उपलब्ध हैं!"
                )
            else:
                diet_label = "Vegetarian " if is_veg_req else ("Non-Veg " if is_nonveg_req else "")
                return (
                    f"💰 **{diet_label}Dishes under ₹{limit} at Eat Street:**\n\n" +
                    "\n".join(sample) +
                    f"\n\n✨ Total {len(budget_items)} items available under ₹{limit} across stalls!"
                )
        else:
            if lang == 'te':
                return f"₹{limit} లోపు సరిపోయే వంటకాలు ప్రస్తుతం లేవు. మరిన్ని స్నాక్స్ కోసం ₹150 లోపు చూడండి!"
            elif lang == 'teluglish':
                return f"₹{limit} lopala items match avvaledu. Snacks kosam ₹150 lopala try cheyandi!"
            elif lang == 'hi':
                return f"₹{limit} के अंदर कोई व्यंजन उपलब्ध नहीं है। कृपया ₹150 के अंदर प्रयास करें!"
            else:
                return f"We don't have dishes under ₹{limit} matching your criteria. Try searching under ₹150 for delicious snack & meal options!"

    # 6. Specific Food Tag / Noun Detection
    matched_tags = []
    for pattern, tag in FOOD_PATTERNS:
        if re.search(pattern, msg):
            matched_tags.append(tag)

    broad_tags = {'chicken', 'mutton', 'egg', 'paneer', 'mushroom', 'fried rice', 'rice'}
    specific_tags = [t for t in matched_tags if t not in broad_tags]
    primary_tag = specific_tags[0] if specific_tags else (matched_tags[0] if matched_tags else None)

    matched_dishes = []
    for item in items:
        iname = item['name'].lower()
        sname = item['shop_name'].lower()

        if is_veg_req and item['veg'] != 'veg':
            continue
        if is_nonveg_req and item['veg'] != 'non-veg':
            continue

        score = 0
        if primary_tag:
            tag_regex = next((pat for pat, tag in FOOD_PATTERNS if tag == primary_tag), primary_tag)
            if re.search(tag_regex, iname):
                score += 100
            elif primary_tag in iname:
                score += 80
            else:
                continue

            for st in matched_tags:
                if st != primary_tag and (st in iname or st in sname):
                    score += 30
        else:
            tokens = re.findall(r'[a-zA-Z0-9]+', msg)
            for tok in tokens:
                if len(tok) > 2 and (tok in iname or tok in sname):
                    score += 20
            if score == 0:
                continue

        matched_dishes.append((score, item))

    matched_dishes.sort(key=lambda x: x[0], reverse=True)
    results = [x[1] for x in matched_dishes]

    # If direct matching dishes are found
    if results:
        shop_groups = defaultdict(list)
        for it in results:
            shop_groups[it['shop_name']].append(it)

        # Lollipops
        if primary_tag == 'lollipop':
            top = results[0]
            combos = [r for r in results if 'combo' in r['name'].lower()]
            if lang == 'te':
                reply = (
                    f"🍗 **{top['name']} (చికెన్ లాలీపాప్)** వివరాలు:\n\n"
                    f"• **ధర:** **₹{top['price']}**\n"
                    f"• **స్టాల్:** **{top['shop_name']}** (⭐ 4.3)\n"
                    f"• **లొకేషన్:** రామా రావు పేట, కాకినాడ (11:00 AM – 11:00 PM)\n"
                )
                if combos:
                    reply += "\n🔥 **లాలీపాప్ కాంబో ఆఫర్స్:**\n"
                    for c in combos:
                        reply += f"• **{c['name']}** — ₹{c['price']}\n"
                reply += "\n😋 టేక్‌అవే/డెలివరీ లేదా డైన్-ఇన్ కోసం ఆన్‌లైన్‌లో ఆర్డర్ చేయండి!"
                return reply
            elif lang == 'teluglish':
                reply = (
                    f"🍗 **{top['name']}** details:\n\n"
                    f"• **Price:** **₹{top['price']}**\n"
                    f"• **Stall:** **{top['shop_name']}** (⭐ 4.3)\n"
                    f"• **Location:** Rama Rao Peta, Kakinada (11:00 AM – 11:00 PM)\n"
                )
                if combos:
                    reply += "\n🔥 **Combo Deals with Lollipops:**\n"
                    for c in combos:
                        reply += f"• **{c['name']}** — ₹{c['price']}\n"
                reply += "\n😋 Online lo order chesukondi leda table book cheyandi!"
                return reply
            elif lang == 'hi':
                reply = (
                    f"🍗 **{top['name']} (चिकन लॉलीपॉप)** का विवरण:\n\n"
                    f"• **कीमत:** **₹{top['price']}**\n"
                    f"• **दुकान:** **{top['shop_name']}** (⭐ 4.3)\n"
                    f"• **स्थान:** रामा राव पेटा, काकीनाडा (11:00 AM – 11:00 PM)\n"
                )
                if combos:
                    reply += "\n🔥 **कॉम्बो डील्स:**\n"
                    for c in combos:
                        reply += f"• **{c['name']}** — ₹{c['price']}\n"
                reply += "\n😋 ऑनलाइन ऑर्डर करें या टेबल बुक करें!"
                return reply
            else:
                reply = (
                    f"🍗 **{top['name']}** at Kakinada Eat Street:\n\n"
                    f"• **Price:** **₹{top['price']}**\n"
                    f"• **Stall:** **{top['shop_name']}** (⭐ 4.3)\n"
                    f"• **Location:** Rama Rao Peta, Kakinada (Open 11:00 AM – 11:00 PM)\n"
                )
                if combos:
                    reply += "\n🔥 **Combo Deals with Lollipops:**\n"
                    for c in combos:
                        reply += f"• **{c['name']}** — ₹{c['price']}\n"
                reply += "\n😋 Order online for takeaway/delivery or reserve a table to dine in!"
                return reply

        # Pakodi
        if primary_tag == 'pakodi':
            if lang == 'te':
                reply = "🥦 **కాకినాడ ఈట్ స్ట్రీట్ లో వెజ్ పకోడి రకాలు & ధరలు:**\n\n"
                reply += "**Mushroom Magic** (100% శాకాహార స్టాల్) లో లభించేవి:\n"
                for it in results:
                    reply += f"• **{it['name']}** — **₹{it['price']}** (🥦 వెజ్)\n"
                reply += "\n✨ వేడి వేడిగా, క్రిస్పీగా తయారుచేయబడుతుంది!"
                return reply
            elif lang == 'teluglish':
                reply = "🥦 **Veg Pakodi Varieties & Prices at Eat Street:**\n\n"
                reply += "**Mushroom Magic** (100% Veg Stall) lo unnay:\n"
                for it in results:
                    reply += f"• **{it['name']}** — **₹{it['price']}** (🥦 Veg)\n"
                reply += "\n✨ Hot and crispy snacks!"
                return reply
            elif lang == 'hi':
                reply = "🥦 **वेज पकोड़ी की किस्में और दाम:**\n\n"
                reply += "**Mushroom Magic** (100% शाकाहारी दुकान) पर उपलब्ध:\n"
                for it in results:
                    reply += f"• **{it['name']}** — **₹{it['price']}** (🥦 वेज)\n"
                reply += "\n✨ गरमा-गरम और क्रिस्पी स्नैक्स!"
                return reply
            else:
                reply = "🥦 **Veg Pakodi Varieties & Prices at Eat Street:**\n\n"
                reply += "Available at **Mushroom Magic** (100% Vegetarian Stall):\n"
                for it in results:
                    reply += f"• **{it['name']}** — **₹{it['price']}** (🥦 Veg)\n"
                reply += "\n✨ Freshly prepared hot & crispy! Perfect evening snack."
                return reply

        # Biryani
        if primary_tag == 'biryani':
            if lang == 'te':
                reply = "🍚 **ఈట్ స్ట్రీట్ లో బిర్యానీ రకాలు & ధరలు:**\n\n"
                reply += "**Biryani House** (⭐ 4.5) లో లభించేవి:\n"
                for it in results[:7]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else "🍗"
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n😋 కాకినాడ దమ్ స్టైల్ లో రైతా & సాలన్‌తో వడ్డించబడుతుంది!"
                return reply
            elif lang == 'teluglish':
                reply = "🍚 **Biryani Varieties & Prices at Eat Street:**\n\n"
                reply += "**Biryani House** (⭐ 4.5) lo unnay:\n"
                for it in results[:7]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else "🍗"
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n😋 Kakinada dum style biryani served with raita & salan!"
                return reply
            elif lang == 'hi':
                reply = "🍚 **बिरयानी की किस्में और दाम:**\n\n"
                reply += "**Biryani House** (⭐ 4.5) पर उपलब्ध:\n"
                for it in results[:7]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else "🍗"
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n😋 रायता और सालन के साथ परोसी जाती है!"
                return reply
            else:
                reply = "🍚 **Biryani Varieties & Prices at Eat Street:**\n\n"
                reply += "Available at **Biryani House** (⭐ 4.5):\n"
                for it in results[:7]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else "🍗"
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n😋 Authentic Kakinada dum style biryani served hot with raita & salan!"
                return reply

        # Generic multi-item direct answer
        query_title = primary_tag.title() if primary_tag else "Matching"
        if lang == 'te':
            reply = f"🍴 **{query_title} వంటకాలు & ధరలు:**\n\n"
            for sname, sitems in shop_groups.items():
                reply += f"🏪 **{sname}:**\n"
                for it in sitems[:5]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else ("🥚" if it['veg'] == 'egg' else "🍗")
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n"
            reply += "📍 రామా రావు పేట, కాకినాడ · డైన్-ఇన్, టేక్‌అవే & డెలివరీలో లభ్యం!"
            return reply.strip()
        elif lang == 'teluglish':
            reply = f"🍴 **{query_title} Dishes & Rates at Eat Street:**\n\n"
            for sname, sitems in shop_groups.items():
                reply += f"🏪 **{sname}:**\n"
                for it in sitems[:5]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else ("🥚" if it['veg'] == 'egg' else "🍗")
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n"
            reply += "📍 Rama Rao Peta, Kakinada · Available for Dine-In, Takeaway & Delivery!"
            return reply.strip()
        elif lang == 'hi':
            reply = f"🍴 **{query_title} व्यंजन और दाम:**\n\n"
            for sname, sitems in shop_groups.items():
                reply += f"🏪 **{sname}:**\n"
                for it in sitems[:5]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else ("🥚" if it['veg'] == 'egg' else "🍗")
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n"
            reply += "📍 रामा राव पेटा, काकीनाडा · डाइन-इन, टेकअवे और डिलीवरी उपलब्ध!"
            return reply.strip()
        else:
            reply = f"🍴 **{query_title} Dishes & Prices at Eat Street:**\n\n"
            for sname, sitems in shop_groups.items():
                reply += f"🏪 **{sname}:**\n"
                for it in sitems[:5]:
                    vt_icon = "🥦" if it['veg'] == 'veg' else ("🥚" if it['veg'] == 'egg' else "🍗")
                    reply += f"• **{it['name']}** — **₹{it['price']}** ({vt_icon} {it['veg'].title()})\n"
                reply += "\n"
            reply += "📍 Rama Rao Peta, Kakinada · Available for Dine-In, Takeaway & Delivery!"
            return reply.strip()

    # 7. Unmatched food query (food not available in Eat Street)
    stop_words = {
        'what', 'which', 'show', 'food', 'dishes', 'item', 'items', 'available', 'have', 'tell', 'about', 'some', 'give',
        'want', 'like', 'need', 'kakinada', 'eatstreet', 'street', 'please', 'there', 'with', 'you', 'can', 'get', 'the',
        'and', 'for', 'are', 'any', 'does', 'menu', 'price', 'cost', 'near',
        'ఉందా', 'ఉన్నాయా', 'లభిస్తుందా', 'దొరుకుతుందా', 'చెప్పు', 'చూపించు', 'కావాలి', 'ఏమిటి', 'ధర', 'ఎంత', 'లేదా', 'ఉంది', 'అందుబాటులో',
        'क्या', 'उपलब्ध', 'है', 'बताओ', 'दिखाओ', 'चाहिए', 'कीमत', 'दाम', 'रुपये', 'या', 'उपलब्धता', 'मिलती', 'मिलता'
    }
    tokens = [w.strip('.,?!₹"\'()[]{}<>-:;!@#$%^&*') for w in msg.split() if w.strip()]
    tokens = [w for w in tokens if w and w.lower() not in stop_words and len(w) > 1]
    term_str = " ".join(tokens) if tokens else ("మీరు అడిగిన వంటకం" if lang == 'te' else ("आपका पसंदीदा व्यंजन" if lang == 'hi' else "the requested dish"))

    if lang == 'te':
        return (
            f"❌ క్షమించండి, **{term_str}** ప్రస్తుతానికి కాకినాడ ఈట్ స్ట్రీట్ లో అందుబాటులో లేదు.\n\n"
            f"మా స్టాల్స్ లో లభించే ఇతర ముఖ్యమైన వంటకాలు:\n"
            f"• 🍗 **చికెన్ లాలీపాప్స్** — ₹120 *(Chicken Corner)*\n"
            f"• 🍚 **చికెన్ దమ్ బిర్యానీ** — ₹180 *(Biryani House)*\n"
            f"• 🍢 **స్మోకీ బార్బెక్యూ వింగ్స్** — ₹130 *(Bullet BBQ)*\n"
            f"• 🥟 **చికెన్ మోమోస్** — ₹90 *(Momos & More)*\n"
            f"• 🌯 **చికెన్ షవర్మా** — ₹80 *(Shawarma Street)*\n"
            f"• 🧇 **చాక్లెట్ వాఫుల్** — ₹100 *(Waffle World)*\n"
            f"• 🍲 **మష్రూమ్ పకోడి / 65** — ₹70–₹90 *(Mushroom Magic - వెజ్)*\n\n"
            f"ఏదైనా స్టాల్ మెనూ లేదా ధరల కోసం అడగవచ్చు!"
        )
    elif lang == 'teluglish':
        return (
            f"❌ Sorry, **{term_str}** ippudu Kakinada Eat Street lo ledu.\n\n"
            f"Mana stalls lo popular items unnay:\n"
            f"• 🍗 **Chicken Lollipops** — ₹120 *(Chicken Corner)*\n"
            f"• 🍚 **Chicken Dum Biryani** — ₹180 *(Biryani House)*\n"
            f"• 🍢 **Smoky BBQ Chicken Wings** — ₹130 *(Bullet BBQ)*\n"
            f"• 🥟 **Chicken Momos** — ₹90 *(Momos & More)*\n"
            f"• 🌯 **Chicken Shawarma** — ₹80 *(Shawarma Street)*\n"
            f"• 🧇 **Chocolate Waffle** — ₹100 *(Waffle World)*\n"
            f"• 🍲 **Mushroom Pakodi / 65** — ₹70–₹90 *(Mushroom Magic - Veg)*\n\n"
            f"Miku kavalasina stall menu prices gurinchi adagandi!"
        )
    elif lang == 'hi':
        return (
            f"❌ क्षमा करें, **{term_str}** वर्तमान में काकीनाडा ईट स्ट्रीट पर उपलब्ध नहीं है।\n\n"
            f"हमारी दुकानों पर लोकप्रिय व्यंजन:\n"
            f"• 🍗 **चिकन लॉलीपॉप** — ₹120 *(Chicken Corner)*\n"
            f"• 🍚 **चिकन दम बिरयानी** — ₹180 *(Biryani House)*\n"
            f"• 🍢 **बारबेक्यू चिकन विंग्स** — ₹130 *(Bullet BBQ)*\n"
            f"• 🥟 **चिकन मोमोज** — ₹90 *(Momos & More)*\n"
            f"• 🌯 **चिकन शवर्मा** — ₹80 *(Shawarma Street)*\n"
            f"• 🧇 **चॉकलेट वाफल** — ₹100 *(Waffle World)*\n"
            f"• 🍲 **मशरूम पकोड़ा / 65** — ₹70–₹90 *(Mushroom Magic - वेज)*\n\n"
            f"आप किसी भी दुकान के मेनू या कीमत के बारे में पूछ सकते हैं!"
        )
    else:
        return (
            f"❌ Sorry, **{term_str}** is not currently available at Kakinada Eat Street.\n\n"
            f"Here are popular specialties available at our stalls:\n"
            f"• 🍗 **Chicken Lollipops** — ₹120 *(Chicken Corner)*\n"
            f"• 🍚 **Chicken Dum Biryani** — ₹180 *(Biryani House)*\n"
            f"• 🍢 **Smoky BBQ Chicken Wings** — ₹130 *(Bullet BBQ)*\n"
            f"• 🥟 **Steamed Chicken Momos** — ₹90 *(Momos & More)*\n"
            f"• 🌯 **Chicken Shawarma** — ₹80 *(Shawarma Street)*\n"
            f"• 🧇 **Chocolate Waffle** — ₹100 *(Waffle World)*\n"
            f"• 🍲 **Mushroom Pakodi / 65** — ₹70–₹90 *(Mushroom Magic - Veg)*\n\n"
            f"Feel free to ask for any stall menu or dish prices!"
        )


# ─── STREAMING GENERATOR ──────────────────────────────────────────────────────
def stream_ollama(user_message: str, context: str, chat_history: list = None, lang: str = "en"):
    """
    Generator that yields text tokens as they arrive.
    Enforces scope check first. If unrelated, returns the refusal message in selected language.
    Uses Ollama if online; falls back to smart local assistant engine.
    """
    refusal_msg = SCOPE_REFUSAL_MESSAGES.get(lang, SCOPE_REFUSAL_MESSAGES['en'])

    # 1. Immediate scope classification
    if not is_relevant_query(user_message, context):
        for word in re.split(r'(\s+)', refusal_msg):
            if word:
                yield word
                time.sleep(0.01)
        return

    # 2. If Ollama is available, stream from Ollama model
    online, model = is_ollama_online()

    if online:
        prompt = _build_prompt(user_message, context, chat_history, lang=lang)
        payload = {
            "model":  model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.5,
                "top_p":       0.9,
                "num_predict": 300,
                "stop":        ["Customer:", "\nCustomer:"],
            },
        }

        try:
            with requests.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json=payload,
                stream=True,
                timeout=(2, 120),
            ) as resp:
                if resp.status_code == 200:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
                            if chunk.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
                    return
        except Exception:
            pass  # Fall through to smart fallback engine

    # 3. Fallback assistant response
    reply = generate_smart_fallback(user_message, context, lang=lang)
    
    # Stream the reply word-by-word with small delay for natural typing feel
    words = re.split(r'(\s+)', reply)
    for word in words:
        if word:
            yield word
            time.sleep(0.015)


# ─── NON-STREAMING FALLBACK ───────────────────────────────────────────────────
def chat_with_ollama(user_message: str, context: str, chat_history: list = None, lang: str = "en") -> str:
    """Non-streaming version — returns a single string."""
    return "".join(stream_ollama(user_message, context, chat_history, lang=lang))


# ─── QUICK RECOMMENDATIONS ────────────────────────────────────────────────────
def get_quick_recommendations(app, budget: float = None, veg_only: bool = False) -> list:
    """Return structured food recommendations based on budget/diet filters."""
    with app.app_context():
        q = MenuItem.query.filter_by(is_available=True)
        if budget:
            q = q.filter(MenuItem.price <= budget)
        if veg_only:
            q = q.filter(MenuItem.veg_nonveg == "veg")
        return [
            {
                "name":  item.name,
                "price": item.price,
                "shop":  item.shop.name,
                "veg":   item.veg_nonveg,
                "qty":   item.quantity_desc,
            }
            for item in q.order_by(MenuItem.price.asc()).limit(10).all()
        ]
