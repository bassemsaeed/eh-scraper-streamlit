import scrapy
import json
from typing import Dict, Any, List

class ElectricHouseSpider(scrapy.Spider):
    name = "electrichouse"
    allowed_domains = ["electric-house.com"]
    # API Endpoint
    api_url = "https://electric-house.com/graphql"
    
    # Store ID (from network analysis, likely needed for context)
    store_code = "en" # Defaulting to English as per requirement to link with Arabic later
    
    headers = {
        "Content-Type": "application/json",
        "Store": store_code,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    def __init__(self, store="en", *args, **kwargs):
        super(ElectricHouseSpider, self).__init__(*args, **kwargs)
        self.store_code = store
        self.headers["Store"] = self.store_code

    def start_requests(self):
        """
        Start by fetching the category tree to get all Category UIDs.
        """
        query = """
        query categoryList {
            categoryList {
                id
                uid
                name
                url_path
                children {
                    id
                    uid
                    name
                    url_path
                    children {
                        id
                        uid
                        name
                        url_path
                        children {
                            id
                            uid
                            name
                            url_path
                        }
                    }
                }
            }
        }
        """
        payload = {
            "query": query,
            "variables": {}
        }
        yield scrapy.Request(
            url=self.api_url,
            method="POST",
            headers=self.headers,
            body=json.dumps(payload),
            callback=self.parse_categories,
            errback=self.handle_error
        )

    def parse_categories(self, response):
        """
        Parse the category tree and yield requests for products in leaf categories.
        """
        try:
            data = json.loads(response.body)
            categories = data.get("data", {}).get("categoryList", [])
            self.logger.info(f"Found {len(categories)} root categories")
            
            # Helper to recursively traverse categories
            def traverse_categories(cats: List[Dict[str, Any]]):
                for cat in cats:
                    # If it has children, traverse them
                    if cat.get("children") and len(cat["children"]) > 0:
                        yield from traverse_categories(cat["children"])
                    else:
                        # Leaf category (or one we want to scrape)
                        # Yield a request to fetch products for this category
                        uid = cat.get("uid")
                        if uid:
                            yield from self.fetch_products(uid, page=1)

            yield from traverse_categories(categories)

        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode JSON from {response.url}")

    def fetch_products(self, category_uid: str, page: int):
        """
        Generate a GraphQL request to fetch products for a specific category and page.
        """
        query = """
        query getProducts($uid: String!, $page: Int!) {
            products(
                filter: { category_uid: { eq: $uid } }
                pageSize: 20
                currentPage: $page
            ) {
                total_count
                page_info {
                    current_page
                    total_pages
                }
                items {
                    id
                    uid
                    sku
                    name
                    stock_status
                    url_key
                    price_range {
                        maximum_price {
                            final_price {
                                value
                                currency
                            }
                            regular_price {
                                value
                                currency
                            }
                            discount {
                                amount_off
                                percent_off
                            }
                        }
                    }
                    small_image {
                        url
                    }
                    description {
                        html
                    }
                }
            }
        }
        """
        payload = {
            "query": query,
            "variables": {
                "uid": category_uid,
                "page": page
            }
        }
        
        yield scrapy.Request(
            url=self.api_url,
            method="POST",
            headers=self.headers,
            body=json.dumps(payload),
            callback=self.parse_products,
            cb_kwargs={"category_uid": category_uid, "page": page},
            meta={"handle_httpstatus_list": [400, 404, 500]}, # Handle errors gracefully
            dont_filter=True # Allow multiple requests to same URL (API endpoint)
        )

    def parse_products(self, response, category_uid: str, page: int):
        """
        Parse product data and handle pagination.
        """
        try:
            data = json.loads(response.body)
            
            if "errors" in data:
                self.logger.error(f"GraphQL Errors for Cat {category_uid} Page {page}: {data['errors']}")
                return

            products_data = data.get("data", {}).get("products", {})
            items = products_data.get("items", [])
            page_info = products_data.get("page_info", {})
            total_pages = page_info.get("total_pages", 1)

            self.logger.info(f"Scraped {len(items)} products from Cat '{category_uid}' Page {page}/{total_pages}")

            for item in items:
                yield self.process_product_item(item)

            # Pagination
            if page < total_pages:
                next_page = page + 1
                yield from self.fetch_products(category_uid, next_page)

        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode JSON from {response.url}")

    def process_product_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and format product data.
        """
        price_info = item.get("price_range", {}).get("maximum_price", {})
        final_price = price_info.get("final_price", {}).get("value")
        regular_price = price_info.get("regular_price", {}).get("value")
        currency = price_info.get("final_price", {}).get("currency")
        
        # Calculate discount if present
        discount = price_info.get("discount", {})
        
        return {
            "id": item.get("id"),
            "uid": item.get("uid"),
            "sku": item.get("sku"),
            "name": item.get("name"),
            "url_key": item.get("url_key"),
            "stock_status": item.get("stock_status"),
            "final_price": final_price,
            "regular_price": regular_price,
            "currency": currency,
            "discount_amount": discount.get("amount_off"),
            "discount_percent": discount.get("percent_off"),
            "image_url": item.get("small_image", {}).get("url"),
            "description": item.get("description", {}).get("html"), # Be careful with HTML content size
            "source_site": "electric-house"
        }

    def handle_error(self, failure):
        self.logger.error(f"Request failed: {failure.request.url} - {failure.value}")
