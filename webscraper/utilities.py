from collections import OrderedDict
import random
import string
import unicodedata
from difflib import SequenceMatcher

def uniqueList(list):
    seen = set()
    uniqueList = []

    for stack in list:
        hash = stack['hash']

        if hash in seen:
            continue

        uniqueList.append(stack)
        seen.add(hash)

    return uniqueList

def uniqueHashable(hashableItems):
    return list(OrderedDict.fromkeys(hashableItems))

def getRandomString(str):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for i in range(str))

def getNonRecursiveText(element):
    return ''.join(element.find_all(text = True, recursive = False)).strip()

def normalize(item):
    if not isinstance(item, str):
        return item
    
    return unicodedata.normalize("NFKD", item.strip())

def textMatch(t1, t2, ratio_limit):
    if hasattr(t1, 'fullmatch'):
        return bool(t1.fullmatch(t2))
    
    if ratio_limit >= 1:
        return t1 == t2
    
    return SequenceMatcher(None, t1, t2).ratio() >= ratio_limit

class ResultItem():
    def __init__(self, text, index):
        self.text = text
        self.index = index

    def __str__(self):
        return self.text

class FuzzyText(object):
    def __init__(self, text, ratio_limit):
        self.text = text
        self.ratio_limit = ratio_limit
        self.match = None

    def search(self, text):
        return SequenceMatcher(None, self.text, text).ratio() >= self.ratio_limit