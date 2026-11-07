"""Scan your code: replay a public GitHub repo's recent pull requests and
estimate what a coding agent spends finding what each change could break,
with text search and with Muse.

This is a simulation, not an agent run. For every merged pull request it
finds the functions the change touched, then counts two costs against a
snapshot of the repository:

  grep   the agent searches for each changed name, reads every file that
         mentions it (capped), finds the functions those callers live in,
         searches for them too, and reads those files: callers two levels deep.
  muse   one ``muse code impact --json`` answer per changed symbol: the
         callers two levels deep, as JSON.

Tokens are estimated at four characters per token. The per-task estimate
applies a measured share: coding agents spend 46.5% of their tokens reading
and searching (Zhang et al. 2026, "FastContext", arXiv 2606.14066), and Muse
replaces at most 85% of that, because the agent still reads the code it edits.

The analysis is language-agnostic and regex-based on purpose: it runs on any
public repo without installing a toolchain. It approximates Muse's symbol
graph; it does not call it. Results say so.

Only this module talks to GitHub for scans.
"""
from __future__ import annotations

import asyncio
import io
import re
import secrets
import tarfile
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

import httpx

from musehub.config import settings

# ── Constants (all illustrative except EXPLORE_SHARE, which is measured) ─────

#: Share of a coding agent's tokens spent reading and searching (measured).
EXPLORE_SHARE = 0.465
#: The most of that exploration Muse can replace: the agent still reads what it edits.
MAX_REPLACEABLE = 0.85
#: Characters per token, for estimating.
CHARS_PER_TOKEN = 4
#: Pull requests replayed per scan.
PR_LIMIT = 20
#: Files an agent would actually open per searched name; it stops reading after that.
READ_CAP_PER_NAME = 25
#: Second-level names searched per changed symbol.
LEVEL2_CAP = 10
#: Tokens in one caller entry of Muse's JSON answer, and its fixed envelope.
MUSE_TOKENS_PER_CALLER = 40
MUSE_TOKENS_ENVELOPE = 120
#: Seconds an agent spends per tool call (search or read), for the time estimate.
SECONDS_PER_TOOL_CALL = 3.0

SOURCE_EXTS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".rb",
    ".php", ".cs", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".scala", ".ex", ".exs",
})
SKIP_DIRS = frozenset({
    "node_modules", "vendor", "dist", "build", ".git", "third_party", "__pycache__",
    "target", "out", ".next", "coverage", "site-packages",
})
MAX_FILE_BYTES = 400_000
MAX_SNAPSHOT_BYTES = 80_000_000
TOO_COMMON = frozenset({"main", "init", "get", "set", "run", "test", "new", "self", "this", "constructor", "render"})

_DEF_RE = re.compile(
    r"(?:\bdef|\bfunction|\bfunc|\bfn|\bclass|\binterface|\bstruct|\benum|\btrait|\bmodule)\s+"
    r"(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)"
)
_JS_ASSIGN_RE = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")
_METHOD_RE = re.compile(r"^\s*(?:(?:public|private|protected|static|async|override|final|export|default|readonly)\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{)]*\)\s*(?::\s*[^{=]+)?\{\s*$")
_HUNK_RE = re.compile(r"^@@ [^@]* @@ ?(.*)$")
_COMMENT_RE = re.compile(r"^\s*(?:#|//|/\*|\*|--)")


def defined_names(line: str) -> list[str]:
    """Names a line defines: functions, classes, methods, arrow functions."""
    names = [m.group(1) for m in _DEF_RE.finditer(line)]
    names += [m.group(1) for m in _JS_ASSIGN_RE.finditer(line)]
    m = _METHOD_RE.match(line)
    if m and m.group(1) not in {"if", "for", "while", "switch", "catch", "return", "function"}:
        names.append(m.group(1))
    return names


def changed_symbols(patch: str) -> list[str]:
    """Symbols a unified diff touches: the function each hunk sits in, and any
    definition added or removed. Deduplicated, in order of appearance."""
    seen: dict[str, None] = {}
    for line in patch.splitlines():
        hunk = _HUNK_RE.match(line)
        if hunk:
            for n in defined_names(hunk.group(1)):
                seen.setdefault(n, None)
        elif line[:1] in "+-" and not line.startswith(("+++", "---")):
            for n in defined_names(line[1:]):
                seen.setdefault(n, None)
    return [n for n in seen if len(n) >= 3 and n not in TOO_COMMON]


