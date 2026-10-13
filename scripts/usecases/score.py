#!/usr/bin/env python3
"""Scores use-case answers (run.js output) against tasks.json.

  python3 score.py --selftest tasks.json          every reference answer must pass, every wrong one fail
  python3 score.py --cases tasks.json cases.json  answers written in other formats, each with the verdict it should get
  python3 score.py tasks.json answers.jsonl ...   one JSON line per answer, then one summary line per model

Code answers are executed, so run this through score.sh, which starts a throwaway
container with no network, a read-only filesystem, a small /tmp and limits on
memory and processes."""
import json, os, re, statistics, subprocess, sys, tempfile

TITLE = re.compile(r'^(#{1,6}\s.*|\*\*[^*]+\*\*:?|__[^_]+__:?)$')
PASSED = '__ALL_TESTS_PASSED__'


def words(t):
    """Words as a reader counts them: split at spaces and at em or en dashes (so
    'fell—rain' is two words), while slashes and hyphens join ('days/week' and
    'sun-kissed' are one). A word needs a letter or digit."""
    return [w for w in re.split(r'[\s—–]+', t) if re.search(r'[A-Za-z0-9]', w)]


def bare(w):
    """A word without the punctuation around it ('rain.' -> 'rain')."""
    return re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', w)


def raw_lines(text):
    text = re.sub(r'^\s*```[\w-]*\s*$', '', text, flags=re.M)
    return [l.strip() for l in text.split('\n') if l.strip()]


def body_lines(text):
    """Non-empty lines, without a title or a 'Here is ...:' line above the answer."""
    ls = raw_lines(text)
    if len(ls) > 1 and (TITLE.match(ls[0]) or ls[0].endswith(':')) and len(words(ls[0])) <= 12:
        ls = ls[1:]
    return ls


def tidy(line):
    """A line without a leading bullet, markdown emphasis or quotes."""
    s = re.sub(r'^[-*•–]\s+', '', line.strip())
    return s.strip('*_`"“”‘’\' \t')


def sentences(text):
    t = ' '.join(tidy(l) for l in body_lines(text)).strip()
    parts = re.split(r'(?<=[.!?…])["\'”’)\]]*\s+(?=["“‘\'(]?[A-Z])', t)
    return [p for p in parts if re.search(r'[A-Za-z]', p)]


def final_answer(text):
    ls = [l.replace('*', '').replace('#', '').strip() for l in raw_lines(text)]
    idx = [i for i, l in enumerate(ls) if re.search(r'\banswer\s*[:：]', l, re.I)]
    if not idx:
        return ls[-1] if ls else ''
    i = idx[-1]
    rest = re.split(r'\banswer\s*[:：]', ls[i], flags=re.I)[-1].strip()
    if not rest and i + 1 < len(ls):
        rest = ls[i + 1]
    return rest


def answer_number(s):
    s = s.replace(',', '')
    if '=' in s:
        s = s.rsplit('=', 1)[1]
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group()) if m else None


def first_of(s, cands):
    best = None
    for c in cands:
        m = re.search(r'\b' + re.escape(c) + r'\b', s, re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), c)
    return best[1] if best else None


def code_of(text):
    blocks = re.findall(r'```[ \t]*(?:python3|python|py)?[ \t]*\n(.*?)```', text, re.S | re.I)
    if blocks:
        return '\n\n'.join(blocks)
    m = re.search(r'```[ \t]*(?:python3|python|py)?[ \t]*\n(.*)$', text, re.S | re.I)  # cut off mid-block
    return m.group(1) if m else text.strip()


