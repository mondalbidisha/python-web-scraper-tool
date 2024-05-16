import hashlib
import json
from collections import defaultdict
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from utilities import (
    FuzzyText,
    ResultItem,
    getNonRecursiveText,
    getRandomString,
    normalize,
    textMatch,
    uniqueHashable,
    uniqueList,
)

class WebScraper (object):

    request_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 \
            (KHTML, like Gecko) Chrome/84.0.4147.135 Safari/537.36"
    }

    def __init__(self, list = None):
        self.list = list or []

    @classmethod
    def fetchHTML(cls, url, requestArguments = None):
        requestArguments = requestArguments or {}
        headers = dict(cls.request_headers)
        if url:
            headers["Host"] = urlparse(url).netloc

        user_headers = requestArguments.pop("headers", {})
        headers.update(user_headers)
        response = requests.get(url, headers = headers, **requestArguments)
        if response.encoding == "ISO-8859-1" and not "ISO-8859-1" in response.headers.get("Content-Type", ""):
            response.encoding = response.apparent_encoding
        
        html = response.text
        return html
        
    @classmethod
    def getScrapedHTML(cls, url = None, html = None, requestArguments = None):
        if html:
            html = normalize(unescape(html))
            return BeautifulSoup(html, "lxml")

        html = cls.fetchHTML(url, requestArguments)
        html = normalize(unescape(html))

        return BeautifulSoup(html, "lxml")
    
    @staticmethod
    def getValidAttributes(item):
        keyAttributes = {"class", "style"}
        attributes = {
            k: v if v != [] else "" for k, v in item.attrs.items() if k in keyAttributes
        }

        for attribute in keyAttributes:
            if attribute not in attributes:
                attributes[attribute] = ""
        return attributes
    
    @staticmethod
    def childHasText(child, text, url, fuzzinessRatio):
        childElementText = child.getText().strip()

        if textMatch(text, childElementText, fuzzinessRatio):
            parentText = child.parent.getText().strip()
            if childElementText == parentText and child.parent.parent:
                return False

            child.wanted_attr = None
            return True

        if textMatch(text, getNonRecursiveText(child), fuzzinessRatio):
            child.is_non_rec_text = True
            child.wanted_attr = None
            return True

        for key, value in child.attrs.items():
            if not isinstance(value, str):
                continue

            value = value.strip()

            if textMatch(text, value, fuzzinessRatio):
                child.wanted_attr = key
                return True

            if key in {"href", "src"}:
                full_url = urljoin(url, value)
                if textMatch(text, full_url, fuzzinessRatio):
                    child.wanted_attr = key
                    child.is_full_url = True
                    return True

        return False
    
    def getChildren(self, soup, text, url, textFuzzinessRatio):
        children = reversed(soup.findChildren())
        children = [x for x in children if self.childHasText(x, text, url, textFuzzinessRatio)]
        return children

    def build(self, url = None, requiredList = None, requiredDict = None, html = None, requestArguments = None, update = False, textFuzzinessRatio = 1.0):
        soup = self.getScrapedHTML(url = url, html = html, requestArguments = requestArguments)
        resultList = []

        if update is False:
            self.list = []

        if requiredList:
            requiredDict = {"": requiredList}

        requiredList = []

        for alias, wanted_items in requiredDict.items():
            wanted_items = [normalize(w) for w in wanted_items]
            requiredList += wanted_items

            for wanted in wanted_items:
                children = self.getChildren(soup, wanted, url, textFuzzinessRatio)

                for child in children:
                    result, stack = self.getResultForChildElement(child, soup, url)
                    stack["alias"] = alias
                    resultList += result
                    self.list.append(stack)

        resultList = [item.text for item in resultList]
        resultList = uniqueHashable(resultList)

        self.list = uniqueList(self.list)
        return resultList

    @classmethod
    def buildStack(cls, child, url):
        content = [(child.name, cls.getValidAttributes(child))]

        parent = child
        while True:
            grandParentElement = parent.findParent()
            if not grandParentElement:
                break

            children = grandParentElement.findAll(parent.name, cls.getValidAttributes(parent), recursive = False)
            for i, c in enumerate(children):
                if c == parent:
                    content.insert(0, (grandParentElement.name, cls.getValidAttributes(grandParentElement), i))
                    break

            if not grandParentElement.parent:
                break

            parent = grandParentElement

        wanted_attr = getattr(child, "wanted_attr", None)
        is_full_url = getattr(child, "is_full_url", False)
        is_non_rec_text = getattr(child, "is_non_rec_text", False)
        stack = dict(content = content, wanted_attr = wanted_attr, is_full_url = is_full_url, is_non_rec_text = is_non_rec_text)
        stack["url"] = url if is_full_url else ""
        stack["hash"] = hashlib.sha256(str(stack).encode("utf-8")).hexdigest()
        stack["stack_id"] = "rule_" + getRandomString(4)
        return stack

    def getResultForChildElement(self, child, soup, url):
        stack = self.buildStack(child, url)
        result = self.getResultWithStack(stack, soup, url, 1.0)
        return result, stack

    @staticmethod
    def fetchResultFromChildElement(child, wanted_attr, is_full_url, url, is_non_rec_text):
        if wanted_attr is None:
            if is_non_rec_text:
                return getNonRecursiveText(child)
            return child.getText().strip()

        if wanted_attr not in child.attrs:
            return None

        if is_full_url:
            return urljoin(url, child.attrs[wanted_attr])

        return child.attrs[wanted_attr]

    @staticmethod
    def getFuzzyAttributes(attrs, attributeFuzzyRatio):
        attrs = dict(attrs)
        for key, val in attrs.items():
            if isinstance(val, str) and val:
                val = FuzzyText(val, attributeFuzzyRatio)
            elif isinstance(val, (list, tuple)):
                val = [FuzzyText(x, attributeFuzzyRatio) if x else x for x in val]
            attrs[key] = val
        return attrs

    def getResultWithStack(self, stack, soup, url, attributeFuzzyRatio, **kwargs):
        parents = [soup]
        stack_content = stack["content"]
        contain_sibling_leaves = kwargs.get("contain_sibling_leaves", False)
        for index, item in enumerate(stack_content):
            children = []
            if item[0] == "[document]":
                continue
            for parent in parents:

                attrs = item[1]
                if attributeFuzzyRatio < 1.0:
                    attrs = self._get_fuzzy_attrs(attrs, attributeFuzzyRatio)

                found = parent.findAll(item[0], attrs, recursive = False)
                if not found:
                    continue

                if not contain_sibling_leaves and index == len(stack_content) - 1:
                    idx = min(len(found) - 1, stack_content[index - 1][2])
                    found = [found[idx]]

                children += found

            parents = children

        wanted_attr = stack["wanted_attr"]
        is_full_url = stack["is_full_url"]
        is_non_rec_text = stack.get("is_non_rec_text", False)
        result = [
            ResultItem(
                self.fetchResultFromChildElement(
                    i, wanted_attr, is_full_url, url, is_non_rec_text
                ),
                getattr(i, "child_index", 0),
            )
            for i in parents
        ]
        if not kwargs.get("keepBlank", False):
            result = [x for x in result if x.text]
        return result

    def getResultUsingBasisListIndex(self, stack, soup, url, attributeFuzzyRatio, **kwargs):
        p = soup.findChildren(recursive=False)[0]
        stack_content = stack["content"]
        for index, item in enumerate(stack_content[:-1]):
            if item[0] == "[document]":
                continue
            content = stack_content[index + 1]
            attrs = content[1]
            if attributeFuzzyRatio < 1.0:
                attrs = self._get_fuzzy_attrs(attrs, attributeFuzzyRatio)
            p = p.findAll(content[0], attrs, recursive=False)
            if not p:
                return []
            idx = min(len(p) - 1, item[2])
            p = p[idx]

        result = [
            ResultItem(
                self.fetchResultFromChildElement(
                    p,
                    stack["wanted_attr"],
                    stack["is_full_url"],
                    url,
                    stack["is_non_rec_text"],
                ),
                getattr(p, "child_index", 0),
            )
        ]
        if not kwargs.get("keepBlank", False):
            result = [x for x in result if x.text]
        return result

    def getResultByFunction(self, func, url, html, soup, requestArguments, grouped, groupByAlias, unique, attributeFuzzyRatio, **kwargs):
        if not soup:
            soup = self.getScrapedHTML(url = url, html = html, requestArguments = requestArguments)

        maintainOrder = kwargs.get("maintainOrder", False)

        if groupByAlias or (maintainOrder and not grouped):
            for index, child in enumerate(soup.findChildren()):
                setattr(child, "child_index", index)

        resultList = []
        grouped_result = defaultdict(list)
        for stack in self.list:
            if not url:
                url = stack.get("url", "")

            result = func(stack, soup, url, attributeFuzzyRatio, **kwargs)

            if not grouped and not groupByAlias:
                resultList += result
                continue

            group_id = stack.get("alias", "") if groupByAlias else stack["stack_id"]
            grouped_result[group_id] += result

        return self.cleanResult(resultList, grouped_result, grouped, groupByAlias, unique, maintainOrder)

    @staticmethod
    def cleanResult(resultList, grouped_result, grouped, grouped_by_alias, unique, maintainOrder):
        if not grouped and not grouped_by_alias:
            if unique is None:
                unique = True
            if maintainOrder:
                resultList = sorted(resultList, key=lambda x: x.index)
            result = [x.text for x in resultList]
            if unique:
                result = uniqueHashable(result)
            return result

        for k, val in grouped_result.items():
            if grouped_by_alias:
                val = sorted(val, key=lambda x: x.index)
            val = [x.text for x in val]
            if unique:
                val = uniqueHashable(val)
            grouped_result[k] = val

        return dict(grouped_result)

    def getSimilarResults(self, url = None, html = None, soup = None, requestArguments = None, grouped = False, groupByAlias = False, unique = None, attributeFuzzyRatio = 1.0, keepBlank = False, maintainOrder = False, contain_sibling_leaves = False):
        function = self.getResultWithStack
        return self.getResultByFunction(function, url, html, soup, requestArguments, grouped, groupByAlias, unique, attributeFuzzyRatio, keepBlank = keepBlank, maintainOrder = maintainOrder, contain_sibling_leaves = contain_sibling_leaves)

    def getExactResults(self, url = None, html = None, soup = None, requestArguments = None, grouped = False, groupByAlias = False, unique = None, attributeFuzzyRatio = 1.0, keepBlank = False):
        function = self.getResultUsingBasisListIndex
        return self.getResultByFunction(function, url, html, soup, requestArguments, grouped, groupByAlias, unique, attributeFuzzyRatio, keepBlank = keepBlank)

    def getResults(self, url = None, html = None, requestArguments = None, grouped = False, groupByAlias = False, unique = None, attributeFuzzyRatio = 1.0):
        soup = self.getScrapedHTML(url = url, html = html, requestArguments = requestArguments)
        args = dict(url = url, soup = soup, grouped = grouped, groupByAlias = groupByAlias, unique = unique, attributeFuzzyRatio = attributeFuzzyRatio)
        similar = self.getSimilarResults(**args)
        exact = self.getExactResults(**args)
        return similar, exact

    def removeRules(self, rules):
        self.list = [x for x in self.list if x["stack_id"] not in rules]

    def keepRules(self, rules):
        self.list = [x for x in self.list if x["stack_id"] in rules]

    def setRuleAliases(self, ruleAliases):
        id_to_stack = {stack["stack_id"]: stack for stack in self.list}
        for rule_id, alias in ruleAliases.items():
            id_to_stack[rule_id]["alias"] = alias

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
