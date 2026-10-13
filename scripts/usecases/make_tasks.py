#!/usr/bin/env python3
"""Writes tasks.json: 48 use-case tasks, 8 in each of six groups (chat, reasoning,
code, debugging, summaries, creative writing). These are the categories of the usual
"tokens per second by use case" chart, but here every answer is also checked by code:
code and bug fixes run against unit tests, the rest against fixed rules.
Each task carries a reference answer that must pass and wrong answers that must fail
(python3 score.py --selftest tasks.json). Synthetic content only."""
import json, os, textwrap

TASKS = []
CAP = {'chat': 384, 'reason': 1536, 'code': 1536, 'debug': 1536, 'summary': 512, 'creative': 512}


def add(id, cat, user, check, ref, bad, history=None):
    messages = list(history or []) + [{'role': 'user', 'content': user}]
    TASKS.append({'id': id, 'cat': cat, 'max_tokens': CAP[cat], 'messages': messages,
                  'check': check, 'ref': ref, 'bad': bad})


def code(s):
    return textwrap.dedent(s).strip()


def fence(s):
    return '```python\n' + code(s) + '\n```'


# ---- chat / Q&A ------------------------------------------------------------
add('c1', 'chat', 'Which planet is known as the Red Planet?',
    {'re': [r'\bmars\b']}, 'Mars is known as the Red Planet.', ['Jupiter is called the Red Planet.'])
add('c2', 'chat', 'What does NAS stand for in computer storage?',
    {'re': [r'network[\s-]*attached[\s-]*storage']}, 'NAS stands for Network Attached Storage.',
    ['NAS stands for New Application Server.'])
add('c3', 'chat', 'How many minutes are there in one day?',
    {'re': [r'\b1,?440\b'], 'not_re': [r'(?<![\d,])(?!1,?440\b)\d[\d,]{2,}\s*minutes']}, 'There are 1,440 minutes in a day.',
    ['There are 1,400 minutes in a day.', 'There are 1440 minutes in a day. Leap years have 1461 minutes.'])
add('c4', 'chat', 'What is the capital of Australia?',
    {'re': [r'canberra']}, 'The capital of Australia is Canberra.', ['The capital of Australia is Sydney.'])
add('c5', 'chat', 'Who painted the Mona Lisa?',
    {'re': [r'leonardo|vinci']}, 'Leonardo da Vinci painted the Mona Lisa.', ['Michelangelo painted it.'])
add('c6', 'chat', 'Which country will I be visiting?',
    {'re': [r'portugal']}, "You'll be visiting Portugal.", ["You'll be visiting Spain."],
    history=[{'role': 'user', 'content': "Hi! I'm planning a trip. I'm flying from Denver to Lisbon next month."},
             {'role': 'assistant', 'content': 'That sounds exciting! How can I help you plan it?'}])
add('c7', 'chat', 'How many pets do I have in total? Reply with just the number.',
    {'re': [r'\b(5|five)\b']}, '5', ['3'],
    history=[{'role': 'user', 'content': 'I have 3 cats and 2 dogs.'},
             {'role': 'assistant', 'content': "That's a lively household! What would you like to know?"}])
add('c8', 'chat', 'In which year did the Berlin Wall fall?',
    {'re': [r'\b1989\b']}, 'The Berlin Wall fell in 1989.', ['The Berlin Wall fell in 1991.'])

# ---- reasoning -------------------------------------------------------------
TAIL = '\nFinish with a final line in the form: Answer: <answer>'
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
add('r1', 'reason', 'A train leaves at 09:40 and the journey takes 2 hours 35 minutes. At what time does it arrive? Give the time as HH:MM in 24-hour format.' + TAIL,
    {'answer': {'re': r'\b12[:.]15\b'}}, '09:40 + 2:35 = 12:15\nAnswer: 12:15', ['Answer: 11:15', 'Answer: 12:05'])
add('r2', 'reason', 'Tom is taller than Ana. Ana is taller than Raj. Raj is taller than Lee. Who is the second shortest?' + TAIL,
    {'answer': {'first': ['Tom', 'Ana', 'Raj', 'Lee'], 'want': 'Raj'}}, 'Order: Tom, Ana, Raj, Lee.\nAnswer: Raj',
    ['Answer: Lee', 'Answer: Ana'])