def run_python(src, tests, timeout=10):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'solution_test.py')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(f'{src}\n\n# ---- tests ----\n{tests}\nprint({PASSED!r})\n')
        try:
            r = subprocess.run([sys.executable, '-I', p], cwd=d, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, 'timed out'
        if r.returncode == 0 and PASSED in r.stdout:
            return True, None
        err = (r.stderr.strip().splitlines() or [f'exit {r.returncode}, tests did not finish'])[-1]
        return False, err[:200]


def check(task, answer, finish=None):
    """(passed, reason) for one answer. finish is the server's stop reason; a text
    answer cut off at the token limit is unfinished and fails (code is judged by its tests)."""
    # Thinking is switched off with chat_template_kwargs plus a "/no_think" tag at the end of
    # the prompt. Bonsai sometimes copies that tag onto the end of its answer; it is part of
    # the prompt, not of the answer, so it is dropped before checking (for every model).
    answer = re.sub(r'[ \t]*/no_think\b', '', answer)
    if not answer.strip() or answer.startswith('ERROR'):
        return False, 'no answer' if not answer.strip() else answer[:200]
    c = task['check']
    if 'python' in c:
        return run_python(code_of(answer), c['python'])
    if finish == 'length':
        return False, 'cut off at the token limit'
    why = []
    body = body_lines(answer)
    w = words('\n'.join(body))
    for pat in c.get('re', []):
        if not re.search(pat, answer, re.I):
            why.append(f'missing /{pat}/')
    for pat in c.get('not_re', []):
        m = re.search(pat, answer, re.I)
        if m:
            why.append(f'says {m.group(0)!r}')
    if 'answer' in c:
        a, spec = final_answer(answer), c['answer']
        if 'num' in spec:
            x = answer_number(a)
            if x is None or abs(x - spec['num']) > 1e-6 * max(1, abs(spec['num'])):
                why.append(f'answer {a[:60]!r}')
        if 're' in spec and not re.search(spec['re'], a, re.I):
            why.append(f'answer {a[:60]!r}')
        if 'first' in spec and first_of(a, spec['first']) != spec['want']:
            why.append(f'answer {a[:60]!r}')
    if 'max_words' in c and len(w) > c['max_words']:
        why.append(f'{len(w)} words, max {c["max_words"]}')
    if 'min_words' in c and len(w) < c['min_words']:
        why.append(f'{len(w)} words, min {c["min_words"]}')
    if 'words' in c and len(w) != c['words']:
        why.append(f'{len(w)} words, want {c["words"]}')
    if 'lines' in c and len(body) != c['lines']:
        why.append(f'{len(body)} lines, want {c["lines"]}')
    if 'line_max_words' in c and any(len(words(l)) > c['line_max_words'] for l in body):
        why.append(f'a line over {c["line_max_words"]} words')
    if 'initials' in c:
        got = ''.join((re.search(r'[A-Za-z]', tidy(l)) or ['?'])[0].upper() for l in body)
        if got != c['initials']:
            why.append(f'initials {got}')
    if 'line_words' in c and any(len(words(tidy(l))) != c['line_words'] for l in body):
        why.append(f'a line is not {c["line_words"]} word(s)')
    if c.get('distinct') and len({tidy(l).lower() for l in body}) != len(body):
        why.append('repeated lines')
    if 'line_end_re' in c:
        ends = [bare((words(l) or [''])[-1]).lower() for l in body]
        bad = [e for e in ends if not re.search(c['line_end_re'], e)]
        if bad:
            why.append(f'line endings {bad}')
    if 'bullets' in c:
        # a marker followed by text; '- - text' is a list inside a list, not a bullet
        n = sum(bool(re.match(r'^[-*•–]\s+(?![-*•–]\s)', l)) for l in body)
        if n != c['bullets'] or n != len(body):
            why.append(f'{n} bullets in {len(body)} lines, want {c["bullets"]}')
    if 'numbered' in c:
        lo, hi = c['numbered']
        n = sum(bool(re.match(r'^\**\s*\d+[.)]', l)) for l in body)
        if n != len(body) or not lo <= n <= hi:
            why.append(f'{n} numbered steps in {len(body)} lines, want {lo}-{hi}')
    if 'sentences' in c and len(sentences(answer)) != c['sentences']:
        why.append(f'{len(sentences(answer))} sentences, want {c["sentences"]}')
    if 'last_word' in c and (not w or bare(w[-1]).lower() != c['last_word']):
        why.append(f'last word {bare((w or [""])[-1])!r}')
    return not why, '; '.join(why) or None


def selftest(tasks):
    problems = 0
    for t in tasks:
        ok, why = check(t, t['ref'])
        if not ok:
            problems += 1
            print(f'{t["id"]}: reference answer FAILS: {why}')
        for i, b in enumerate(t['bad']):
            ok, _ = check(t, b)
            if ok:
                problems += 1
                print(f'{t["id"]}: wrong answer {i + 1} PASSES')
    for t in tasks:  # an unfinished text answer fails even when its content would pass
        if 'python' not in t['check'] and check(t, t['ref'], 'length')[0]:
            problems += 1
            print(f'{t["id"]}: reference answer cut off at the token limit PASSES')
    print(f'selftest: {len(tasks)} tasks, {sum(1 + len(t["bad"]) for t in tasks)} answers checked, {problems} problems')
    return problems


def cases(tasks, path):
    """Each case is [task id, answer, expected verdict]; prints every mismatch."""
    by_id = {t['id']: t for t in tasks}
    items = json.load(open(path, encoding='utf-8'))
    bad = 0
    for tid, ans, want in items:
        ok, why = check(by_id[tid], ans)
        if ok != want:
            bad += 1
            print(f'{tid}: expected {"pass" if want else "fail"}, got {"pass" if ok else "fail"} ({why}): {ans[:80]!r}')
    print(f'cases: {len(items)} checked, {bad} mismatches')
    return bad


def med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.median(xs), 2) if xs else None


