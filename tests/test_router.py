import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

CATALOG = [
    ("frontend-design", "Builds distinctive production-grade web pages, landing pages and UI components with a bold design."),
    ("systematic-debugging", "Four-phase debugging for any bug, test failure or unexpected behavior; finds the root cause before fixing."),
    ("pricing-strategy", "Designs product pricing: tiers, freemium, willingness to pay and price changes."),
    ("market-research", "Produces market research: sizing, competitor comparisons and industry analysis with sources."),
    ("email-sequences", "Plans and writes email sequences, newsletters and drip campaigns."),
    ("verification-before-completion", "Gate that forbids claiming work is done until the proving command has been run."),
    ("brainstorming", "Design dialogue before building a new feature; explores ideas and approaches."),
    ("study-habits", "Coaches studying with spaced repetition and exam plans."),
]
LOW = {"min_score": 0.1, "strong_score": 0.5, "min_pack_score": 0.1}   # thresholds for the tiny fixture catalogue


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home, self.data, self.proj = (os.path.join(self.tmp, n) for n in ("home", "data", "proj"))
        for d in (self.home, self.data, self.proj):
            os.makedirs(d)
        self._env = dict(os.environ)
        os.environ.update(CLAUDE_CONFIG_DIR=self.home, CLAUDE_PLUGIN_DATA=self.data)
        for k in ("CLAUDE_PLUGIN_OPTION_MODE", "CLAUDE_PLUGIN_OPTION_LANGUAGE"):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp)

    def skill(self, root, name, desc, extra=""):
        d = os.path.join(root, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: %s\ndescription: %s\n%s---\nbody\n" % (name, desc, extra))

    def install_catalog(self, extra=None):
        for name, desc in CATALOG:
            self.skill(os.path.join(self.home, "skills"), name, desc, (extra or {}).get(name, ""))

    def profile(self, **kw):
        with open(os.path.join(self.data, "profile.json"), "w", encoding="utf-8") as fh:
            json.dump(kw, fh)


class TestFrontmatter(unittest.TestCase):
    def test_forms(self):
        from srouter import inventory
        fm = inventory.parse_frontmatter(
            '---\nname: x\ndescription: >\n  folded one\n  line two\nwhen_to_use: "q: a"\n'
            "title: 'it''s'\ndisable-model-invocation: true\n---\nbody")
        self.assertEqual(fm["description"], "folded one line two")
        self.assertEqual(fm["when_to_use"], "q: a")
        self.assertEqual(fm["title"], "it's")
        self.assertEqual(fm["disable-model-invocation"], "true")

    def test_missing_or_broken(self):
        from srouter import inventory
        self.assertEqual(inventory.parse_frontmatter("no front matter"), {})
        self.assertEqual(inventory.parse_frontmatter("---\nname: x\nno closing"), {})


class TestTokens(unittest.TestCase):
    def test_english_forms_meet(self):
        from srouter import match
        for a, b in (("pages", "page"), ("designing", "design"), ("created", "create"), ("writing", "write")):
            self.assertEqual(match.stem(a), match.stem(b), (a, b))

    def test_russian_forms_meet(self):
        from srouter import match
        for a, b in (("страницы", "страница"), ("тесты", "тест"), ("лендинга", "лендинг")):
            self.assertEqual(match.stem(a), match.stem(b), (a, b))

    def test_stop_words_dropped(self):
        from srouter import match
        self.assertEqual(match.tokens("the and это"), [])


class TestPhase(unittest.TestCase):
    def test_detect(self):
        from srouter import match
        cases = {"fix the login bug": "build", "почини баг на странице": "build", "review the diff": "verify",
                 "проверь результат": "verify", "задеплой сайт": "ship", "deploy to production": "ship",
                 "compare options and decide": "plan", "что-то непонятное": "plan",
                 "запусти параллельных агентов в цикле": "plan"}
        for text, phase in cases.items():
            self.assertEqual(match.detect_phase(text), phase, text)


class TestRanking(Env):
    def ranker(self, **kw):
        from srouter import inventory, match
        self.install_catalog()
        return match.Ranker(inventory.build(self.proj), **kw)

    def top(self, ranker, text, n=1):
        from srouter import match
        return [s["short"] for _, s in ranker.rank(match.query_weights(text))[:n]]

    def test_english(self):
        r = self.ranker()
        self.assertEqual(self.top(r, "fix the bug in checkout, the test fails"), ["systematic-debugging"])
        self.assertEqual(self.top(r, "how should I price my product tiers"), ["pricing-strategy"])

    def test_bug_intent_beats_topic_words(self):
        from srouter import inventory, match
        self.install_catalog()
        self.skill(os.path.join(self.home, "skills"), "payment-checkout",
                   "Stripe checkout payments: builds the checkout flow and payment tests for a store.")
        r = match.Ranker(inventory.build(self.proj))
        self.assertEqual(self.top(r, "the checkout test fails after my last commit"), ["systematic-debugging"])
        self.assertEqual(self.top(r, "чекаут не работает, ошибка при оплате"), ["systematic-debugging"])

    def test_russian_via_lexicon(self):
        r = self.ranker()
        self.assertIn("frontend-design", self.top(r, "сделай лендинг для стартапа", 3))
        self.assertEqual(self.top(r, "почини ошибку в коде"), ["systematic-debugging"])
        self.assertEqual(self.top(r, "исследуй конкурентов и рынок"), ["market-research"])

    def test_unrelated_prompt_matches_nothing(self):
        from srouter import match
        self.assertEqual(self.ranker().rank(match.query_weights("weather forecast tomorrow")), [])

    def test_alias_teaches_a_new_language(self):
        from srouter import inventory, match
        self.install_catalog()
        skills = inventory.build(self.proj)
        plain = match.Ranker(skills).rank(match.query_weights("сделай рассылку для клиентов"))
        self.assertNotEqual(plain[0][1]["short"] if plain else None, "email-sequences")
        aliased = match.Ranker(skills, aliases={"email-sequences": ["рассылка", "письма"]})
        self.assertEqual(aliased.rank(match.query_weights("сделай рассылку для клиентов"))[0][1]["short"], "email-sequences")

    def test_manual_skills_are_never_ranked(self):
        from srouter import inventory, match
        self.install_catalog({"pricing-strategy": "disable-model-invocation: true\n"})
        names = [s["short"] for _, s in match.Ranker(inventory.build(self.proj)).rank(match.query_weights("pricing tiers"))]
        self.assertNotIn("pricing-strategy", names)

    def test_usage_boost_lifts_a_familiar_skill(self):
        from srouter import match
        r = self.ranker()
        q = match.query_weights("pricing tiers")
        base = dict((s["short"], sc) for sc, s in r.rank(q))["pricing-strategy"]
        r2 = self.ranker(boosts={"pricing-strategy": 1.4})
        self.assertAlmostEqual(dict((s["short"], sc) for sc, s in r2.rank(q))["pricing-strategy"], base * 1.4, places=6)

    def test_ignored_suggestions_fade_but_used_skills_never_do(self):
        from srouter import match
        self.assertEqual(match.ignored_penalty(5, 0), 1.0)
        self.assertAlmostEqual(match.ignored_penalty(10, 0), 0.75)
        self.assertEqual(match.ignored_penalty(40, 0), 0.5)
        self.assertEqual(match.ignored_penalty(40, 1), 1.0)

    def test_usage_boost_is_capped(self):
        from srouter import match
        self.assertEqual(match.usage_boost(0), 1.0)
        self.assertLessEqual(match.usage_boost(10_000), 1.5)
        self.assertGreater(match.usage_boost(5), match.usage_boost(1))


class TestTiers(unittest.TestCase):
    def test_strong_also_and_cut(self):
        from srouter import match
        ranked = [(10, {"short": "a"}), (7, {"short": "b"}), (4, {"short": "c"}), (0.5, {"short": "d"})]
        cfg = {"min_score": 1, "top_n": 3, "strong_score": 5}
        strong, also = match.classify(ranked, cfg)
        self.assertEqual([s["short"] for s in strong], ["a", "b"])
        self.assertEqual([s["short"] for s in also], ["c"])

    def test_nothing_strong_when_best_is_weak(self):
        from srouter import match
        strong, also = match.classify([(3, {"short": "a"}), (2, {"short": "b"})], {"min_score": 1, "top_n": 5, "strong_score": 5})
        self.assertEqual(strong, [])
        self.assertEqual([s["short"] for s in also], ["a", "b"])

    def test_resolve_pins_by_short_or_qualified_name(self):
        from srouter import match
        skills = [{"name": "p:x", "short": "x", "manual": False}, {"name": "y", "short": "y", "manual": True}]
        self.assertEqual([s["name"] for s in match.resolve(skills, ["x", "p:x", "y", "ghost"])], ["p:x"])


class TestInventory(Env):
    def test_sources_and_qualified_names(self):
        from srouter import inventory
        self.skill(os.path.join(self.home, "skills"), "mine", "a user skill")
        self.skill(os.path.join(self.proj, ".claude", "skills"), "local", "a project skill")
        plug = os.path.join(self.tmp, "plug")
        self.skill(os.path.join(plug, "skills"), "pskill", "a plugin skill")
        self.skill(os.path.join(self.tmp, "off", "skills"), "hidden", "from a disabled plugin")
        with open(os.path.join(self.home, "plugins.json"), "w"):
            pass
        os.makedirs(os.path.join(self.home, "plugins"))
        with open(os.path.join(self.home, "plugins", "installed_plugins.json"), "w") as fh:
            json.dump({"plugins": {"pm@market": [{"installPath": plug}],
                                   "dead@market": [{"installPath": os.path.join(self.tmp, "off")}]}}, fh)
        with open(os.path.join(self.home, "settings.json"), "w") as fh:
            json.dump({"enabledPlugins": {"dead@market": False}}, fh)
        names = {s["name"]: s["source"] for s in inventory.build(self.proj)}
        self.assertEqual(names, {"mine": "user", "local": "project", "pm:pskill": "plugin"})

    def test_cache_reparses_only_changed_files(self):
        from srouter import inventory
        self.install_catalog()
        with mock.patch.object(inventory, "_parse_file", wraps=inventory._parse_file) as parse:
            inventory.build(self.proj)
            first = parse.call_count
            inventory.build(self.proj)
            self.assertEqual(parse.call_count, first)
        self.assertEqual(first, len(CATALOG))


class TestShell(unittest.TestCase):
    def test_classifier(self):
        from srouter import shell
        safe = ["ls -la", "git status", "git log --oneline | head", "cat a.txt | grep x", "FOO=1 ls",
                "skill-router phase verify --query 'x'", "pwd && ls"]
        risky = ["rm -rf x", "git commit -m x", "cat a > b", "python3 run.py", "echo hi && rm a", 'echo "unclosed',
                 "sed -i s/a/b/ f", "git push", "npm install"]
        for c in safe:
            self.assertTrue(shell.is_readonly(c), c)
        for c in risky:
            self.assertFalse(shell.is_readonly(c), c)


class HookCase(Env):
    def setUp(self):
        super().setUp()
        self.install_catalog()
        self.profile(mode="guided", max_denials=1, **LOW)

    def prompt(self, text, sid="s1", **kw):
        from srouter import hooks
        return hooks.on_prompt(dict({"session_id": sid, "prompt": text, "cwd": self.proj}, **kw))

    def pre(self, tool="Edit", inp=None, sid="s1", **kw):
        from srouter import hooks
        return hooks.on_pretool(dict({"session_id": sid, "tool_name": tool, "tool_input": inp or {}, "cwd": self.proj}, **kw))

    def used(self, name, sid="s1"):
        from srouter import hooks
        return hooks.on_posttool({"session_id": sid, "tool_name": "Skill", "tool_input": {"skill": name}, "cwd": self.proj})

    @staticmethod
    def ctx(out):
        return out["hookSpecificOutput"]["additionalContext"]

    @staticmethod
    def denied(out):
        return bool(out) and out["hookSpecificOutput"].get("permissionDecision") == "deny"

    def journal(self):
        path = os.path.join(self.data, "journal.jsonl")
        return [json.loads(x) for x in open(path)] if os.path.exists(path) else []


class TestHooks(HookCase):
    FIX = "fix the bug in checkout, the test fails"

    def test_prompt_injects_ranked_skills_even_for_a_tiny_task(self):
        self.assertIn("systematic-debugging", self.ctx(self.prompt("fix typo bug")))

    def test_guided_blocks_once_then_lets_work_through(self):
        self.prompt(self.FIX)
        first = self.pre("Edit")
        self.assertTrue(self.denied(first))
        self.assertIn("none-fits", first["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("systematic-debugging", first["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_a_skill_call_unblocks(self):
        self.prompt(self.FIX)
        self.used("systematic-debugging")
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_suggest_mode_never_blocks(self):
        self.profile(mode="suggest", **LOW)
        self.assertIn("systematic-debugging", self.ctx(self.prompt(self.FIX)))
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_strict_blocks_until_limit(self):
        self.profile(mode="strict", max_denials=2, **LOW)
        self.prompt(self.FIX)
        self.assertEqual([self.denied(self.pre("Write")) for _ in range(3)], [True, True, False])

    def test_off_is_silent(self):
        self.profile(mode="off", **LOW)
        self.assertIsNone(self.prompt(self.FIX))
        self.assertIsNone(self.pre("Edit"))

    def test_weak_matches_do_not_block_in_guided(self):
        self.profile(mode="guided", min_score=0.1, strong_score=999)
        self.assertIn("systematic-debugging", self.ctx(self.prompt(self.FIX)))
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_read_only_bash_passes_and_changes_are_gated(self):
        self.prompt(self.FIX)
        self.assertFalse(self.denied(self.pre("Bash", {"command": "ls -la"})))
        self.assertTrue(self.denied(self.pre("Bash", {"command": "rm -rf build"})))

    def test_subagents_are_not_gated(self):
        self.prompt(self.FIX)
        self.assertFalse(self.denied(self.pre("Edit", agent_id="sub-1")))

    def test_user_typed_slash_skill_counts_as_a_choice(self):
        self.prompt("/frontend-design make a landing page")
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_skill_already_loaded_is_not_demanded_again(self):
        self.prompt(self.FIX)
        self.used("systematic-debugging")
        out = self.prompt("fix the bug in the cart, the test fails")
        self.assertIn("Already loaded", self.ctx(out))
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_phase_command_reopens_the_gate_with_phase_skills(self):
        self.profile(mode="guided", max_denials=1, pin={"verify": ["verification-before-completion"]}, **LOW)
        self.prompt(self.FIX)
        self.used("systematic-debugging")
        self.assertFalse(self.denied(self.pre("Edit")))
        self.assertFalse(self.denied(self.pre("Bash", {"command": "skill-router phase verify --query 'checkout'"})))
        out = self.pre("Edit")
        self.assertTrue(self.denied(out))
        self.assertIn("verification-before-completion", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_short_acknowledgement_keeps_the_state(self):
        self.prompt(self.FIX)
        self.assertIsNone(self.prompt("ок"))
        self.assertTrue(self.denied(self.pre("Edit")))

    def test_harness_messages_are_ignored(self):
        self.assertIsNone(self.prompt("<task-notification>done</task-notification>"))

    def test_nothing_relevant_means_no_gate(self):
        self.prompt("weather forecast tomorrow")
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_journal_and_usage_are_local_and_minimal(self):
        self.prompt(self.FIX)
        self.used("systematic-debugging")
        events = [e["ev"] for e in self.journal()]
        self.assertEqual(events, ["suggested", "used"])
        self.assertNotIn("checkout", json.dumps(self.journal()))   # prompt text is never stored
        usage = json.load(open(os.path.join(self.data, "usage.json")))
        self.assertEqual(usage["systematic-debugging"], 1)

    def test_none_fits_is_logged_with_its_reason_and_unblocks(self):
        self.prompt(self.FIX)
        from srouter import hooks
        hooks.on_posttool({"session_id": "s1", "tool_name": "Skill", "cwd": self.proj,
                           "tool_input": {"skill": "skill-router:none-fits", "args": "task is a one-off script"}})
        self.assertFalse(self.denied(self.pre("Edit")))
        self.assertEqual(self.journal()[-1]["ev"], "none-fits")
        self.assertIn("one-off", self.journal()[-1]["reason"])

    def test_light_task_is_suggested_but_never_blocked(self):
        out = self.prompt("fix a typo in the pricing tiers page")
        self.assertIn("pricing-strategy", self.ctx(out))
        self.assertFalse(self.denied(self.pre("Edit")))
        self.assertFalse(self.denied(self.pre("Edit")))

    def test_russian_messages(self):
        self.profile(mode="guided", language="ru", **LOW)
        self.assertRegex(self.ctx(self.prompt("почини ошибку в коде, тест падает")), "Подходящие")

    def test_suggestions_that_are_never_used_are_counted_and_then_fade(self):
        for _ in range(12):
            self.prompt(self.FIX, sid="s%d" % _)
        seen = json.load(open(os.path.join(self.data, "seen.json")))
        self.assertGreaterEqual(seen["systematic-debugging"], 12)
        from srouter import config, hooks, match
        cfg = config.load()
        weights = match.query_weights(self.FIX)

        def scores():
            return {s["short"]: sc for sc, s in hooks.suggest(cfg, self.proj, weights, "build")["ranked"]}
        faded = scores()
        os.remove(os.path.join(self.data, "seen.json"))
        fresh = scores()
        self.assertLess(faded["systematic-debugging"], fresh["systematic-debugging"])

    def test_context_stays_small(self):
        self.assertLess(len(self.ctx(self.prompt("design the landing page and fix the pricing bug"))), 1800)


class TestCli(HookCase):
    def run_cli(self, *argv):
        from srouter import cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_garbage_hook_input_is_swallowed(self):
        from srouter import cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(cli.run_hook("prompt", "{not json"), 0)
        self.assertEqual(buf.getvalue(), "")

    def test_profile_set_validates(self):
        self.assertEqual(self.run_cli("profile", "set", "mode", "strict")[0], 0)
        self.assertEqual(json.load(open(os.path.join(self.data, "profile.json")))["mode"], "strict")
        self.assertNotEqual(self.run_cli("profile", "set", "mode", "bogus")[0], 0)
        self.assertEqual(json.load(open(os.path.join(self.data, "profile.json")))["mode"], "strict")

    def test_profile_alias_pin_and_ignore(self):
        self.run_cli("profile", "alias", "email-sequences", "рассылка", "письма")
        self.run_cli("profile", "pin", "verify", "verification-before-completion")
        self.run_cli("profile", "ignore", "brainstorming")
        prof = json.load(open(os.path.join(self.data, "profile.json")))
        self.assertEqual(prof["aliases"]["email-sequences"], ["рассылка", "письма"])
        self.assertEqual(prof["pin"]["verify"], ["verification-before-completion"])
        self.assertEqual(prof["ignore"], ["brainstorming"])

    def test_phase_prints_pinned_and_matching_skills(self):
        self.run_cli("profile", "pin", "verify", "verification-before-completion")
        code, out = self.run_cli("phase", "verify", "--query", "check the checkout bug")
        self.assertEqual(code, 0)
        self.assertIn("verification-before-completion", out)

    def test_suggest_shows_tiers(self):
        code, out = self.run_cli("suggest", "fix the bug in checkout, the test fails")
        self.assertEqual(code, 0)
        self.assertIn("systematic-debugging", out)

    def test_status_reports_counts(self):
        self.prompt("fix the bug in checkout, the test fails")
        code, out = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn(str(len(CATALOG)), out)


PACK_CATALOG = CATALOG + [
    ("founder-board", "Puts a business idea in front of a board that votes fund or pass."),
    ("founder-plan", "Compiles a business plan with a verdict computed from the numbers."),
    ("founder-cfo", "Builds the unit economics of a business before money is spent."),
    ("founder-pricing", "Finds the price buyers will actually pay for a startup offer."),
    ("founder-offer", "Builds an offer too good to refuse for a new business."),
    ("subagent-driven-development", "Runs an implementation plan task by task with a fresh subagent per task and review loops."),
    ("dispatching-parallel-agents", "Dispatches one sub-agent per independent problem to run concurrently in parallel."),
    ("autonomous-loops", "Patterns for autonomous loops and orchestration of long running agent work."),
    ("marketing-loops", "Recurring marketing workflows an agent runs on a schedule, chosen from a loop catalog."),
    ("create-workflow-diagram", "Turns a plain-text workflow into a diagram."),
    ("zeta-one", "Zeta alpha tool."), ("zeta-two", "Zeta beta tool."), ("zeta-three", "Zeta gamma tool."), ("zeta-four", "Zeta delta tool."),
]


class PackEnv(Env):
    def setUp(self):
        super().setUp()
        for name, desc in PACK_CATALOG:
            self.skill(os.path.join(self.home, "skills"), name, desc)
        plug = os.path.join(self.tmp, "pmplug")
        for n in ("alpha", "beta", "gamma"):
            self.skill(os.path.join(plug, "skills"), n, "pm helper %s" % n)
        os.makedirs(os.path.join(self.home, "plugins"))
        with open(os.path.join(self.home, "plugins", "installed_plugins.json"), "w") as fh:
            json.dump({"plugins": {"pmx@market": [{"installPath": plug}]}}, fh)

    def discover(self, user_packs=None):
        from srouter import inventory, packs
        skills = inventory.build(self.proj)
        return skills, packs.discover(skills, user_packs or {})

    def pick(self, text, user_packs=None, **cfg):
        from srouter import match, packs
        skills, found = self.discover(user_packs)
        w = match.query_weights(text)
        ranked = match.Ranker(skills).rank(w)
        conf = dict({"min_pack_score": 0.1, "pack_n": 2}, **cfg)
        return packs.pick(found, ranked, w, conf)


class TestPacks(PackEnv):
    def test_discovery(self):
        _, found = self.discover()
        ids = {p["id"] for p in found}
        self.assertIn("business", ids)                 # built-in set, spans several skills
        self.assertIn("orchestration", ids)
        self.assertNotIn("family:founder", ids)        # fully inside the built-in business set
        self.assertIn("family:zeta", ids)              # a name family nobody curated
        self.assertIn("plugin:pmx", ids)               # an installed plugin is a set too
        self.assertNotIn("media", ids)                 # built-in sets need two installed members

    def test_business_task_picks_the_business_set(self):
        picks = self.pick("validate my startup business idea and decide the pricing")
        self.assertEqual(picks[0]["id"], "business")
        self.assertTrue({"founder-board", "founder-pricing", "founder-plan", "founder-cfo", "founder-offer"}
                        & {s["short"] for s in picks[0]["entry"]})

    def test_loop_task_picks_orchestration(self):
        picks = self.pick("run parallel agents in a loop until the tests pass")
        self.assertIn("orchestration", [p["id"] for p in picks])

    def test_orchestration_is_not_hijacked_by_look_alikes(self):
        picks = self.pick("run parallel agents in a loop until the tests pass")
        orch = next(p for p in picks if p["id"] == "orchestration")
        self.assertFalse({"marketing-loops", "create-workflow-diagram"} & {s["short"] for s in orch["entry"]})

    def test_at_most_two_sets_and_none_for_noise(self):
        self.assertLessEqual(len(self.pick("business idea parallel agents loop pricing zeta study")), 2)
        self.assertEqual(self.pick("weather forecast tomorrow"), [])

    def test_user_defined_set(self):
        picks = self.pick("outreach to my clients", {"my-sales": {"members": ["founder-pricing", "email-sequences"],
                                                                    "about": "outreach clients sales"}})
        self.assertEqual(picks[0]["id"], "my-sales")
        self.assertEqual({s["short"] for s in picks[0]["entry"]}, {"founder-pricing", "email-sequences"})


class TestPackHooks(PackEnv):
    def test_prompt_names_the_sets_and_entry_skills(self):
        from srouter import hooks
        with open(os.path.join(self.data, "profile.json"), "w") as fh:
            json.dump(dict(mode="guided", **LOW), fh)
        out = hooks.on_prompt({"session_id": "s", "cwd": self.proj, "prompt": "validate my startup business idea and pricing"})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Skill set", ctx)
        self.assertIn("business", ctx)
        self.assertLess(len(ctx), 1800)

    def test_russian_label(self):
        from srouter import hooks
        with open(os.path.join(self.data, "profile.json"), "w") as fh:
            json.dump(dict(mode="suggest", language="ru", **LOW), fh)
        out = hooks.on_prompt({"session_id": "s", "cwd": self.proj, "prompt": "проверь идею стартапа и бизнес модель, цены"})
        self.assertIn("Набор", out["hookSpecificOutput"]["additionalContext"])

    def test_profile_pack_command(self):
        from srouter import cli
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["profile", "pack", "my-sales", "founder-pricing", "email-sequences"]), 0)
        prof = json.load(open(os.path.join(self.data, "profile.json")))
        self.assertEqual(prof["packs"]["my-sales"]["members"], ["founder-pricing", "email-sequences"])


if __name__ == "__main__":
    unittest.main()