@dataclass
class Snapshot:
    """The repository's source files at one commit, with a line index."""

    files: dict[str, str]
    #: name → [(path, line number)] of every line where the name appears as a word.
    _occ: dict[str, list[tuple[str, int]]] = field(default_factory=dict, repr=False)

    @property
    def symbol_count(self) -> int:
        return sum(len(defined_names(l)) for text in self.files.values() for l in text.splitlines())

    def occurrences(self, name: str) -> list[tuple[str, int]]:
        if name not in self._occ:
            rx = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
            out = []
            for path, text in self.files.items():
                if name not in text:
                    continue
                for i, line in enumerate(text.splitlines()):
                    if rx.search(line):
                        out.append((path, i))
            self._occ[name] = out
        return self._occ[name]

    def line(self, path: str, i: int) -> str:
        return self.files[path].splitlines()[i]

    def enclosing(self, path: str, i: int) -> str | None:
        """The name of the function or class a line sits in, by scanning upward."""
        lines = self.files[path].splitlines()
        for j in range(i, -1, -1):
            names = defined_names(lines[j])
            if names:
                return names[0]
        return None


@dataclass
class SymbolCost:
    symbol: str
    grep_tokens: int
    grep_calls: int
    muse_tokens: int
    callers: int
    false_matches: int
    alias_misses: int


def _is_call(line: str, name: str) -> bool:
    return bool(re.search(rf"(?<![\w$]){re.escape(name)}\s*\(", line)) and not defined_names(line) and not _COMMENT_RE.match(line)


def _alias_lines(snap: Snapshot, name: str) -> int:
    rx = re.compile(rf"(?:\bimport\b.*\b{re.escape(name)}\s+as\s+\w+|\{{[^}}]*\b{re.escape(name)}\s+as\s+\w+)")
    return sum(1 for path, i in snap.occurrences(name) if rx.search(snap.line(path, i)))


def cost_of(snap: Snapshot, name: str) -> SymbolCost:
    """What it costs to find a symbol's callers two levels deep, both ways."""
    occ = snap.occurrences(name)
    read: set[str] = set()
    grep_out_chars = sum(len(snap.line(p, i)) + len(p) + 8 for p, i in occ)
    calls = 1
    for p, _ in occ:
        if len(read) >= READ_CAP_PER_NAME:
            break
        if p not in read:
            read.add(p); calls += 1
    callers1 = [(p, i) for p, i in occ if _is_call(snap.line(p, i), name)]
    false_matches = len(occ) - len(callers1) - sum(1 for p, i in occ if name in defined_names(snap.line(p, i)))
    level2 = []
    for p, i in callers1:
        e = snap.enclosing(p, i)
        if e and e != name and e not in level2 and e not in TOO_COMMON:
            level2.append(e)
        if len(level2) >= LEVEL2_CAP:
            break
    callers2 = 0
    for e in level2:
        occ2 = snap.occurrences(e)
        grep_out_chars += sum(len(snap.line(p, i)) + len(p) + 8 for p, i in occ2)
        calls += 1
        opened = 0
        for p, i in occ2:
            if _is_call(snap.line(p, i), e):
                callers2 += 1
            if p not in read and opened < READ_CAP_PER_NAME // 2:
                read.add(p); opened += 1; calls += 1
    read_chars = sum(len(snap.files[p]) for p in read)
    grep_tokens = (read_chars + grep_out_chars) // CHARS_PER_TOKEN
    muse_tokens = MUSE_TOKENS_ENVELOPE + MUSE_TOKENS_PER_CALLER * (len(callers1) + callers2)
    return SymbolCost(name, grep_tokens, calls, muse_tokens, len(callers1) + callers2, max(0, false_matches), _alias_lines(snap, name))


@dataclass
class PullCost:
    number: int
    title: str
    symbols: list[str]
    grep_tokens: int
    muse_tokens: int
    grep_calls: int
    callers: int
    false_matches: int
    alias_misses: int