add('r3', 'reason', 'Today is Wednesday. What day of the week will it be 100 days from today?' + TAIL,
    {'answer': {'first': DAYS, 'want': 'Friday'}}, '100 = 14 weeks + 2 days.\nAnswer: Friday', ['Answer: Thursday'])
add('r4', 'reason', 'Five people are in a room. Each person shakes hands with every other person exactly once. How many handshakes are there in total?' + TAIL,
    {'answer': {'num': 10}}, '5 * 4 / 2 = 10\nAnswer: 10', ['Answer: 20', 'Answer: 25'])
add('r5', 'reason', 'What is the smaller angle between the hour hand and the minute hand of a clock at 3:15, in degrees?' + TAIL,
    {'answer': {'num': 7.5}}, 'The hour hand is 7.5 degrees past the 3.\nAnswer: 7.5', ['Answer: 0', 'Answer: 90'])
add('r6', 'reason', 'Five runners finished a race. Ada finished first and Ben finished last. Cara finished before Eve, and Eve finished before Dan. Who finished third?' + TAIL,
    {'answer': {'first': ['Ada', 'Ben', 'Cara', 'Dan', 'Eve'], 'want': 'Eve'}}, 'Ada, Cara, Eve, Dan, Ben.\nAnswer: Eve',
    ['Answer: Cara', 'Answer: Dan'])
add('r7', 'reason', 'A meeting needs 90 minutes in a row between 09:00 and 17:00. Nobody meets during lunch, from 12:00 to 13:00. Ann is busy from 09:00 to 10:00 and from 14:00 to 16:00. What is the earliest time the meeting can start? Give the time as HH:MM in 24-hour format.' + TAIL,
    {'answer': {'re': r'\b10[:.]00\b'}}, '10:00 to 11:30 is free.\nAnswer: 10:00', ['Answer: 13:00', 'Answer: 16:00'])
add('r8', 'reason', 'A farmer has 17 sheep. All but 9 run away. How many sheep does the farmer have left?' + TAIL,
    {'answer': {'num': 9}}, 'All but 9 ran away, so 9 are left.\nAnswer: 9', ['Answer: 8'])

# ---- code generation (Python, hidden unit tests) ----------------------------
def gen(id, sig, desc, examples, tests, ref, bad):
    user = (f'Write a Python function `{sig}` that {desc}\n\nExamples:\n{examples}\n\n'
            'Reply with only the code, in a single ```python code block.')
    add(id, 'code', user, {'python': code(tests)}, fence(ref), [fence(b) for b in bad])


gen('g1', 'parse_duration(s: str) -> int',
    "converts a duration such as '1h30m', '45s' or '2h5m10s' into a number of seconds. The string has one or more parts, each a whole number followed by h (hours), m (minutes) or s (seconds), in that order.",
    "parse_duration('1h30m') == 5400\nparse_duration('45s') == 45",
    """
    assert parse_duration('1h30m') == 5400
    assert parse_duration('45s') == 45
    assert parse_duration('2h') == 7200
    assert parse_duration('1h1m1s') == 3661
    assert parse_duration('10m5s') == 605
    assert parse_duration('0s') == 0
    assert parse_duration('100m') == 6000
    assert parse_duration('2h5m10s') == 7510
    """,
    """
    import re

    def parse_duration(s):
        return sum(int(n) * {'h': 3600, 'm': 60, 's': 1}[u] for n, u in re.findall(r'(\\d+)([hms])', s))
    """,
    ["""
    def parse_duration(s):
        h = m = 0
        if 'h' in s:
            h, s = s.split('h')
        if 'm' in s:
            m, s = s.split('m')
        return int(h or 0) * 3600 + int(m or 0) * 60
    """])

