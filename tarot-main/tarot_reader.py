import requests
import json
from config import RANDOM_API_KEY, MISTRAL_API_KEY, DEEPSEEK_API_KEY,GROK_API_KEY ,logger
from pydantic import BaseModel
from cards import tarot_cards
from dotenv import dotenv_values
from mistralai import Mistral
from openai import OpenAI
from spread_info import celtic_cross_spread, three_card_spread, one_card_spread
from system_prompts import (
    celtic_cross_system_text,
    three_card_system_text,
    one_card_system_text,
)


class TarotCard(BaseModel):
    name: str
    id: int
    reversed: bool
    picture: str
    meaning: str
    crowley_meaning: str
    ai_meaning: str
    position: str
    position_description: str


class ApiResponse(BaseModel):
    query: str
    cards: list[TarotCard]
    final_result: str


def ai_request(api_request, system_text, model="mistral-small-latest"):
    if "mistral" in model:
        return mistral_api_request(api_request, system_text)
    elif "deepseek" in model:
        return deepseeek_api_request(api_request, system_text)
    elif "grok" in model:
        return grok_api_request(api_request, system_text)
    else:
        raise ValueError(f"Unsupported model: {model}. Supported models are: mistral, deepseek, grok.")


def deepseeek_api_request(api_request, system_text):
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    ai_response = client.chat.completions.create(
        model="deepseek-chat",
        temperature=1.5,
        response_format={'type': 'json_object'},
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": api_request},
        ],
        stream=False,
    )
    logger.info(f"AI Response:{ai_response}")
    return ai_response

def grok_api_request(api_request, system_text):
    logger.info(f"Using Grock API ")
    client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
    ai_response = client.chat.completions.create(
        model="grok-3-mini",
        temperature=1.5,
        response_format={'type': 'json_object'},
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": api_request},
        ],
        stream=False,
    )
    logger.info(f"AI Response:{ai_response}")
    return ai_response




def mistral_api_request(api_request, system_text):
    # Use the Mistral API to get a response
    with Mistral(api_key=MISTRAL_API_KEY) as mistral:
        ai_response = mistral.chat.complete(
            model="mistral-small-latest",
            temperature=1.3,
            response_format={"type": "json_object"},
            messages=[
                {"content": api_request, "role": "user"},
                {"content": system_text, "role": "system"},
            ],
        )
    logger.info(f"AI Response:{ai_response}")
    return ai_response