@dataclass
class ScanResult:
    id: str
    repo: str
    url: str
    sha: str
    files: int
    lines: int
    symbols: int
    pulls: list[PullCost]
    grep_tokens: int
    muse_tokens: int
    ratio: float
    grep_seconds: float
    task_saving: float
    false_matches: int
    alias_misses: int
    created: float
    method: str = "simulated"

    def to_dict(self) -> dict[str, str | int | float | list[dict[str, str | int | list[str]]]]:
        return asdict(self)


def summarize(repo: str, sha: str, snap: Snapshot, pulls: list[tuple[int, str, list[str]]]) -> ScanResult:
    """Cost every pull request's changed symbols and total them."""
    rows: list[PullCost] = []
    for number, title, symbols in pulls:
        costs = [cost_of(snap, s) for s in symbols if snap.occurrences(s)]
        if not costs:
            continue
        rows.append(PullCost(
            number=number, title=title, symbols=[c.symbol for c in costs],
            grep_tokens=sum(c.grep_tokens for c in costs), muse_tokens=sum(c.muse_tokens for c in costs),
            grep_calls=sum(c.grep_calls for c in costs), callers=sum(c.callers for c in costs),
            false_matches=sum(c.false_matches for c in costs), alias_misses=sum(c.alias_misses for c in costs),
        ))
    g = sum(r.grep_tokens for r in rows)
    m = sum(r.muse_tokens for r in rows)
    replaced = min(MAX_REPLACEABLE, 1 - m / g) if g else 0.0
    return ScanResult(
        id=secrets.token_urlsafe(4).replace("-", "x").replace("_", "z")[:5].lower(),
        repo=repo, url=f"https://github.com/{repo}", sha=sha,
        files=len(snap.files), lines=sum(t.count("\n") + 1 for t in snap.files.values()), symbols=snap.symbol_count,
        pulls=rows, grep_tokens=g, muse_tokens=m, ratio=round(g / m, 1) if m else 0.0,
        grep_seconds=round(sum(r.grep_calls for r in rows) * SECONDS_PER_TOOL_CALL, 1),
        task_saving=round(EXPLORE_SHARE * max(0.0, replaced), 3),
        false_matches=sum(r.false_matches for r in rows), alias_misses=sum(r.alias_misses for r in rows),
        created=time.time(),
    )


# ── GitHub ───────────────────────────────────────────────────────────────────

_REPO_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class ScanError(Exception):
    """A scan that can't run: bad input, private or missing repo, or GitHub refusing."""


def parse_repo(text: str) -> str:
    m = _REPO_RE.match(text.strip())
    if not m:
        raise ScanError("Paste a GitHub repo as owner/repo or its URL.")
    return f"{m.group(1)}/{m.group(2)}"


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "musehub-scan"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, str | int] | None = None) -> httpx.Response:
    r = await client.get(url, headers=_headers(), params=params)
    if r.status_code == 404:
        raise ScanError("That repo isn't public on GitHub, or doesn't exist.")
    if r.status_code in (403, 429):
        raise ScanError("GitHub is rate-limiting scans right now. Try again in a few minutes.")
    r.raise_for_status()
    return r


