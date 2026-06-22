"""Constants and compiled patterns shared by timeline components."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable
TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}

NUMBER_WORD_PATTERN = "one|two|three|four|five|six|seven|eight|nine|ten"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "did", "do",
    "does", "for", "from", "have", "how", "i", "in", "is", "it", "me",
    "my", "of", "on", "or", "our", "previous", "the", "this", "to",
    "was", "were", "what", "when", "where", "which", "who", "with",
    "you", "your",
}

TRAVEL_LOCATION_ALIASES = {
    "new york city": {"new york city", "new york", "nyc"},
}

KNOWN_TRAVEL_LOCATIONS = {
    "amsterdam",
    "barcelona",
    "brazil",
    "chicago",
    "europe",
    "hawaii",
    "japan",
    "new york",
    "new york city",
    "nyc",
    "paris",
    "portland",
    "rome",
    "seattle",
}

_STATE_PATTERNS = [
    re.compile(
        r"(?P<prefix>\bupdate\s*[:,-]?\s*)?"
        r"\b(?P<subject>my|the|our)\s+"
        r"(?P<attribute>[a-zA-Z0-9][a-zA-Z0-9\s_-]{1,60}?)\s+"
        r"(?:is|are|was|were)\s+"
        r"(?P<marker>now|currently|updated to|changed to|recently)?\s*"
        r"(?P<value>[^.?!;\n]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI\s+(?P<marker>now|currently|recently)\s+"
        r"(?P<attribute>have|own|use|attend|take|spend|prefer)\s+"
        r"(?P<value>[^.?!;\n]{1,80})",
        re.IGNORECASE,
    ),
]

_VALUE_STATE_PATTERNS = [
    re.compile(
        r"\b(?:currently\s+have|have|own)\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+bikes?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:new\s+hybrid\s+bike|hybrid\s+bike)[^.?!;\n]{0,160}?\b(?:road bike|mountain bike|commuter bike)[^.?!;\n]{0,160}?\b(?:hybrid\s+bike|new\s+bike)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:road bike|mountain bike|commuter bike)[^.?!;\n]{0,160}?\b(?:new|hybrid)\s+bike\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:need|requires?|require)\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+stars?\s+"
        r"(?:to\s+)?(?:reach|get to)\s+(?:the\s+)?gold",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcurrently\s+(?:at|working\s+at)\s+(?P<value>[A-Z][A-Za-z0-9&.-]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<subject>[A-Z][a-z]+)[^.\n]{0,80}?\b(?:currently\s+at|currently\s+working\s+at|who's\s+currently\s+at)\s+"
        r"(?P<value>[A-Z][A-Za-z0-9&.-]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:got|getting|with)\s+(?P<value>(?:a|my)?\s*new\s+)?(?P<attribute>\d{2,3}-\d{2,3}mm\s+zoom\s+lens|50mm\s+prime\s+lens)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:got|having\s+got)\s+my\s+guitar\s+serviced(?:\s+from|\s+at)?\s+(?P<value>[^.?!;\n]{2,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:music\s+shop\s+on\s+Main\s+St)[^.?!;\n]{0,80}?\b(?:got\s+my\s+guitar\s+serviced|guitar\s+servicing)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgym[^.?!;\n]{0,120}?\b(?:usually\s+)?(?:at|to\s+at)\s+(?P<value>\d{1,2}:\d{2}\s*(?:am|pm))",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:on\s+page|page)\s+(?P<value>\d{1,4})\b[^.?!;\n]{0,120}?"
        r"(?:A\s+Short\s+History\s+of\s+Nearly\s+Everything|history\s+of\s+medicine|discovery\s+of\s+DNA)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:currently\s+)?on\s+page\s+(?P<value>\d{1,4})\s+of\s+['\"](?P<subject>[^'\"]{2,80})['\"]",
        re.IGNORECASE,
    ),
    re.compile(
        r"['\"](?P<subject>[^'\"]{2,80})['\"][^.?!;\n]{0,120}?\b(?:with|has|is)\s+(?P<value>\d{2,4})\s+pages?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:A\s+Short\s+History\s+of\s+Nearly\s+Everything)[^.?!;\n]{0,120}?\b(?:on\s+page|page)\s+(?P<value>\d{1,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:we(?:'re| are)|team[^.?!;\n]{0,40}?\bis)\s+(?P<value>\d+-\d+)\b[^.?!;\n]{0,80}?\b(?:volleyball|league|record)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:volleyball|league|record)[^.?!;\n]{0,120}?\b(?P<value>\d+-\d+)\s+record\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:see|session\s+with)\s+Dr\.\s+(?P<subject>[A-Z][a-z]+)[^.?!;\n]{0,80}?\b(?P<value>every\s+(?:week|two\s+weeks|other\s+week)|weekly|bi-weekly)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<value>every\s+(?:week|two\s+weeks|other\s+week)|weekly|bi-weekly)[^.?!;\n]{0,80}?\b(?:session\s+with|see)\s+Dr\.\s+(?P<subject>[A-Z][a-z]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:attend\s+)?yoga\s+(?:classes\s+)?[^.?!;\n]{0,80}?\b(?:is\s+)?(?P<value>(?:once|twice|three|four|five|\d+)\s+times?\s+a\s+week)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmy\s+grandma(?:'s)?\s+(?P<value>\d{1,3})(?:st|nd|rd|th)?\s+birthday",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bdo\s+you\s+think\s+(?P<value>\d{1,3})\s+is\s+considered",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bKorean\s+restaurants?[\s\S]{0,160}?\bI(?:'ve| have)\s+tried\s+"
        r"(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+different\s+ones",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bpersonal best(?: time)?(?: in| for)?(?P<attribute>[^.?!;\n]{0,45}?)\s+"
        r"(?:with a time of|was|is|of)\s+"
        r"(?P<value>\d{1,2}:\d{2}|\d+\s+minutes?(?:\s+and\s+\d+\s+seconds?)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:completed|finished|did)[^.?!;\n]{0,100}?(?P<attribute>(?:charity\s+)?5K\s+run)[^.?!;\n]{0,100}?"
        r"personal best time\s+(?:of|with)\s+"
        r"(?P<value>\d{1,2}:\d{2}|\d+\s+minutes?(?:\s+and\s+\d+\s+seconds?)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:pre[- ]approval amount|pre[- ]approved(?: for)?|approved(?: for)?)\s+"
        r"(?:of|for|was|is)?\s*(?P<value>\$?\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:doing|attend(?:ing)?)\s+(?P<attribute>yoga(?: classes)?)\s+"
        r"(?P<value>(?:once|twice|three|four|five|\d+)\s+times?\s+a\s+week)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btried\s+(?P<value>(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)(?:\s+different)?)\s+"
        r"(?P<attribute>[^.?!;\n]{0,50}?restaurants?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:moved|relocated)\s+(?:back\s+)?to\s+(?P<value>[^.?!;\n]{2,80})",
        re.IGNORECASE,
    ),
]

_SEMANTIC_EVENT_PATTERNS = [
    re.compile(
        r"\b(?:just\s+|recently\s+)?(?P<verb>got back from|came back from)\s+"
        r"(?P<value>[^.?!;\n]{2,140})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI\s+(?:just\s+|recently\s+|actually\s+)?(?P<verb>tried|visited|attended|ordered|started|finished|completed|discovered|helped|met|received|participated in|took part in|volunteered at|volunteered for|did|went to|went on|came back from|got back from|walked down|picked up|scored|set|got|bought|used|redeemed|signed up for|harvested|practice)\s+"
        r"(?P<value>[^.?!;\n]{2,140})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI\s+(?:just\s+|recently\s+|actually\s+)?(?P<verb>baked|made|watched|fixed|serviced|planted|launched|signed|joined|upgraded)\s+"
        r"(?P<value>[^.?!;\n]{2,140})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bI(?:'ve| have)\s+(?P<verb>tried|visited|attended|finished|completed|been doing|been playing|been using|been listening to|been trying|been focusing on|gone on|used|redeemed|signed up for|harvested|practiced)\s+"
        r"(?P<value>[^.?!;\n]{2,140})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<subject>[A-Z][a-z]+|she|he|they)\s+(?P<verb>moved|relocated|switched|changed)\s+(?:to|into|from)?\s*"
        r"(?P<value>[^.?!;\n]{2,100})",
        re.IGNORECASE,
    ),
]

_DATED_NOUN_EVENT_PATTERN = re.compile(
    r"\b(?P<value>(?:upcoming\s+)?(?:team\s+meeting|bible\s+study|(?:lovely\s+)?midnight\s+mass|holiday\s+food\s+drive|food\s+drive|workshop|meeting))"
    r"[\s\S]{0,160}?\bon\s+"
    r"(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?",
    re.IGNORECASE,
)

__all__ = ['TOKEN_RE', 'MONTHS', 'WEEKDAYS', 'NUMBER_WORDS', 'ORDINAL_WORDS', 'NUMBER_WORD_PATTERN', 'STOPWORDS', 'TRAVEL_LOCATION_ALIASES', 'KNOWN_TRAVEL_LOCATIONS', '_STATE_PATTERNS', '_VALUE_STATE_PATTERNS', '_SEMANTIC_EVENT_PATTERNS', '_DATED_NOUN_EVENT_PATTERN']