gen('g2', 'rle(s: str) -> str',
    'run-length encodes a string: each run of the same character becomes that character followed by the length of the run.',
    "rle('aaabcc') == 'a3b1c2'\nrle('') == ''",
    """
    assert rle('aaabcc') == 'a3b1c2'
    assert rle('') == ''
    assert rle('aaabccdddd') == 'a3b1c2d4'
    assert rle('abc') == 'a1b1c1'
    assert rle('zzzzzzzzzzzz') == 'z12'
    assert rle('aabbaa') == 'a2b2a2'
    """,
    """
    from itertools import groupby

    def rle(s):
        return ''.join(f'{ch}{len(list(run))}' for ch, run in groupby(s))
    """,
    ["""
    from collections import Counter

    def rle(s):
        return ''.join(f'{ch}{n}' for ch, n in Counter(s).items())
    """])

gen('g3', 'is_balanced(s: str) -> bool',
    'returns True if every bracket in s, meaning (), [] and {}, is closed in the right order, and False otherwise. Other characters are ignored.',
    "is_balanced('a(b[c]{d})') == True\nis_balanced('([)]') == False",
    """
    assert is_balanced('a(b[c]{d})') == True
    assert is_balanced('([)]') == False
    assert is_balanced('') == True
    assert is_balanced('((') == False
    assert is_balanced('}{') == False
    assert is_balanced('{[()()]}') == True
    assert is_balanced('x)') == False
    """,
    """
    def is_balanced(s):
        pairs, stack = {')': '(', ']': '[', '}': '{'}, []
        for ch in s:
            if ch in '([{':
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack.pop() != pairs[ch]:
                    return False
        return not stack
    """,
    ["""
    def is_balanced(s):
        return all(s.count(a) == s.count(b) for a, b in ['()', '[]', '{}'])
    """])

gen('g4', 'merge_intervals(intervals: list[list[int]]) -> list[list[int]]',
    'merges overlapping intervals and returns them sorted by their start. Intervals that touch, like [1, 4] and [4, 5], also merge.',
    'merge_intervals([[1, 3], [2, 6], [8, 10]]) == [[1, 6], [8, 10]]',
    """
    def _as_lists(x):
        return [list(i) for i in x]
    assert _as_lists(merge_intervals([[1, 3], [2, 6], [8, 10]])) == [[1, 6], [8, 10]]
    assert _as_lists(merge_intervals([])) == []
    assert _as_lists(merge_intervals([[1, 4], [4, 5]])) == [[1, 5]]
    assert _as_lists(merge_intervals([[5, 6], [1, 2]])) == [[1, 2], [5, 6]]
    assert _as_lists(merge_intervals([[1, 10], [2, 3]])) == [[1, 10]]
    assert _as_lists(merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]])) == [[1, 6], [8, 10], [15, 18]]
    """,
    """
    def merge_intervals(intervals):
        out = []
        for a, b in sorted(intervals):
            if out and a <= out[-1][1]:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return out
    """,
    ["""
    def merge_intervals(intervals):
        out = []
        for a, b in sorted(intervals):
            if out and a < out[-1][1]:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return out
    """])

gen('g5', 'top_words(text: str, k: int) -> list[str]',
    'returns the k most common words in text, most common first. Words are runs of the letters a-z, compared without regard to case and returned in lowercase. Break ties alphabetically. If there are fewer than k different words, return all of them.',
    "top_words('the cat and the hat and the bat', 2) == ['the', 'and']",
    """
    assert top_words('the cat and the hat and the bat', 2) == ['the', 'and']
    assert top_words('B a b A c', 3) == ['a', 'b', 'c']
    assert top_words('Hello, hello! World.', 1) == ['hello']
    assert top_words('one two', 5) == ['one', 'two']
    assert top_words('', 3) == []
    assert top_words('Red, red; BLUE. green? red!', 2) == ['red', 'blue']
    """,
    """
    import re
    from collections import Counter

    def top_words(text, k):
        counts = Counter(re.findall(r'[a-z]+', text.lower()))
        return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]
    """,
    ["""
    import re
    from collections import Counter

    def top_words(text, k):
        return [w for w, _ in Counter(re.findall(r'[a-z]+', text.lower())).most_common(k)]
    """])

