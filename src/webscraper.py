import hashlib
import json
from collections import defaultdict
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

class WebScraper (scrapeObject):

    def __init__(self, list = None):
        self.list = list or []

    def saveSerialisedJSON(self, filePath):
        data = dict(list = self.list)
        with open(filePath, "w") as fileObject:
            json.dump(data, fileObject)

    def loadFromDisk(self, filePath):
        with open(filePath, "r") as fileObject:
            jsonData = json.load(fileObject)

        if isinstance(jsonData, list):
            self.list = jsonData
            return

        self.list = jsonData["list"]

    @classmethod
    def _fetch_html(cls, url, request_args = None):
        request_args = request_args or {}
        headers = dict(cls.request_headers)
        if url:
            headers["Host"] = urlparse(url).netloc

        user_headers = request_args.pop("headers", {})
        headers.update(user_headers)
        response = requests.get(url, headers = headers, **request_args)
        if response.encoding == "ISO-8859-1" and not "ISO-8859-1" in response.headers.get(
            "Content-Type", ""
        ):
            response.encoding = response.apparent_encoding
            html = response.text
            return html