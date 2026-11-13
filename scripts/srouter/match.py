"""Relevance ranking (BM25) with a small Russian-to-English lexicon, confidence tiers and work-phase detection."""
import math
import re

STOP = set("""a an and are as at be by can do for from has have how i if in into is it its me my of on or our so that the
their them then there these they this to up us use used using via was we what when where which who will with you your
also any all not no than too very just more most other some such only own same both each few about after before skill
skills user users claude ask asks asked need needs want wants like make makes new cases case etc eg ie
ok okay yes yep nope thanks thx please go continue proceed sure fine right
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из
ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей
может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот
того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при
наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо
свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между
это эта ок окей ага угу давай поехали спасибо продолжай дальше""".split())

# Russian task words -> English terms that skill descriptions use. Keys are raw-word prefixes.
LEXICON = {
    "сайт": "website site web page landing", "страниц": "page landing web", "лендинг": "landing page website",
    "дизайн": "design ui ux visual", "анимац": "animation motion animate", "исследован": "research analysis study",
    "исследу": "research analysis study", "анализ": "analysis analyze research",
    "конкурент": "competitor competitive competition", "рын": "market research", "цен": "pricing price",
    "тариф": "pricing plans", "реклам": "ads advertising campaign", "видео": "video", "ролик": "video",
    "текст": "copy writing text content", "промпт": "prompt prompting", "учеб": "study learn teach",
    "учит": "study learn teach", "изуч": "study learn research", "бизнес": "business strategy",
    "стартап": "startup product business", "автоматиз": "automation integration", "письм": "email", "отчет": "report",
    "отчёт": "report", "презентац": "presentation slides deck", "безопасн": "security",
    "деплой": "deploy deployment", "задеплой": "deploy deployment", "скорост": "performance speed optimization",
    "быстродейств": "performance speed optimization", "картинк": "image photo", "изображен": "image photo",
    "фото": "image photo", "голос": "voice audio", "баг": "bug debug fix error", "ошибк": "bug debug fix error",
    "почин": "bug debug fix", "исправ": "bug fix debug", "тест": "test testing", "план": "plan planning",
    "иде": "idea brainstorm", "провер": "verify review check audit test", "ревью": "review code",
    "коммит": "commit git", "репозитор": "repository git github", "баз": "database sql",
    "мобильн": "mobile responsive", "телефон": "mobile responsive", "доступн": "accessibility", "сео": "seo search",
    "поиск": "search seo", "продаж": "sales customer", "клиент": "customer client sales",
    "финанс": "finance financial budget", "бюджет": "finance budget", "спецификац": "spec requirements",
    "требован": "requirements spec", "код": "code programming", "архитектур": "architecture design system",
    "рефактор": "refactor cleanup", "документац": "documentation docs", "пдф": "pdf",
    "таблиц": "spreadsheet table xlsx", "бренд": "brand identity", "логотип": "logo brand identity",
    "музык": "music audio", "перевод": "translate translation", "резюме": "resume cv", "ресерч": "research",
    "прототип": "prototype", "стил": "style design", "цвет": "color palette", "шрифт": "typography font",
    "интервью": "interview research survey", "опрос": "survey research", "гипотез": "hypothesis experiment",
    "эксперимент": "experiment test hypothesis", "метрик": "metrics analytics", "аналитик": "analytics metrics",
    "экономик": "economics unit pricing", "приложен": "app application mobile",
    "верстк": "layout css frontend html", "компонент": "component react ui", "форм": "form input",
    "кнопк": "button interaction", "скролл": "scroll animation", "агент": "agent subagent orchestration",
    "параллел": "parallel agents", "цикл": "loop iterate autonomous", "оркестр": "orchestration agents workflow",
    "автоном": "autonomous agent loop", "команд": "team agents",
    "экзамен": "exam study", "зачет": "exam study", "зачёт": "exam study", "подготов": "prepare study",
    "математик": "math", "курс": "course study", "лекци": "lecture study", "конспект": "notes study", "урок": "lesson study",
}

# Intent words outrank topic words: "the checkout test fails" is a debugging task, not a payments task.
BUG = re.compile(r"\b(bugs?|fail\w*|errors?|crash\w*|broken|exception|regression|doesn'?t work|not working)\b"
                 r"|баг|ошибк|падает|упал|не работает|сломал|слетел|не запускается")
# Small edits are still routed, but never blocked for: nobody wants a gate in front of a typo fix.
LIGHT = re.compile(r"\b(typos?|renam\w*|reformat\w*|whitespace|tweak\w*|nits?|tiny|minor|one[- ]liner|small fix)\b"
                   r"|опечатк|переименуй|переимен|отформатируй|пробел|мелк|небольш")