gen('g6', 'parse_csv_line(line: str) -> list[str]',
    'splits one line of CSV into its fields. Fields are separated by commas. A field may be wrapped in double quotes; then it can contain commas, and two double quotes in a row inside it stand for one double-quote character.',
    "parse_csv_line('a,b,c') == ['a', 'b', 'c']\nparse_csv_line('\"x,y\",z') == ['x,y', 'z']",
    r'''
    assert parse_csv_line('a,b,c') == ['a', 'b', 'c']
    assert parse_csv_line('"x,y",z') == ['x,y', 'z']
    assert parse_csv_line('"he said ""hi""",2') == ['he said "hi"', '2']
    assert parse_csv_line('a,,b') == ['a', '', 'b']
    assert parse_csv_line('1,"",3') == ['1', '', '3']
    assert parse_csv_line('solo') == ['solo']
    ''',
    """
    import csv

    def parse_csv_line(line):
        return next(csv.reader([line]))
    """,
    ["""
    def parse_csv_line(line):
        return [f.strip('"') for f in line.split(',')]
    """])

gen('g7', 'luhn_valid(number: str) -> bool',
    'checks a card number with the Luhn algorithm and returns True if it is valid. Spaces in the string are ignored.',
    "luhn_valid('4539 1488 0343 6467') == True\nluhn_valid('8273 1232 7352 0569') == False",
    """
    assert luhn_valid('4539 1488 0343 6467') == True
    assert luhn_valid('8273 1232 7352 0569') == False
    assert luhn_valid('79927398713') == True
    assert luhn_valid('79927398710') == False
    assert luhn_valid('4111 1111 1111 1111') == True
    assert luhn_valid('1234 5678 9012 3456') == False
    """,
    """
    def luhn_valid(number):
        digits = [int(c) for c in number if c != ' ']
        total = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 1:
                d = d * 2 - 9 if d > 4 else d * 2
            total += d
        return total % 10 == 0
    """,
    ["""
    def luhn_valid(number):
        digits = [int(c) for c in number if c != ' ']
        total = 0
        for i, d in enumerate(digits):
            if i % 2 == 0:
                d = d * 2 - 9 if d > 4 else d * 2
            total += d
        return total % 10 == 0
    """])

gen('g8', 'semver_cmp(a: str, b: str) -> int',
    "compares two version strings made of dot-separated whole numbers, like '1.2.10'. Return -1 if a is lower, 0 if they are equal and 1 if a is higher. Compare each part as a number.",
    "semver_cmp('1.2.10', '1.2.9') == 1\nsemver_cmp('1.0', '1.0') == 0",
    """
    assert semver_cmp('1.2.10', '1.2.9') == 1
    assert semver_cmp('1.0', '1.0') == 0
    assert semver_cmp('0.9.9', '1.0.0') == -1
    assert semver_cmp('2.10.0', '2.9.12') == 1
    assert semver_cmp('1.2.3', '1.2.4') == -1
    assert semver_cmp('10.0.1', '9.99.99') == 1
    """,
    """
    def semver_cmp(a, b):
        x, y = [tuple(int(p) for p in v.split('.')) for v in (a, b)]
        return (x > y) - (x < y)
    """,
    ["""
    def semver_cmp(a, b):
        return (a > b) - (a < b)
    """])

# ---- debugging (fix the shown bug; same unit-test checks) --------------------
def debug(id, buggy, symptom, tests, ref):
    user = (f'This Python function has a bug:\n\n```python\n{code(buggy)}\n```\n\n{symptom} '
            'Fix the bug. Reply with only the corrected function, in a single ```python code block.')
    add(id, 'debug', user, {'python': code(tests)}, fence(ref), [fence(buggy)])


debug('d1', '''
    def find_index(xs, target):
        """Return the index of target in the sorted list xs, or -1 if it is not there."""
        lo, hi = 0, len(xs) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if xs[mid] == target:
                return mid
            if xs[mid] < target:
                lo = mid + 1
            else:
                hi = mid - 1
        return -1
    ''', 'find_index([1, 2, 3], 3) returns -1, but it should return 2.', """
    assert find_index([1, 2, 3], 3) == 2
    assert find_index([1, 2, 3], 1) == 0
    assert find_index([5], 5) == 0
    assert find_index([], 1) == -1
    assert find_index([1, 3, 5, 7], 4) == -1
    assert find_index([1, 3, 5, 7], 7) == 3
    assert find_index([1, 3, 5, 7, 9, 11], 9) == 4
    """, '''
    def find_index(xs, target):
        lo, hi = 0, len(xs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if xs[mid] == target:
                return mid
            if xs[mid] < target:
                lo = mid + 1
            else:
                hi = mid - 1
        return -1
    ''')

