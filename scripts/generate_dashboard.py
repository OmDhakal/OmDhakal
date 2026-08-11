import os
import json
import random
import hashlib
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
import html

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
GRAPHQL = "https://api.github.com/graphql"
FONT = 14
LINE = 19
ART_W = 42
ART_H = 26
LEFT_X = 22
RIGHT_X = 430
TOP_Y = 30
GLITCH = "░!@#$%&*?/|"


def load_config():
    with open(ROOT / "profile.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def uptime(birthdate):
    if not birthdate or "YYYY" in birthdate:
        return "not set"
    try:
        b = datetime.strptime(birthdate, "%Y-%m-%d").date()
    except ValueError:
        return "not set"
    t = date.today()
    years = t.year - b.year
    months = t.month - b.month
    days = t.day - b.day
    if days < 0:
        months -= 1
        pm = t.month - 1 or 12
        py = t.year if t.month > 1 else t.year - 1
        days += monthrange(py, pm)[1]
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years {months} months {days} days"


def github_stats(user, token):
    if not token:
        return {}
    query = """
    query($login:String!) {
      user(login:$login) {
        repositories(first:100, ownerAffiliations:OWNER, privacy:PUBLIC) {
          totalCount
          nodes { stargazerCount }
        }
        followers { totalCount }
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
          contributionCalendar { totalContributions }
        }
      }
    }
    """
    try:
        r = requests.post(
            GRAPHQL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": query, "variables": {"login": user}},
            timeout=30,
        )
        r.raise_for_status()
        u = r.json()["data"]["user"]
        repos = u["repositories"]
        cc = u["contributionsCollection"]
        return {
            "repos": repos["totalCount"],
            "stars": sum(x["stargazerCount"] for x in repos["nodes"]),
            "followers": u["followers"]["totalCount"],
            "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
            "contributions": cc["contributionCalendar"]["totalContributions"],
        }
    except Exception as e:
        print("GitHub stats warning:", e)
        return {}


def loc_stats(user, token, cache_name):
    path = ROOT / cache_name
    try:
        cache = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        cache = {}

    if not token:
        return cache.get("total", 0), cache.get("additions", 0), cache.get("deletions", 0)

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        repos = []
        page = 1
        while True:
            r = requests.get(
                f"https://api.github.com/users/{user}/repos",
                headers=headers,
                params={"per_page": 100, "page": page, "type": "owner"},
                timeout=30,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1

        old = cache.get("repos", {})
        add_total = del_total = 0

        for repo in repos:
            if repo.get("fork"):
                continue
            full = repo["full_name"]
            if full in old:
                add_total += old[full].get("additions", 0)
                del_total += old[full].get("deletions", 0)
                continue

            try:
                r = requests.get(
                    f"https://api.github.com/repos/{full}/stats/contributors",
                    headers=headers,
                    timeout=30,
                )
                if r.status_code != 200 or not r.json():
                    continue
                for contributor in r.json():
                    author = (contributor.get("author") or {}).get("login", "")
                    if author.lower() == user.lower():
                        a = sum(w.get("a", 0) for w in contributor.get("weeks", []))
                        d = sum(w.get("d", 0) for w in contributor.get("weeks", []))
                        old[full] = {"additions": a, "deletions": d}
                        add_total += a
                        del_total += d
                        break
            except Exception:
                continue

        total = add_total + del_total
        cache.update({
            "total": total,
            "additions": add_total,
            "deletions": del_total,
            "repos": old,
            "updated": datetime.now().isoformat(),
        })
        path.write_text(json.dumps(cache, indent=2))
        return total, add_total, del_total
    except Exception as e:
        print("LOC warning:", e)
        return cache.get("total", 0), cache.get("additions", 0), cache.get("deletions", 0)


def load_art(folder):
    arts = []
    for path in sorted((ROOT / folder).glob("*.txt")):
        lines = path.read_text(errors="ignore").rstrip("\n").splitlines()
        lines = [x.rstrip() for x in lines]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue

        indent = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
        lines = [x[indent:] if len(x) >= indent else "" for x in lines]

        width = max((len(x) for x in lines), default=0)
        if width > ART_W:
            ratio = width / ART_W
            scaled = []
            for line in lines:
                scaled.append("".join(
                    line[min(int(i * ratio), max(0, len(line) - 1))] if line else " "
                    for i in range(ART_W)
                ))
            lines = scaled

        if len(lines) > ART_H:
            start = (len(lines) - ART_H) // 2
            lines = lines[start:start + ART_H]

        content_w = max((len(x) for x in lines), default=0)
        left = max(0, (ART_W - content_w) // 2)
        lines = [(" " * left + x).ljust(ART_W)[:ART_W] for x in lines]

        while len(lines) < ART_H:
            lines.insert(0, " " * ART_W)
        arts.append((path.stem.upper().replace("_", "-"), lines))
    return arts


def morph(src, dst, seed):
    rng = random.Random(hashlib.md5(seed.encode()).hexdigest())
    frames = []
    for ratio, prefer_src in [(0.4, True), (0.75, True), (0.95, True),
                              (0.75, False), (0.4, False)]:
        frame = []
        for y in range(ART_H):
            a = src[y] if y < len(src) else " " * ART_W
            b = dst[y] if y < len(dst) else " " * ART_W
            out = []
            for x in range(ART_W):
                ca, cb = a[x], b[x]
                if ca == cb:
                    out.append(ca)
                elif rng.random() < ratio:
                    out.append(rng.choice(GLITCH) if (ca != " " or cb != " ") else " ")
                elif prefer_src and ca != " ":
                    out.append(ca)
                elif cb != " ":
                    out.append(cb)
                else:
                    out.append(ca)
            frame.append("".join(out))
        frames.append(frame)
    return frames


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def esc(value):
    return html.escape(str(value), quote=True)


def generate(config, stats, loc, arts, dark):
    bg = "#0d1117" if dark else "#ffffff"
    fg = "#c9d1d9" if dark else "#24292f"
    label = "#79c0ff" if dark else "#0550ae"
    title = "#58a6ff" if dark else "#0969da"
    green = "#3fb950" if dark else "#1a7f37"
    red = "#f85149" if dark else "#cf222e"
    dim = "#8b949e" if dark else "#57606a"
    border = "#30363d" if dark else "#d0d7de"
    glitch = "#d29922" if dark else "#9a6700"
    art_color = "#3fb950" if dark else "#1a7f37"

    display = float(config.get("display_seconds", 3.5))
    transition = float(config.get("transition_seconds", 0.6))
    count = max(1, len(arts))
    phase = display + transition
    cycle = count * phase

    css = []
    for i in range(count):
        start = i * phase
        stop = start + display
        p0, p1 = start / cycle * 100, stop / cycle * 100
        css.append(
            f"@keyframes art{i}{{0%,{max(0,p0-.4):.2f}%{{opacity:0}}"
            f"{p0:.2f}%,{p1:.2f}%{{opacity:1}}{min(100,p1+.8):.2f}%,100%{{opacity:0}}}}"
            f".art{i}{{animation:art{i} {cycle}s ease infinite}}"
        )

    art_nodes = []
    for i, (_, lines) in enumerate(arts):
        text = "".join(
            f'<text x="{LEFT_X}" y="{TOP_Y + y * LINE}">{esc(line)}</text>'
            for y, line in enumerate(lines)
        )
        art_nodes.append(f'<g class="art{i}">{text}</g>')

    for i in range(count):
        frames = morph(arts[i][1], arts[(i + 1) % count][1], f"{arts[i][0]}-{arts[(i + 1) % count][0]}")
        start = i * phase + display
        frame_time = transition / 5
        for j, frame in enumerate(frames):
            t0, t1 = start + j * frame_time, start + (j + 1) * frame_time
            p0, p1 = t0 / cycle * 100, t1 / cycle * 100
            css.append(
                f"@keyframes morph{i}_{j}{{0%,{max(0,p0-.2):.2f}%{{opacity:0}}"
                f"{p0:.2f}%,{p1:.2f}%{{opacity:1}}{min(100,p1+.2):.2f}%,100%{{opacity:0}}}}"
                f".morph{i}_{j}{{animation:morph{i}_{j} {cycle}s steps(1) infinite}}"
            )
            text = "".join(
                f'<text x="{LEFT_X}" y="{TOP_Y + y * LINE}">{esc(line)}</text>'
                for y, line in enumerate(frame)
            )
            art_nodes.append(f'<g class="morph{i}_{j}">{text}</g>')

    stats = stats or {}
    total, additions, deletions = loc
    title_text = f'{config["username"]}@{config["hostname"]}'
    rows = []
    y = TOP_Y

    def row(label_text, value, color=None):
        nonlocal y
        value_color = color or fg
        rows.append(
            f'<text x="{RIGHT_X}" y="{y}">'
            f'<tspan class="label">{esc(label_text)}: </tspan>'
            f'<tspan fill="{value_color}" class="value">{esc(value)}</tspan></text>'
        )
        y += LINE

    def space():
        nonlocal y
        y += 10

    rows.append(f'<text x="{RIGHT_X}" y="{y}" class="title">{esc(title_text)}</text>')
    y += LINE
    rows.append(f'<text x="{RIGHT_X}" y="{y}" class="dim">{"─" * len(title_text)}</text>')
    y += LINE + 10

    row("OS", config.get("os", ""))
    row("Uptime", uptime(config.get("birthdate", "")))
    row("Host", config.get("host", ""))
    row("Kernel", config.get("kernel", ""))
    row("IDE", config.get("ide", ""))
    space()

    row("Languages.Programming", config.get("languages_programming", ""))
    row("Languages.Computer", config.get("languages_computer", ""))
    row("Languages.Real", config.get("languages_real", ""))
    space()

    row("Hobbies.Software", config.get("hobbies_software", ""))
    row("Hobbies.Hardware", config.get("hobbies_hardware", ""))
    space()

    rows.append(f'<text x="{RIGHT_X}" y="{y}" class="section">- Contact</text>')
    y += LINE
    row("Email.Personal", config.get("email_personal", ""))
    row("Email.Work", config.get("email_work", ""))
    row("LinkedIn", config.get("linkedin", ""))
    row("Discord", config.get("discord", ""))
    space()

    rows.append(f'<text x="{RIGHT_X}" y="{y}" class="section">- GitHub Stats</text>')
    y += LINE
    row("Repos", fmt(stats.get("repos", 0)))
    row("Commits", fmt(stats.get("commits", 0)))
    row("Followers", fmt(stats.get("followers", 0)))
    row("Stars", fmt(stats.get("stars", 0)))
    row("Contributions", fmt(stats.get("contributions", 0)))
    rows.append(
        f'<text x="{RIGHT_X}" y="{y}">'
        f'<tspan class="label">Lines of Code: </tspan>'
        f'<tspan class="value" fill="{fg}">{fmt(total)}</tspan>'
        f'<tspan class="value" fill="{dim}"> (</tspan>'
        f'<tspan class="value" fill="{green}">{fmt(additions)}++</tspan>'
        f'<tspan class="value" fill="{dim}">, </tspan>'
        f'<tspan class="value" fill="{red}">{fmt(deletions)}--</tspan>'
        f'<tspan class="value" fill="{dim}">)</tspan></text>'
    )

    width = int(config.get("svg_width", 980))
    height = int(config.get("svg_height", 590))
    css_text = "".join(css)
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
<style>
.bg{{fill:{bg};stroke:{border};stroke-width:1;rx:8;ry:8}}
text{{font-family:'JetBrains Mono','Fira Code','Cascadia Code','SF Mono',monospace;font-size:{FONT}px;fill:{fg};font-weight:600;white-space:pre}}
.art0,.art1,.art2,.art3,.art4,.art5,.art6,.art7{{fill:{art_color}}}
.art{{fill:{art_color}}}.glitch{{fill:{glitch}}}.label,.section{{fill:{label};font-weight:700}}
.title{{fill:{title};font-weight:700}}.value{{font-weight:700}}.dim{{fill:{dim}}}
{css_text}
@keyframes cursor{{50%{{opacity:0}}}}.cursor{{animation:cursor 1s step-end infinite}}
</style>
<rect class="bg" x=".5" y=".5" width="{width-1}" height="{height-1}"/>
<line x1="395" y1="14" x2="395" y2="{height-14}" stroke="{border}" stroke-width="1" stroke-dasharray="4,4" opacity=".5"/>
<g id="ascii">{''.join(art_nodes)}</g>
<g id="info">{''.join(rows)}</g>
<text x="{RIGHT_X + len(title_text) * 8.4 + 4}" y="{TOP_Y}" class="title cursor">_</text>
</svg>"""


def main():
    config = load_config()
    token = os.environ.get("GITHUB_TOKEN", "")
    user = config["github_username"]

    stats = github_stats(user, token)
    stats_cache = ROOT / ".stats-cache.json"
    if stats:
        stats_cache.write_text(json.dumps(stats, indent=2))
    elif stats_cache.exists():
        stats = json.loads(stats_cache.read_text())

    loc = loc_stats(user, token, config.get("loc_cache_file", ".loc-cache.json"))
    arts = load_art(config.get("ascii_dir", "ascii"))
    if not arts:
        raise SystemExit("No ASCII art files found in ascii/")

    for dark, filename in ((True, "profile-dark.svg"), (False, "profile-light.svg")):
        (ROOT / filename).write_text(generate(config, stats, loc, arts, dark), encoding="utf-8")
        print(f"generated {filename}")


if __name__ == "__main__":
    main()