PHASE_WORDS = {
    "plan": "plan brainstorm idea design research compare analyze analyse strategy spec outline explore think decide "
            "план идея иде исследов анализ сравни продума придума стратег спецификац обдума решим",
    "build": "build create implement write add fix refactor make develop code generate update change edit "
             "сделай создай напиши добавь исправ почини реализуй построй собери переделай поправь измени разработ",
    "verify": "review test check verify audit validate debug inspect lint "
              "проверь протестируй ревью аудит сверь валидир проверк",
    "ship": "deploy publish commit release ship push merge launch "
            "задеплой опубликуй закоммить выпусти залей",
}
PHASE_BOOST = {
    "plan": "plan brainstorm design spec research", "build": "implement build code",
    "verify": "verify review test check audit", "ship": "deploy commit release publish",
}
_RU_ENDINGS = sorted("""ами ями ого его ому ему ых их ую юю ая яя ое ее ые ие ой ей ом ем ам ям ах ях ов ев ий ый ть ет ют ут ит
ят ал ил ла ло ли ся сь а я у ю ы и е о ь й""".split(), key=len, reverse=True)


def _words(text):
    return re.findall(r"[a-zа-я0-9]+", text.lower().replace("ё", "е"))


def stem(w):
    if re.match(r"[а-я]", w):
        for end in _RU_ENDINGS:
            if w.endswith(end) and len(w) - len(end) >= 3:
                w = w[:-len(end)]
                break
        return w[:6]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    if len(w) > 3 and w[-1] == w[-2] and w[-1] in "bdgmnprt":
        w = w[:-1]
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def tokens(text):
    return [stem(w) for w in _words(text) if w not in STOP and len(w) > 1]


def query_weights(text):
    """Stem -> weight. Original words weigh 1.0; lexicon expansions of Russian words weigh 0.6."""
    weights = {}
    for w in _words(text):
        if w in STOP or len(w) < 2:
            continue
        weights[stem(w)] = 1.0
        if re.match(r"[а-я]", w):
            for key, eng in LEXICON.items():
                if w.startswith(key):
                    for e in eng.split():
                        weights.setdefault(stem(e), 0.6)
    if BUG.search(text.lower()):
        for term, w in (("debug", 1.6), ("bug", 1.0), ("root", 1.0), ("caus", 1.0), ("fix", 1.0)):
            weights[term] = max(weights.get(term, 0.0), w)
    return weights


def is_light(text):
    return bool(LIGHT.search(text.lower()))


def detect_phase(text):
    words = _words(text)
    score = {p: sum(1 for w in words if any(w.startswith(k) for k in lex.split())) for p, lex in PHASE_WORDS.items()}
    best = max(score, key=lambda p: score[p])
    return best if score[best] else "plan"


def ignored_penalty(seen, used):
    """Suggested over and over, never called: this person does not want it. Fades to half, never to zero."""
    if used > 0 or seen <= 5:
        return 1.0
    return max(0.5, 1.0 - 0.05 * (seen - 5))


def usage_boost(count):
    """A skill the person actually uses ranks a little higher. Capped so history never drowns relevance."""
    return min(1.5, 1.0 + 0.15 * math.log(1 + max(0, count)))


class Ranker:
    K1, B = 1.2, 0.75

    def __init__(self, skills, aliases=None, prefer=(), boosts=None):
        aliases, self.prefer, self.boosts = aliases or {}, set(prefer), boosts or {}
        self.skills = [s for s in skills if not s.get("manual")]
        self.docs, df = [], {}
        for s in self.skills:
            alias_text = " ".join(aliases.get(s["name"], []) + aliases.get(s["short"], []))
            doc = tokens(re.sub(r"[-_:]", " ", s["short"])) * 3 + tokens(s["desc"]) + tokens(alias_text) * 3
            tf = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            self.docs.append((tf, len(doc)))
            for t in tf:
                df[t] = df.get(t, 0) + 1
        self.n, self.df = len(self.skills), df
        self.avgdl = (sum(d[1] for d in self.docs) / self.n) if self.n else 1.0

    def rank(self, weights):
        out = []
        for s, (tf, dl) in zip(self.skills, self.docs):
            score = 0.0
            for term, w in weights.items():
                f = tf.get(term)
                if f:
                    idf = math.log(1 + (self.n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    score += w * idf * (f * (self.K1 + 1)) / (f + self.K1 * (1 - self.B + self.B * dl / self.avgdl))
            if score:
                if s["name"] in self.prefer or s["short"] in self.prefer:
                    score *= 1.25
                score *= self.boosts.get(s["short"], self.boosts.get(s["name"], 1.0))
                out.append((score, s))
        out.sort(key=lambda x: -x[0])
        return out


def classify(ranked, cfg):
    """(strong, also). Strong: clearly the best fit, at most four. Also: related, shown by name only."""
    if not ranked:
        return [], []
    top = ranked[0][0]
    floor = max(cfg["min_score"], 0.35 * top)
    picked = [(sc, s) for sc, s in ranked if sc >= floor][:cfg["top_n"]]
    strong = [s for sc, s in picked if sc >= cfg["strong_score"] and sc >= 0.7 * top][:4]
    ids = {id(s) for s in strong}
    return strong, [s for _, s in picked if id(s) not in ids]


def resolve(skills, names):
    """Skills matching the given short or qualified names, in the given order. Manual skills are skipped."""
    out, seen = [], set()
    for want in names:
        for s in skills:
            if not s.get("manual") and want in (s["name"], s["short"]) and s["name"] not in seen:
                seen.add(s["name"])
                out.append(s)
    return out