debug('d2', '''
    def add_tag(tag, tags=[]):
        """Add tag to the list of tags and return the list."""
        tags.append(tag)
        return tags
    ''', "Calling add_tag('a') and then add_tag('b') gives ['a', 'b'] on the second call, but it should give ['b'].", """
    assert add_tag('a') == ['a']
    assert add_tag('b') == ['b']
    assert add_tag('c', ['x']) == ['x', 'c']
    """, '''
    def add_tag(tag, tags=None):
        if tags is None:
            tags = []
        tags.append(tag)
        return tags
    ''')

debug('d3', '''
    def average(nums):
        """Return the mean of a list of numbers."""
        return sum(nums) // len(nums)
    ''', 'average([1, 2]) returns 1 instead of 1.5, and average([]) crashes. It should return 0.0 for an empty list.', """
    assert average([1, 2]) == 1.5
    assert average([]) == 0.0
    assert average([4]) == 4
    assert average([1, 2, 3, 4]) == 2.5
    assert average([-1, 1]) == 0
    """, '''
    def average(nums):
        return sum(nums) / len(nums) if nums else 0.0
    ''')

debug('d4', '''
    def dedupe(items):
        """Remove repeated items, keeping the first time each one appears."""
        return list(set(items))
    ''', "dedupe(['b', 'a', 'b', 'c']) should return ['b', 'a', 'c'], but the items come back in a different order.", """
    assert dedupe(['b', 'a', 'b', 'c']) == ['b', 'a', 'c']
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
    assert dedupe([]) == []
    assert dedupe(['x']) == ['x']
    """, '''
    def dedupe(items):
        return list(dict.fromkeys(items))
    ''')

debug('d5', '''
    def remove_evens(nums):
        """Return the list with every even number removed."""
        for n in nums:
            if n % 2 == 0:
                nums.remove(n)
        return nums
    ''', 'remove_evens([2, 4, 6, 7]) returns [4, 7], but it should return [7].', """
    assert remove_evens([2, 4, 6, 7]) == [7]
    assert remove_evens([1, 3]) == [1, 3]
    assert remove_evens([]) == []
    assert remove_evens([2, 2, 3]) == [3]
    assert remove_evens([1, 2, 3, 4, 5, 6]) == [1, 3, 5]
    """, '''
    def remove_evens(nums):
        return [n for n in nums if n % 2 != 0]
    ''')

debug('d6', '''
    def largest(numbers_as_text):
        """numbers_as_text is a list like ['9', '10', '2']. Return the largest value as an int."""
        return int(max(numbers_as_text))
    ''', "largest(['9', '10', '2']) returns 9, but it should return 10.", """
    assert largest(['9', '10', '2']) == 10
    assert largest(['-5', '-12']) == -5
    assert largest(['100']) == 100
    assert largest(['3', '30', '4']) == 30
    """, '''
    def largest(numbers_as_text):
        return max(int(n) for n in numbers_as_text)
    ''')

debug('d7', '''
    def is_leap_year(year):
        """Return True if year is a leap year in the Gregorian calendar."""
        return year % 4 == 0
    ''', 'is_leap_year(1900) returns True, but 1900 was not a leap year (2000 was).', """
    assert is_leap_year(2024) == True
    assert is_leap_year(1900) == False
    assert is_leap_year(2000) == True
    assert is_leap_year(2023) == False
    assert is_leap_year(2100) == False
    assert is_leap_year(2400) == True
    """, '''
    def is_leap_year(year):
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    ''')

debug('d8', '''
    def make_multipliers():
        """Return three functions that multiply their input by 0, 1 and 2."""
        return [lambda x: x * i for i in range(3)]
    ''', 'make_multipliers()[0](10) returns 20, but it should return 0.', """
    fs = make_multipliers()
    assert len(fs) == 3
    assert [f(10) for f in fs] == [0, 10, 20]
    assert fs[1](7) == 7
    """, '''
    def make_multipliers():
        return [lambda x, i=i: x * i for i in range(3)]
    ''')

