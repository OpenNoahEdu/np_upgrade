#!/usr/bin/env python3

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


SITE_URL = 'https://downloads.youxuepai.com/source/list.shtml'
API_BASE_URL = 'https://resapi.youxuepai.com'
DOWNLOAD_BASE_URL = 'https://files1.youxuepai.com/Upload/'
USER_AGENT = 'np-upgrade-resource-list/1.0'


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='List a Youxuepai model\'s resources and download URLs as Markdown.',
    )
    parser.add_argument('model', help='Model name, for example: NP1100')
    parser.add_argument('--catalog', metavar='NAME', help='Only list this catalog and its subcatalogs.')
    parser.add_argument('--filter', metavar='KEYWORD', action='append', default=[], help='Only list resource names containing KEYWORD. Can be repeated.')
    parser.add_argument('--compact', action='store_true', help='Only output file names, size, date, MD5, and download URLs.')
    parser.add_argument('--download', metavar='DIR', help='Download files to this directory preserving URL hierarchy.')
    parser.add_argument('--out', metavar='FILE', help='Write Markdown to FILE instead of stdout.')
    parser.add_argument('--verbose', action='store_true', help='Print progress to stderr.')
    return parser.parse_args()


def normalize_name(value: object) -> str:
    return ' '.join(str(value or '').split()).lower()


def escape_markdown(value: object) -> str:
    return re.sub(r'([\\`*_[\]<>])', r'\\\1', str(value or ''))


def decode_html(value: object) -> str:
    text = str(value or '')
    text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]*>', '', text)
    text = html.unescape(text).replace('\r', '')
    return re.sub(r'\n[ \t]*\n+', '\n', text).strip()


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


def download_url(resource: dict[str, Any]) -> str:
    source_address = resource.get('souraddr')
    if source_address:
        return urljoin(DOWNLOAD_BASE_URL, quote(str(source_address), safe='/'))
    return resource.get('url') or f"http://dl.youxuepai.com/download/courseware/{resource['id']}"


def resource_name(resource: dict[str, Any]) -> str:
    return str(resource.get('cname') or resource.get('name') or resource.get('fileName') or '')


def resource_markdown(resource: dict[str, Any], compact: bool) -> str:
    fields = [
        ('资源 ID', resource.get('id')),
        ('类别', resource.get('type')),
        ('大小', resource.get('sfileSize')),
        ('更新日期', resource.get('updateTime')),
        ('科目', resource.get('subject')),
        ('年级', resource.get('gradeFull') or resource.get('grade')),
        ('学期', resource.get('term')),
        ('出版社', resource.get('publishname') or resource.get('press')),
        ('版本', resource.get('version') or resource.get('revision')),
        ('适用机型', resource.get('products')),
        ('MD5', resource.get('md5Code')),
    ]
    if compact:
        fields = [
            ('大小', resource.get('sfileSize')),
            ('更新日期', resource.get('updateTime')),
            ('MD5', resource.get('md5Code')),
        ]
    lines = [f"- **{escape_markdown(resource_name(resource))}**"]

    for label, value in fields:
        if value not in (None, ''):
            lines.append(f'  - {label}: {escape_markdown(value)}')

    if not compact:
        description = decode_html(resource.get('description') or resource.get('remarks'))
        if description:
            lines.append('  - 说明:')
            lines.extend(f'    - {escape_markdown(paragraph.strip())}' for paragraph in description.split('\n') if paragraph)

    lines.append(f'  - 下载: <{download_url(resource)}>')
    return '\n'.join(lines)


