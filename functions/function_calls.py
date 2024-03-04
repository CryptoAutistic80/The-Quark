import json
import os
import re
from typing import Literal

import httpx
import openai
import pandas as pd
import xmltodict
import yfinance as yf


async def get_stock_info(tickers, info_types):
    result = {}

    for ticker in tickers:
        stock_info = yf.Ticker(ticker)
        ticker_result = {}

        try:
            if "current_price" in info_types:
                stock_history = stock_info.history(period="1d")
                ticker_result["current_price"] = stock_history["Close"].iloc[0]

            if "dividends" in info_types:
                dividends_df = stock_info.dividends.reset_index()
                dividends_df['Date'] = dividends_df['Date'].astype(str)
                ticker_result["dividends"] = dividends_df.to_dict(orient='list')

            if "splits" in info_types:
                splits_df = stock_info.splits.reset_index()
                splits_df['Date'] = splits_df['Date'].astype(str)
                ticker_result["splits"] = splits_df.to_dict(orient='list')

            if "company_info" in info_types:
                ticker_result["company_info"] = stock_info.info

            if "financials" in info_types:
                financials_df = stock_info.financials.reset_index()
                financials_df['Date'] = financials_df['Date'].astype(str)
                ticker_result["financials"] = financials_df.to_dict(orient='list')

            if "sustainability" in info_types:
                sustainability_df = stock_info.sustainability.reset_index()
                sustainability_df['Date'] = sustainability_df['Date'].astype(str)
                ticker_result["sustainability"] = sustainability_df.to_dict(orient='list')

            if "recommendations" in info_types:
                rec = stock_info.recommendations
                if isinstance(rec, pd.DataFrame):
                    rec = rec.reset_index()
                    rec['Date'] = rec['Date'].astype(str)
                    ticker_result["recommendations"] = rec.to_dict(orient='list')
                elif isinstance(rec, dict):
                    ticker_result["recommendations"] = rec
                else:
                    ticker_result["recommendations"] = str(rec)

            result[ticker] = ticker_result

        except Exception as e:
            result[ticker] = {"error": str(e)}

    return result


async def query_wolfram_alpha(queries):
    base_url = "https://www.wolframalpha.com/api/v1/llm-api"
    wolfram_id = os.getenv('WOLFRAM_ID')
    if wolfram_id is None:
        raise ValueError("No WOLFRAM_ID found. Please set the WOLFRAM_ID environment variable.")
    results = {}

    def remove_urls(text):
        return re.sub(r'http\S+', '', text)

    async with httpx.AsyncClient() as client:
        for query in queries:
            params = {
                "input": query,
                "appid": wolfram_id
            }
            response = await client.get(base_url, params=params)
            response_text_no_urls = remove_urls(response.text)
            if response.status_code == 200:
                try:
                    results[query] = json.loads(response_text_no_urls)
                except json.JSONDecodeError:
                    results[query] = {"error": "Failed to decode JSON", "response_text": response_text_no_urls}
            elif response.status_code == 502:
                results[query] = {"error": "502 Bad Gateway from Wolfram Alpha"}
            else:
                results[query] = {"error": f"Failed to query Wolfram Alpha, received HTTP {response.status_code}"}

    return results


async def get_crypto_info_from_coinmarketcap(token_symbol: str):
    api_key = os.environ.get('CMC_API_KEY')
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': api_key,
    }
  
    # Function to get basic information such as price, volume, supply, etc.
    async def get_basic_info(symbol):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        params = {'symbol': symbol, 'convert': 'USD'}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            return response.json().get('data', {}).get(symbol.upper(), {})
  
    # Function to get metadata like descriptions, logo, etc.
    async def get_metadata(symbol):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/info"
        params = {'symbol': symbol}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            return response.json().get('data', {}).get(symbol.upper(), {})
  
    # Function to get market pair (exchange) information
    async def get_market_pairs(symbol):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/market-pairs/latest"
        params = {'symbol': symbol}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            return response.json().get('data', {}).get('market_pairs', [])
  
    # Call the above functions asynchronously
    basic_info = await get_basic_info(token_symbol)
    metadata = await get_metadata(token_symbol)
    market_pairs_response = await get_market_pairs(token_symbol)
  
    if not basic_info:
        return "Failed to retrieve basic info"
  
    quote = basic_info.get('quote', {}).get('USD', {})
    market_cap = quote.get('market_cap')
    current_price = quote.get('price')
    total_volume = quote.get('volume_24h')
    circulating_supply = basic_info.get('circulating_supply')
    total_supply = basic_info.get('total_supply')
    undiluted_market_cap = current_price * total_supply if current_price and total_supply else None
  
    # Check if metadata is None before trying to access its properties
    description = metadata.get('description') if metadata else None
    logo = metadata.get('logo') if metadata else None
    urls = metadata.get('urls', {}) if metadata else {}
  
    # Extract exchange information from market pairs
    exchanges = [pair['exchange']['name'] for pair in market_pairs_response] if market_pairs_response else []
  
    result = {
        'market_cap': market_cap,
        'current_price': current_price,
        'total_volume': total_volume,
        'circulating_supply': circulating_supply,
        'total_supply': total_supply,
        'undiluted_market_cap': undiluted_market_cap,
        'description': description,
        'logo': logo,
        'urls': urls,
        'exchanges': exchanges,
    }
  
    return result


async def mediawiki_query(action, search_string):
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": action,
        "format": "json",
        "list": "search",
        "srsearch": search_string
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data



async def generate_image_with_dalle(prompt: str, size: Literal['1024x1024', '1024x1792', '1792x1024'], quality: Literal['standard', 'hd'] = 'standard'):
    """
    Generates an original image based on a text prompt using DALL·E 3.
    - `prompt`: The text prompt based on which DALL·E 3 will generate an image.
    - `size`: The dimension of the generated image. Valid options are '1024x1024', '1024x1792', and '1792x1024'.
    - `quality`: The quality of the generated image, either 'standard' or 'hd'. Defaults to 'standard'.
    """

    # Initialize the OpenAI client (ensure your API key is set up correctly)
    client = openai.OpenAI()

    # Generate the image with DALL·E 3
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )

    # Extract the URL of the generated image
    image_url = response.data[0].url

    return image_url


async def query_arxiv(search_query, max_results=10):
    """
    Asynchronously query the arXiv API for papers matching the search query and return results as JSON.
  
    Parameters:
    search_query (str): The search query string.
    max_results (int): Maximum number of results to return.
  
    Returns:
    JSON: A JSON object containing the query results or an error message.
    """
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": search_query,
        "start": 0,  # Adjust if pagination is needed
        "max_results": max_results
    }
  
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(base_url, params=params)
            if response.status_code == 200:
                # Convert XML response to Python dict and then to JSON
                response_dict = xmltodict.parse(response.content)
                return json.dumps(response_dict)  # Convert dict to JSON string
            else:
                return json.dumps({"error": f"Failed to query arXiv, received HTTP {response.status_code}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

async def get_trending_cryptos():
    async with httpx.AsyncClient() as client:
        response = await client.get('https://api.coingecko.com/api/v3/search/trending')
        response.raise_for_status()
        trending_data = response.json()
    
    trending_coins = trending_data['coins']
    trending_list = []
    for coin in trending_coins:
        coin_info = {
            'name': coin['item']['name'],
            'symbol': coin['item']['symbol'],
            'market_cap_rank': coin['item']['market_cap_rank'],
        }
        trending_list.append(coin_info)
    
    return trending_list