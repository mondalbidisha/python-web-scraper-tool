# Python Web Scraping Tool

### Example Usage

Example usage to fetch all phrases from a stackoverflow page:

```python
from web_scraper import WebScraper

url = 'https://stackoverflow.com/questions/78490118/eslint-for-empty-statements'

# We can add single or multiple phrases here.
# We can add urls here.
required_phrases_list = ["no-unused-expressions"]

webscraper = WebScraper()
result = webscraper.build(url, required_phrases_list)
print(result)
```

Here's the output:
```python
[
    'no-unused-expressions', 
    '@typescript-eslint/no-unused-expressions', 
    'demo in TypeScript ESLint playground'
]
```

