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

    @classmethod
    def fetchHTML(cls, url, requestArguments = None):
        requestArguments = requestArguments or {}
        headers = dict(cls.request_headers)
        if url:
            headers["Host"] = urlparse(url).netloc

        user_headers = requestArguments.pop("headers", {})
        headers.update(user_headers)
        response = requests.get(url, headers = headers, **requestArguments)
        if response.encoding == "ISO-8859-1" and not "ISO-8859-1" in response.headers.get(
            "Content-Type", ""
        ):
            response.encoding = response.apparent_encoding
            html = response.text
            return html
        
    @classmethod
    def getScrapedHTML(cls, url = None, html = None, requestArguments = None):
        if html:
            html = normalize(unescape(html))
            return BeautifulSoup(html, "lxml")

        html = cls._fetch_html(url, requestArguments)
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

        if text_match(text, childElementText, fuzzinessRatio):
            parentText = child.parent.getText().strip()
            if childElementText == parentText and child.parent.parent:
                return False

            child.wanted_attr = None
            return True

        if text_match(text, get_non_rec_text(child), fuzzinessRatio):
            child.is_non_rec_text = True
            child.wanted_attr = None
            return True

        for key, value in child.attrs.items():
            if not isinstance(value, str):
                continue

            value = value.strip()

            if text_match(text, value, fuzzinessRatio):
                child.wanted_attr = key
                return True

            if key in {"href", "src"}:
                full_url = urljoin(url, value)
                if text_match(text, full_url, fuzzinessRatio):
                    child.wanted_attr = key
                    child.is_full_url = True
                    return True

        return False
    
    def getChildren(self, soup, text, url, textFuzzinessRatio):
        children = reversed(soup.findChildren())
        children = [x for x in children if self._child_has_text(x, text, url, textFuzzinessRatio)]
        return children

    def build(self, url = None, wanted_list = None, wanted_dict = None, html = None, requestArguments = None, update = False, textFuzzinessRatio = 1.0):
        soup = self.getSoup(url = url, html = html, requestArguments = requestArguments)
        result_list = []

        if update is False:
            self.list = []

        if wanted_list:
            wanted_dict = {"": wanted_list}

        wanted_list = []

        for alias, wanted_items in wanted_dict.items():
            wanted_items = [normalize(w) for w in wanted_items]
            wanted_list += wanted_items

            for wanted in wanted_items:
                children = self.getChildren(soup, wanted, url, textFuzzinessRatio)

                for child in children:
                    result, stack = self.getResultForChildElement(child, soup, url)
                    stack["alias"] = alias
                    result_list += result
                    self.list.append(stack)

        result_list = [item.text for item in result_list]
        result_list = unique_hashable(result_list)

        self.list = unique_stack_list(self.list)
        return result_list

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
        stack["stack_id"] = "rule_" + get_random_str(4)
        return stack

    def getResultForChildElement(self, child, soup, url):
        stack = self._build_stack(child, url)
        result = self.getResultWithStack(stack, soup, url, 1.0)
        return result, stack

    @staticmethod
    def fetchResultFromChildElement(child, wanted_attr, is_full_url, url, is_non_rec_text):
        if wanted_attr is None:
            if is_non_rec_text:
                return get_non_rec_text(child)
            return child.getText().strip()

        if wanted_attr not in child.attrs:
            return None

        if is_full_url:
            return urljoin(url, child.attrs[wanted_attr])

        return child.attrs[wanted_attr]

    @staticmethod
    def getFuzzyAttributes(attrs, attr_fuzz_ratio):
        attrs = dict(attrs)
        for key, val in attrs.items():
            if isinstance(val, str) and val:
                val = FuzzyText(val, attr_fuzz_ratio)
            elif isinstance(val, (list, tuple)):
                val = [FuzzyText(x, attr_fuzz_ratio) if x else x for x in val]
            attrs[key] = val
        return attrs

    def getResultWithStack(self, stack, soup, url, attr_fuzz_ratio, **kwargs):
        parents = [soup]
        stack_content = stack["content"]
        contain_sibling_leaves = kwargs.get("contain_sibling_leaves", False)
        for index, item in enumerate(stack_content):
            children = []
            if item[0] == "[document]":
                continue
            for parent in parents:

                attrs = item[1]
                if attr_fuzz_ratio < 1.0:
                    attrs = self._get_fuzzy_attrs(attrs, attr_fuzz_ratio)

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
        if not kwargs.get("keep_blank", False):
            result = [x for x in result if x.text]
        return result

    def getResultUsingBasisListIndex(self, stack, soup, url, attr_fuzz_ratio, **kwargs):
        p = soup.findChildren(recursive=False)[0]
        stack_content = stack["content"]
        for index, item in enumerate(stack_content[:-1]):
            if item[0] == "[document]":
                continue
            content = stack_content[index + 1]
            attrs = content[1]
            if attr_fuzz_ratio < 1.0:
                attrs = self._get_fuzzy_attrs(attrs, attr_fuzz_ratio)
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
        if not kwargs.get("keep_blank", False):
            result = [x for x in result if x.text]
        return result

    def getResultByFunction(self, func, url, html, soup, requestArguments, grouped, group_by_alias, unique, attr_fuzz_ratio, **kwargs):
        if not soup:
            soup = self.getSoup(url = url, html = html, requestArguments = requestArguments)

        keep_order = kwargs.get("keep_order", False)

        if group_by_alias or (keep_order and not grouped):
            for index, child in enumerate(soup.findChildren()):
                setattr(child, "child_index", index)

        result_list = []
        grouped_result = defaultdict(list)
        for stack in self.list:
            if not url:
                url = stack.get("url", "")

            result = func(stack, soup, url, attr_fuzz_ratio, **kwargs)

            if not grouped and not group_by_alias:
                result_list += result
                continue

            group_id = stack.get("alias", "") if group_by_alias else stack["stack_id"]
            grouped_result[group_id] += result

        return self.cleanResult(result_list, grouped_result, grouped, group_by_alias, unique, keep_order)

    @staticmethod
    def cleanResult(result_list, grouped_result, grouped, grouped_by_alias, unique, keep_order):
        if not grouped and not grouped_by_alias:
            if unique is None:
                unique = True
            if keep_order:
                result_list = sorted(result_list, key=lambda x: x.index)
            result = [x.text for x in result_list]
            if unique:
                result = unique_hashable(result)
            return result

        for k, val in grouped_result.items():
            if grouped_by_alias:
                val = sorted(val, key=lambda x: x.index)
            val = [x.text for x in val]
            if unique:
                val = unique_hashable(val)
            grouped_result[k] = val

        return dict(grouped_result)

    def getSimilarResults(self, url = None, html = None, soup = None, requestArguments = None, grouped = False, group_by_alias = False, unique = None, attr_fuzz_ratio = 1.0, keep_blank = False, keep_order = False, contain_sibling_leaves = False):
        function = self.getResultWithStack
        return self.getResultByFunction(function, url, html, soup, requestArguments, grouped, group_by_alias, unique, attr_fuzz_ratio, keep_blank = keep_blank, keep_order = keep_order, contain_sibling_leaves = contain_sibling_leaves)

    def getExactResults(self, url = None, html = None, soup = None, requestArguments = None, grouped = False, group_by_alias = False, unique = None, attr_fuzz_ratio = 1.0, keep_blank = False):
        function = self.getResultUsingBasisListIndex
        return self.getResultByFunction(function, url, html, soup, requestArguments, grouped, group_by_alias, unique, attr_fuzz_ratio, keep_blank = keep_blank)

    def getResults(self, url = None, html = None, requestArguments = None, grouped = False, group_by_alias = False, unique = None, attr_fuzz_ratio = 1.0):
        soup = self.getSoup(url = url, html = html, requestArguments = requestArguments)
        args = dict(url = url, soup = soup, grouped = grouped, group_by_alias = group_by_alias, unique = unique, attr_fuzz_ratio = attr_fuzz_ratio)
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