def snapshot_from_tarball(data: bytes) -> Snapshot:
    files: dict[str, str] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar:
            if not m.isfile() or m.size > MAX_FILE_BYTES:
                continue
            parts = m.name.split("/")[1:]
            if not parts or any(p in SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
                continue
            path = "/".join(parts)
            if "." + path.rsplit(".", 1)[-1] not in SOURCE_EXTS:
                continue
            total += m.size
            if total > MAX_SNAPSHOT_BYTES:
                break
            f = tar.extractfile(m)
            if f:
                files[path] = f.read().decode("utf-8", "replace")
    return Snapshot(files)


async def scan(repo_text: str, *, client: httpx.AsyncClient | None = None) -> ScanResult:
    """Scan a public GitHub repo. Raises ScanError for anything the user can fix."""
    repo = parse_repo(repo_text)
    own = client is None
    client = client or httpx.AsyncClient(base_url="https://api.github.com", timeout=30, follow_redirects=True)
    try:
        meta = (await _get(client, f"/repos/{repo}")).json()
        if meta.get("private"):
            raise ScanError("Only public repos can be scanned.")
        branch = meta["default_branch"]
        head = (await _get(client, f"/repos/{repo}/commits/{branch}")).json()["sha"]
        listing = (await _get(client, f"/repos/{repo}/pulls", params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 60})).json()
        merged = sorted((p for p in listing if p.get("merged_at")), key=lambda p: p["merged_at"], reverse=True)[:PR_LIMIT]
        if not merged:
            raise ScanError("No merged pull requests to replay in this repo.")

        async def files_of(p: dict[str, int | str]) -> tuple[int, str, list[str]]:
            fs = (await _get(client, f"/repos/{repo}/pulls/{p['number']}/files", params={"per_page": 100})).json()
            syms: dict[str, None] = {}
            for f in fs:
                if "." + f["filename"].rsplit(".", 1)[-1] in SOURCE_EXTS and f.get("patch"):
                    for s in changed_symbols(f["patch"]):
                        syms.setdefault(s, None)
            return int(p["number"]), str(p["title"]), list(syms)[:12]

        pulls = await asyncio.gather(*(files_of(p) for p in merged))
        tar = await _get(client, f"/repos/{repo}/tarball/{head}")
        snap = await asyncio.to_thread(snapshot_from_tarball, tar.content)
        if not snap.files:
            raise ScanError("No source files found to scan.")
        return await asyncio.to_thread(summarize, repo, head, snap, list(pulls))
    finally:
        if own:
            await client.aclose()


# ── Results, by short id ─────────────────────────────────────────────────────
# Kept in memory for the prototype: a restart forgets them. Persisting them
# needs a table and a migration (follow-up).

_RESULTS: "OrderedDict[str, ScanResult]" = OrderedDict()
_BY_REPO: dict[str, str] = {}
_MAX_RESULTS = 2000
_FRESH_SECONDS = 6 * 3600


def remember(result: ScanResult) -> ScanResult:
    _RESULTS[result.id] = result
    _BY_REPO[result.repo.lower()] = result.id
    while len(_RESULTS) > _MAX_RESULTS:
        old_id, old = _RESULTS.popitem(last=False)
        _BY_REPO.pop(old.repo.lower(), None)
    return result


def recall(result_id: str) -> ScanResult | None:
    return _RESULTS.get(result_id)


def recent_for(repo: str) -> ScanResult | None:
    """A scan of the same repo from the last few hours, so popular repos aren't rescanned."""
    rid = _BY_REPO.get(repo.lower())
    r = _RESULTS.get(rid) if rid else None
    return r if r and time.time() - r.created < _FRESH_SECONDS else None


# ── What the info button shows ───────────────────────────────────────────────

BENCHMARK_PROMPT = """Run a benchmark on this repository: does Muse make you, a coding agent,
faster and cheaper without making your changes worse? Measure it; don't
estimate.

1. Build the task set. Take the 20 most recent merged pull requests that
   change source code and add or change tests. For each, record the parent
   commit, a one-paragraph task description written from the PR title and
   body (never from the diff), and the tests the PR added or changed. Those
   tests are the hidden check; the agent doing the task never sees them.
   Save this to bench/tasks.json.

2. Run every task twice, each in a fresh git worktree at the parent commit,
   as a separate headless agent session with the same model (for example:
   claude -p "<task>" --output-format json).
   - Arm A: no Muse. Add to the task: "Do not use Muse."
   - Arm B: Muse installed and indexed. Add: "Before editing a function, run
     muse code impact <file>::<symbol> --json and
     muse code coverage <file>::<symbol> --json. If blast risk is high,
     write the missing test first. Before finishing, run
     muse code breakage. Don't grep for callers; ask Muse."
   Alternate which arm runs first.

3. Record for every run, in bench/results.csv: tokens and cost from the
   session's own usage report, tool calls (and how many were reads or
   searches), wall-clock time, whether the hidden tests pass, whether the
   existing suite still passes, and lines changed.

4. Write bench/REPORT.md: medians for arm A and arm B with the change in
   percent, per-task results, the repo size, the model, the agent and the
   date, and anything that failed. Label every number as measured. Don't
   drop tasks after seeing results.

Don't push or change anything outside bench/ and the temporary worktrees.
Delete the worktrees when done."""