class RandomOrgClient:
    def __init__(self, api_key=RANDOM_API_KEY):
        self.api_key = api_key
        self.base_url = "https://api.random.org/json-rpc/4/invoke"
        self.headers = {"Content-Type": "application/json"}

    def _make_request(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        response = requests.post(
            self.base_url, headers=self.headers, data=json.dumps(payload)
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            raise Exception(f"API Error: {result['error']['message']}")
        return result["result"]

    def generate_integers(self, n, min_val, max_val):
        params = {
            "apiKey": self.api_key,
            "n": n,
            "min": min_val,
            "max": max_val,
            "replacement": False,
        }
        return self._make_request("generateIntegers", params)["random"]["data"]


class TarotReader:
    def __init__(self, api_key=RANDOM_API_KEY):
        self.client = RandomOrgClient(api_key)
        # Map tarot card numbers to names (Rider-Waite deck example)
        self.cards = tarot_cards

    def draw_cards(self, num_cards=3):
        """
        Draw multiple cards (e.g., past-present-future spread).
        Example: [{"card": "...", "reversed": False}, ...]
        """
        card_nos = self.client.generate_integers(num_cards, -77, 77)
        #Ensure we don't draw the same card twice
        while len(set([abs(no) for no in card_nos])) < num_cards:
            card_nos = self.client.generate_integers(num_cards, -77, 77)
        drawn_cards = []
        for no, card_no in enumerate(card_nos):
            card = [c for c in self.cards if abs(card_no) == c["number"]][0]
            name = card["name"]
            if card_no < 0:
                reversed = True
                name = card["name"] + " (reversed)"
                picture = card["picture_reversed"]
                meaning = card["reversed"]
                c_meaning = card["crowley_reversed"]
            else:
                reversed = False
                picture = card["picture"]
                meaning = card["upright"]
                c_meaning = card["crowley_upright"]
            drawn_cards.append(
                {
                    "name": name,
                    "id": no + 1,
                    "reversed": reversed,
                    "picture": picture,
                    "meaning": meaning,
                    "crowley_meaning": c_meaning,
                }
            )
        return drawn_cards

    def draw_spread(self, spread_type="celtic_cross"):
        """
        Draw a specific spread type (e.g., Celtic Cross).
        Example: [{"card": "...", "reversed": False}, ...]
        """
        if spread_type == "celtic_cross":
            drawn_cards = self.draw_cards(num_cards=10)
            selected_spread = celtic_cross_spread.copy()
        elif spread_type == "three_card":
            drawn_cards = self.draw_cards(num_cards=3)
            selected_spread = three_card_spread.copy()
        elif spread_type == "one_card":
            drawn_cards = self.draw_cards(num_cards=1)
            selected_spread = one_card_spread.copy()
        else:
            raise ValueError("Unsupported spread type")
        for card in drawn_cards:
            card_position = selected_spread.pop(0)
            card["position"] = card_position["name"]
            card["position_description"] = card_position["description"]
        return drawn_cards

    def get_quota(self):
        """Check remaining API quota"""
        params = {"apiKey": self.client.api_key}
        return self.client._make_request("getUsage", params)["bitsLeft"]

    def get_one_card_reading(self, query="",model="mistral-small-latest"):
        cards = self.draw_spread(spread_type="one_card")
        ai_response = self.ai_api_request(cards, one_card_system_text, query=query,model=model)
        ai_json = json.loads(ai_response.choices[0].message.content)
        return self.map_cards_to_ai_response(ai_json, cards, query=query)

    def get_three_card_reading(self, query="",model="mistral-small-latest"):
        cards = self.draw_spread(spread_type="three_card")
        ai_response = self.ai_api_request(cards, three_card_system_text, query=query,model=model)
        ai_json = json.loads(ai_response.choices[0].message.content)
        return self.map_cards_to_ai_response(ai_json, cards, query=query)

    def get_celtic_cross_reading(self, query="",model="mistral-small-latest"):
        cards = self.draw_spread(spread_type="celtic_cross")
        ai_response = self.ai_api_request(cards, celtic_cross_system_text, query=query,model=model)
        ai_json = json.loads(ai_response.choices[0].message.content)
        # MAP THE JSON TO THE CARDS
        return self.map_cards_to_ai_response(ai_json, cards, query=query)

    def map_cards_to_ai_response(self, ai_json, cards, query=""):
        for card in cards:
            ai_response = [
                ai_card
                for ai_card in ai_json["cards"]
                if card["name"] in ai_card["card"]
            ][0]
            card["ai_meaning"] = ai_response["meaning"]
            card["position"] = ai_response["position"]
        api_response = ApiResponse(
            query=query,
            final_result=ai_json["final_result"],
            cards=[TarotCard(**card) for card in cards],
        )
        logger.info(f"API Response OK")
        
        return api_response

    def ai_api_request(
        self, cards, system_query, query="", model="mistral-small-latest"
    ):
        logger.info(f"Query: {query}")
        logger.info(f"Cards: {cards} ")
        if query:
            request_text = f"""I have asked: {query}.\n The cards are """
        else:
            request_text = f"""I have not asked a question.\n The cards are"""
        card_text = "\n".join(
            [
                f"Card {card['id']}: {card['position']}: {card['name']}"
                for card in (cards)
            ]
        )
        api_request = f"""{request_text}\n{card_text}"""
        logger.debug(f"API Request: {api_request}")
        ai_response = ai_request(api_request, system_query, model=model)
        return ai_response