# ---- summaries --------------------------------------------------------------
def summ(id, what, how, text, check, ref, bad):
    add(id, 'summary', f'Summarize this {what} {how}.\n\n{text}', check, ref, bad)


summ('s1', 'meeting note', 'in at most 40 words',
     "Notes from Tuesday's project meeting. The website relaunch was planned for May 4, but it will now go live on May 18. The payment provider asked for two more weeks to finish security testing, and the team agreed not to launch without it. Priya will own the testing plan and send a daily update to the group. The budget stays at $12,000, and no new features will be added before launch. Marketing will hold the launch emails until the new date is confirmed. Jordan raised a concern about the support team's holiday schedule in late May; he will check who is available and report back on Friday. The next meeting is on Tuesday at 10:00.",
     {'max_words': 40, 're': [r'\b(may\s*18(th)?|18(th)?\s*(of\s*)?may)\b', r'payment|security', r'priya']},
     'The website relaunch moves from May 4 to May 18 so the payment provider can finish security testing. Priya owns the testing plan; the $12,000 budget and feature freeze stay.',
     ['The relaunch is still on May 4. Jordan will check the support schedule.'])
summ('s2', 'release note', "as exactly 3 bullet points, each starting with '- '",
     'FotoBox 3.2 is out today. The biggest change is offline albums: you can now mark any album to keep it on your phone and view it without a connection. We also fixed a crash that happened when importing HEIC photos on Android 14. Sharing links now expire after 30 days by default, though you can change this in Settings. Finally, this is the last version that supports iOS 15; FotoBox 3.3 will need iOS 16 or later. The update is free and will reach all users over the next seven days.',
     {'bullets': 3, 're': [r'offline']},
     '- Offline albums: keep any album on your phone and view it without a connection.\n- Fixes the HEIC import crash on Android 14.\n- Last version for iOS 15; 3.3 needs iOS 16.',
     ['- Offline albums are new.\n- HEIC crash fixed.', '- Sharing links expire after 30 days.\n- HEIC crash fixed.\n- iOS 15 support ends.',
      '- - Offline albums work without a connection.\n- - HEIC crash fixed.\n- - Last version for iOS 15.'])
summ('s3', 'customer email', 'in one sentence of at most 30 words, for a support agent',
     "Hello, I ordered a Bravo 600 blender last week (order #48213) and it arrived yesterday with a cracked jar. The box looked fine, so I think it was packed that way. I've had Bravo blenders before and I like them, so I don't want a refund. I'd just like a replacement jar sent out, ideally before Saturday, because I'm making smoothies for my daughter's party. I can send photos if you need them. Thanks, Maria",
     {'max_words': 30, 're': [r'48213', r'crack|broken|damag', r'replac'],
      'not_re': [r'\bordered\s+(?:a|an|the)\s+(?:(?:cracked|broken|damaged|replacement)\s+)?jar\b']},
     'Order #48213: the blender jar arrived cracked; Maria wants a replacement jar before Saturday, not a refund.',
     ['Maria wants a refund for order #48213 because the blender arrived cracked.',
      'Maria ordered a cracked jar for her Bravo 600 blender (order #48213) and wants a replacement before Saturday.'])
summ('s4', 'news story', 'in at most 35 words',
     'The Millbrook city council voted 5-2 on Monday night to build a new public library on Elm Street, replacing the 60-year-old building on Main Street. Construction will begin in March 2027 and is expected to take 18 months. The project will cost $8.4 million; a state grant covers $6 million and the city will pay the rest from its reserve fund. Two council members voted against the plan, saying the city should first repair its roads. The old library will stay open until the new one is finished, and the city has not yet decided what to do with the Main Street building.',
     {'max_words': 35, 're': [r'elm', r'8\.4', r'2027']},
     'Millbrook council voted 5-2 to build an $8.4 million library on Elm Street, mostly grant-funded. Construction starts March 2027 and takes 18 months; the old library stays open meanwhile.',
     ['Millbrook will repair its roads before building a library on Main Street in 2027.'])