def download_resource(resource: dict[str, Any], download_dir: Path, verbose: bool, compact: bool) -> None:
    url = download_url(resource)
    parsed_url = urlparse(url)
    rel_path = unquote(parsed_url.path.lstrip('/'))
    file_path = download_dir / rel_path

    if file_path.exists():
        if verbose:
            print(f"Skipping existing file: {file_path}", file=sys.stderr)
    else:
        if verbose:
            print(f"Downloading {url} to {file_path}", file=sys.stderr)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file_path = file_path.with_name(file_path.name + '.downloading')
        
        try:
            request = Request(url, headers={'User-Agent': USER_AGENT})
            with urlopen(request, timeout=600) as response, temp_file_path.open('wb') as out_file:
                shutil.copyfileobj(response, out_file)
            temp_file_path.rename(file_path)
        except Exception as error:
            if verbose:
                print(f"Failed to download {url}: {error}", file=sys.stderr)
            if temp_file_path.exists():
                temp_file_path.unlink()
            return
        except KeyboardInterrupt:
            if verbose:
                print(f"\nDownload interrupted. Cleaning up {temp_file_path}", file=sys.stderr)
            if temp_file_path.exists():
                temp_file_path.unlink()
            raise

    meta_path = file_path.with_name(file_path.name + '.md')
    with meta_path.open('w', encoding='utf-8') as f:
        f.write(resource_markdown(resource, compact) + '\n')


def write_resources(
    product_id: int,
    catalog_id: int,
    output: TextIO,
    compact: bool,
    filters: list[str],
    download_dir: Path | None,
    verbose: bool,
) -> None:
    page_number = 1
    total_pages = 1

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
            if download_dir:
                download_resource(resource, download_dir, verbose, compact)
            write(output, f'{resource_markdown(resource, compact)}\n')
        total_pages = int(result.get('totalPage') or 1)
        page_number += 1


def write_catalog_markdown(
    nodes: list[dict[str, Any]],
    product_id: int,
    output: TextIO,
    verbose: bool,
    compact: bool,
    filters: list[str],
    download_dir: Path | None,
    depth: int = 3,
    skip_root_heading: bool = False,
) -> None:
    for index, node in enumerate(nodes):
        children = node.get('children') or []
        if not (skip_root_heading and depth == 3 and index == 0):
            heading = '#' * min(depth, 6)
            write(output, f"{heading} {escape_markdown(str(node.get('name', '')).strip())}\n\n")

        if children:
            write_catalog_markdown(children, product_id, output, verbose, compact, filters, download_dir, depth + 1)
        else:
            if verbose:
                print(f"Loading {str(node.get('name', '')).strip()}", file=sys.stderr)
            write_resources(product_id, int(node['id']), output, compact, filters, download_dir, verbose)
            write(output, '\n')


def write(output: TextIO, content: str) -> None:
    output.write(content)
    output.flush()


def main() -> None:
    options = parse_arguments()
    
    if options.out or options.download:
        options.verbose = True

    if options.verbose:
        print(f'Resolving product: {options.model}', file=sys.stderr)
    product = find_product(options.model)
    if options.verbose:
        print(f"Loading catalog tree for {product['name']} (ID: {product['id']})", file=sys.stderr)

    tree = fetch_json(f"{API_BASE_URL}/portal/courseware/apcatalogs?pid={product['id']}")
    skip_root_heading = False
    if options.catalog:
        tree = find_catalogs(tree, options.catalog)
        if not tree:
            raise RuntimeError(f'Catalog not found: {options.catalog}')
        skip_root_heading = len(tree) == 1 and not tree[0].get('children')
    output: TextIO = sys.stdout
    output_file: TextIO | None = None

    if options.out:
        output_path = Path(options.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_file = output_path.open('w', encoding='utf-8')
        output = output_file

    download_dir = Path(options.download) if options.download else None

    try:
        if not options.compact:
            write(output, '\n'.join([
                f"# {escape_markdown(product['name'])} 资源下载清单",
                '',
                f"- 产品 ID: {product['id']}",
                f"- 资源页: <{SITE_URL}#{product['id']}&name={quote(product['name'])}>",
                *([f'- 目录筛选: {escape_markdown(options.catalog)}'] if options.catalog else []),
                '',
                '## 功能目录',
                '',
            ]))
        write_catalog_markdown(
            tree,
            product['id'],
            output,
            options.verbose,
            options.compact,
            options.filter,
            download_dir,
            skip_root_heading=skip_root_heading,
        )
    finally:
        if output_file:
            output_file.close()

    if options.out and options.verbose:
        print(f'Wrote {options.out}', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)