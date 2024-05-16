from web_scraper import WebScraper

url = 'https://stackoverflow.com/questions/78490118/eslint-for-empty-statements'

# We can add one or multiple phrases here.
# You can also put urls here to retrieve urls.
wanted_list = ["no-unused-expressions"]

scraper = WebScraper()
result = scraper.build(url, wanted_list)
print(result)