summ('s5', 'incident report', 'in at most 45 words',
     'Incident report, 12 October. At 02:10 the nightly backup job filled the disk on server nas-02. With no free space, the photo service stopped accepting uploads, and it stayed down for 47 minutes until the on-call engineer, Sam, cleared old logs at 02:57. The root cause was a software update on 9 October that turned off log rotation by mistake, so logs had grown for three days. Fixes: log rotation is back on, and a new alert now fires when any disk is 85% full. No photos were lost.',
     {'max_words': 45, 're': [r'disk|space|storage', r'\blog', r'alert|85\s*%']},
     'A full disk on nas-02 stopped photo uploads for 47 minutes. An update had disabled log rotation. Rotation is back on and an alert now fires at 85% disk use. No photos were lost.',
     ['The photo service was down for 47 minutes because of a network outage. No photos were lost.'])
summ('s6', 'recipe', 'as a numbered list of at most 5 steps',
     'To make the traybake, first heat the oven to 200°C. While it heats, chop two peppers, one red onion and 400 g of potatoes into bite-sized pieces. Toss everything with two tablespoons of olive oil, a teaspoon of smoked paprika and a pinch of salt. Spread the vegetables in a single layer on a large baking tray, and use two trays if they are crowded, or they will steam instead of roasting. Roast for 25 minutes, turning once halfway through, until the edges are brown. Scatter over a handful of chopped parsley and serve with yogurt.',
     {'numbered': [2, 5], 're': [r'200', r'25\s*min']},
     '1. Heat the oven to 200°C.\n2. Chop the peppers, onion and potatoes.\n3. Toss with oil, paprika and salt.\n4. Spread on a tray and roast for 25 minutes, turning once.\n5. Add parsley and serve with yogurt.',
     ['1. Heat the oven.\n2. Chop the vegetables.\n3. Roast until brown.',
      '1. Heat to 200°C.\n2. Chop.\n3. Toss.\n4. Spread.\n5. Roast 25 minutes.\n6. Serve.'])
summ('s7', 'science text', 'for a 10-year-old, in at most 30 words',
     'Photosynthesis is the process plants use to make their own food. Inside the leaves are tiny structures called chloroplasts, which contain a green pigment called chlorophyll. Chlorophyll absorbs energy from sunlight. The plant uses that energy to combine water, which it takes up through its roots, with carbon dioxide, which it takes in from the air through small holes in its leaves. The result is glucose, a sugar the plant uses for energy and growth, and oxygen, which it releases into the air.',
     {'max_words': 30, 're': [r'sun|light', r'oxygen', r'sugar|glucose|food']},
     'Plants use sunlight to turn water and air into sugar, their food, and they give off the oxygen we breathe.',
     ['Plants have green leaves with chlorophyll in them, which is why they look green.'])
summ('s8', 'policy', 'in at most 40 words',
     'Remote work policy, updated 1 September. Employees may work from home up to three days a week. Remote days must be agreed with your manager by Friday of the week before. Exception: new employees must work in the office every day during their first 90 days, so they can meet their team and complete training. Employees who need more remote days for medical or family reasons should speak to HR. Equipment for home offices, such as a monitor or chair, can be claimed up to $300 once a year.',
     {'max_words': 40, 're': [r'\b(3|three)\b[^.]{0,20}\bdays?\b', r'\b90\b|ninety', r'manager']},
     'Staff may work remotely up to three days a week, agreed with their manager by the previous Friday. New hires must be in the office daily for their first 90 days.',
     ['Staff may work remotely up to three days a week and claim $300 a year for equipment.'])

# ---- creative writing (the constraints are checked, not the taste) ----------
ONLY = ' Reply with only the {}.'
add('w1', 'creative', 'Write a haiku about a quiet server room at night.' + ONLY.format('three lines of the haiku'),
    {'lines': 3, 'line_max_words': 9},
    'Fans hum in the dark\nsmall green lights blink through the night\ndata dreams in rows',
    ['Fans hum in the dark\nsmall green lights blink through the night',
     'Here is a haiku about servers.\nFans hum in the dark\nsmall green lights blink through the night\ndata dreams in rows'])
