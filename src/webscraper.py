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