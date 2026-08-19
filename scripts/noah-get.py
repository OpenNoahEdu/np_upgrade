#!/usr/bin/env python3

import argparse
import json
import re
import sys
import yaml
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SITE_URL = 'https://downloads.youxuepai.com/source/list.shtml'
API_BASE_URL = 'https://resapi.youxuepai.com'
USER_AGENT = 'np-upgrade-resource-list/1.0'


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='List a Noah model\'s resources and output as hierarchical YAML.',
    )
    parser.add_argument('model', help='Model name, for example: NP1100')
    parser.add_argument('--catalog', metavar='NAME', help='Only list this catalog and its subcatalogs.')
    parser.add_argument('--filter', metavar='KEYWORD', action='append', default=[], help='Only list resource names containing KEYWORD. Can be repeated.')
    return parser.parse_args()


def normalize_name(value: object) -> str:
    return ' '.join(str(value or '').split()).lower()


def fetch_text(url: str) -> str:
    request = Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or 'utf-8'
            return response.read().decode(charset)
    except HTTPError as error:
        raise RuntimeError(f'Request failed ({error.code}): {url}') from error
    except URLError as error:
        raise RuntimeError(f'Request failed: {url} ({error.reason})') from error


def fetch_json(url: str) -> Any:
    try:
        return json.loads(fetch_text(url))
    except json.JSONDecodeError as error:
        raise RuntimeError(f'Expected JSON from: {url}') from error


def find_product(model: str) -> dict[str, Any]:
    products: list[dict[str, Any]] = []
    pattern = re.compile(
        r'"productId"\s*:\s*(\d+),[\s\S]{0,300}?"productName"\s*:\s*"((?:\\.|[^"\\])*)"',
    )

    for match in pattern.finditer(fetch_text(SITE_URL)):
        products.append({
            'id': int(match.group(1)),
            'name': json.loads(f'"{match.group(2)}"'),
        })

    normalized_model = normalize_name(model)
    for product in products:
        if normalize_name(product['name']) == normalized_model:
            return product

    suggestions = list(dict.fromkeys(
        product['name'] for product in products
        if normalized_model in normalize_name(product['name'])
    ))[:12]
    hint = f" Possible matches: {', '.join(suggestions)}." if suggestions else ''
    raise RuntimeError(f'Product not found: {model}.{hint}')


def find_catalogs(nodes: list[dict[str, Any]], catalog_name: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    normalized_catalog_name = normalize_name(catalog_name)

    for node in nodes:
        if normalize_name(node.get('name')) == normalized_catalog_name:
            matches.append(node)
        matches.extend(find_catalogs(node.get('children') or [], catalog_name))

    return matches


def resource_name(resource: dict[str, Any]) -> str:
    return str(resource.get('cname') or resource.get('name') or resource.get('fileName') or '')


def fetch_resources(
    product_id: int,
    catalog_id: int,
    filters: list[str]
) -> list[dict[str, Any]]:
    page_number = 1
    total_pages = 1
    resources: list[dict[str, Any]] = []

    while page_number <= total_pages:
        parameters = urlencode({
            'function': catalog_id,
            'get': 'basic',
            'highlighter': 'true',
            'pageNo': page_number,
            'pageSize': 100,
            'productids': product_id,
        })
        result = fetch_json(f'{API_BASE_URL}/search/api/searchsource?{parameters}')

        for resource in result.get('keys', []):
            if filters and not any(normalize_name(keyword) in normalize_name(resource_name(resource)) for keyword in filters):
                continue
            resources.append(resource)
            
        total_pages = int(result.get('totalPage') or 1)
        page_number += 1
        
    return resources


def walk_catalog_tree(
    nodes: list[dict[str, Any]],
    product_id: int,
    filters: list[str],
) -> None:
    """Recursively walks the tree and attaches resources to leaf nodes."""
    for node in nodes:
        children = node.get('children') or []
        if children:
            walk_catalog_tree(children, product_id, filters)
        else:
            catalog_name = str(node.get('name', '')).strip()
            print(f"Fetching resources for catalog: {catalog_name}", file=sys.stderr)
            resources = fetch_resources(product_id, int(node['id']), filters)
            if resources:
                print(f"  -> Found {len(resources)} resources.", file=sys.stderr)
            node['resources'] = resources


def main() -> None:
    options = parse_arguments()
    
    print(f'Resolving product: {options.model}', file=sys.stderr)
    product = find_product(options.model)
    print(f"Loading catalog tree for {product['name']} (ID: {product['id']})", file=sys.stderr)

    tree = fetch_json(f"{API_BASE_URL}/portal/courseware/apcatalogs?pid={product['id']}")
    
    if options.catalog:
        tree = find_catalogs(tree, options.catalog)
        if not tree:
            raise RuntimeError(f'Catalog not found: {options.catalog}')
            
    walk_catalog_tree(tree, product['id'], options.filter)
    
    # Construct the final JSON payload
    output_data = {
        "site_url": SITE_URL,
        "product": product,
        "catalogs": tree
    }
    
    # Print the YAML to stdout
    print(yaml.dump(output_data, allow_unicode=True, sort_keys=False))
    print("Done.", file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