add('w2', 'creative', 'Write a four-line acrostic poem about teamwork using the word CODE: the first letters of the four lines must spell C, O, D, E.' + ONLY.format('poem'),
    {'lines': 4, 'initials': 'CODE'},
    'Coming together, we build\nOne idea at a time\nDividing the hard parts\nEvery voice in the line',
    ['Coming together, we build\nOne idea at a time\nEvery voice in the line\nDividing the hard parts'])
add('w3', 'creative', "Suggest 5 names for a home server. Put each name on its own line, use one word per name, and don't number them." + ONLY.format('names'),
    {'lines': 5, 'line_words': 1, 'distinct': True},
    'Atlas\nHearth\nLantern\nBeacon\nVault',
    ['1. Atlas\n2. Hearth\n3. Lantern\n4. Beacon\n5. Vault', 'Atlas\nHearth\nLantern\nAtlas\nVault', 'Home Base\nAtlas\nHearth\nLantern\nVault'])
add('w4', 'creative', 'Write a two-sentence horror story about a smart fridge.' + ONLY.format('story'),
    {'sentences': 2, 're': [r'fridge|refrigerator']},
    'Every night my smart fridge orders more meat than I could ever eat. Tonight the delivery note said it was for the thing living behind the freezer drawer.',
    ['My smart fridge orders more meat every night.', 'My fridge hums. It orders meat. The delivery note says it is for the thing behind the drawer.'])
add('w5', 'creative', 'Write a slogan for a solar-powered backpack. It must be fewer than 10 words and include the word "sun".' + ONLY.format('slogan'),
    {'lines': 1, 'max_words': 9, 're': [r'\bsun']},
    'Carry the sun, charge your world.',
    ['Carry the power of the stars wherever you go.', 'Carry the sun with you and charge every single device you own today.'])
add('w6', 'creative', 'Write a story about a robot gardener in 40 to 60 words. The very last word must be "rain".' + ONLY.format('story'),
    {'min_words': 40, 'max_words': 60, 'last_word': 'rain'},
    'Every morning, Unit 7 rolled between the tomato rows, counting leaves and humming old songs it had learned from the radio. The soil was cracked and the seedlings drooped. Unit 7 could not cry, but it lifted its metal face to the grey clouds and waited, patient as a seed, for the first drops of rain.',
    ['Unit 7 waited for the rain.', 'Every morning, Unit 7 rolled between the tomato rows, counting leaves and humming old songs it had learned from the radio. The soil was cracked and the seedlings drooped. Unit 7 could not cry, but it lifted its metal face to the grey clouds and waited, patient as a seed, for the storm.'])
add('w7', 'creative', 'Write a four-line poem about the night sky in which every line ends with a word that rhymes with "light".' + ONLY.format('poem'),
    {'lines': 4, 'line_end_re': r'^(?!light$).*(ight|ite|yte)$'},
    'The moon climbs slowly into the night\nA thousand stars are burning bright\nA comet streaks in silver flight\nAnd the whole sky glows soft and white',
    ['The moon climbs slowly into the night\nA thousand stars are burning bright\nA comet streaks across the sky\nAnd the whole sky glows soft and white',
     'The stars ignite in silent light\nThe moon casts shadows on the night\nA galaxy of endless sight\nThe universe in quiet light'])
add('w8', 'creative', 'Describe the ocean in exactly 12 words.' + ONLY.format('12 words'),
    {'words': 12},
    'Endless blue water, restless and deep, hiding mountains, whales and ancient secrets.',
    ['Endless blue water, restless and deep, hiding mountains and whales.', 'The ocean is endless blue water, restless and deep, hiding mountains, whales and secrets.'])

CATS = {'chat': 'Chat / Q&A', 'reason': 'Reasoning', 'code': 'Code gen', 'debug': 'Debug code',
        'summary': 'Summarization', 'creative': 'Creativity'}
assert len(TASKS) == 48 and len({t['id'] for t in TASKS}) == 48
for c in CATS:
    assert sum(t['cat'] == c for t in TASKS) == 8, c
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump({'version': 1, 'categories': CATS, 'tasks': TASKS}, f, indent=1, ensure_ascii=False)
print(f'wrote {out}: {len(TASKS)} tasks')