def main(argv):
    if argv[:1] == ['--selftest']:
        tasks = json.load(open(argv[1], encoding='utf-8'))['tasks']
        sys.exit(1 if selftest(tasks) else 0)
    if argv[:1] == ['--cases']:
        tasks = json.load(open(argv[1], encoding='utf-8'))['tasks']
        sys.exit(1 if cases(tasks, argv[2]) else 0)
    spec = json.load(open(argv[0], encoding='utf-8'))
    tasks = {t['id']: t for t in spec['tasks']}
    models = {}
    for path in argv[1:]:
        for line in open(path, encoding='utf-8'):
            line = line.strip()
            if not line.startswith('{'):
                continue
            r = json.loads(line)
            if r.get('id') not in tasks:
                continue
            t = tasks[r['id']]
            ok, why = check(t, r.get('answer') or '', r.get('finish'))
            print(json.dumps({'model': r['model'], 'id': r['id'], 'cat': t['cat'], 'pass': ok, 'why': why}, ensure_ascii=False))
            m = models.setdefault(r['model'], {'rows': []})
            m['rows'].append({**r, 'cat': t['cat'], 'pass': ok})
    for name, m in models.items():
        rows = m['rows']
        by = {}
        for c in spec['categories']:
            rc = [r for r in rows if r['cat'] == c]
            by[c] = {'pass': sum(r['pass'] for r in rc), 'n': len(rc),
                     'writeTokS': med([r.get('writeTokS') for r in rc]), 'readTokS': med([r.get('readTokS') for r in rc]),
                     # time to answer, without Ollama loading the model (first request, or after a restart)
                     'answerS': med([r['s'] - (r.get('loadS') or 0) for r in rc if r.get('s') is not None]),
                     'outTokens': med([r.get('outTokens') for r in rc]),
                     'promptTokens': med([r.get('promptTokens') for r in rc])}
        print(json.dumps({'summary': name, 'pass': sum(r['pass'] for r in rows), 'of': len(rows), 'byCat': by,
                          'truncated': [r['id'] for r in rows if r.get('finish') == 'length']}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1:])
