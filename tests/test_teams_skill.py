"""The teams skill's send verdicts are hand-written across three markdown files.
The dangerous drift is a chat id that ends up in both the writable list and the
never list, or a writable id that stops matching between the two files -- either
one could route a real message to the wrong corporate channel. Parse the docs and
assert the lists stay disjoint and consistent.
"""
import os
import re

SKILL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "skills", "teams",
)
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
INVENTORY = os.path.join(SKILL_DIR, "references", "chat-inventory.md")
MR_FORMAT = os.path.join(SKILL_DIR, "references", "mr-message-format.md")

ID_RE = re.compile(r"(?:19:[\w.\-]+@(?:thread\.tacv2|thread\.v2|unq\.gbl\.spaces)|48:notes)")

# The four purpose-bound channels plus the one free-to-write chat. Anything that
# claims to be writable must be exactly this set.
WRITABLE = {
    "48:notes",
    "19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2",  # [Run] Engine merge requests
    "19:f4b2e5764ffd4762b1f05697045eb35f@thread.tacv2",              # [Run] Config Merge Requests
    "19:8c31731328ee49e09e055dba5f9055a7@thread.tacv2",              # Reviews
    "19:b22a4db9472040859f5efac89f522316@thread.tacv2",              # Heka.core - Update Alerts
}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _section(text, start_heading, stop_pattern=r"\n## "):
    """Text from `start_heading` up to the next heading at the same level."""
    i = text.index(start_heading)
    rest = text[i + len(start_heading):]
    m = re.search(stop_pattern, rest)
    return rest[: m.start()] if m else rest


def test_skill_files_exist():
    for p in (SKILL, INVENTORY, MR_FORMAT):
        assert os.path.exists(p), f"missing {p}"


def test_skill_has_frontmatter_name_and_description():
    text = _read(SKILL)
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert re.search(r"^name: teams$", fm, re.M)
    assert re.search(r"^description: .{40,}", fm, re.M)


def test_writable_and_never_lists_are_disjoint():
    """The core invariant: nothing may be both sendable and forbidden."""
    text = _read(SKILL)
    never = set(ID_RE.findall(_section(text, "### Never send", r"\n### ")))
    assert never, "never-send section found no chat ids -- did the heading change?"
    overlap = WRITABLE & never
    assert not overlap, f"chat id listed as both writable and never-send: {overlap}"


def test_skill_writable_ids_match_the_canonical_set():
    text = _read(SKILL)
    free = set(ID_RE.findall(_section(text, "### Send freely", r"\n### ")))
    bound = set(ID_RE.findall(_section(text, "### Send for one specific purpose", r"\n### ")))
    assert free == {"48:notes"}, f"free-to-write list drifted: {free}"
    assert free | bound == WRITABLE, f"writable set drifted: {free | bound}"


def test_inventory_agrees_with_skill_on_writable_ids():
    inv = _read(INVENTORY)
    free = set(ID_RE.findall(_section(inv, "## Free to write")))
    bound = set(ID_RE.findall(_section(inv, "## Purpose-bound")))
    assert free | bound == WRITABLE, (
        f"chat-inventory.md writable set disagrees with SKILL.md: {free | bound}"
    )
    never = set(ID_RE.findall(_section(inv, "## Never write")))
    assert not (WRITABLE & never), f"inventory lists a writable id as never: {WRITABLE & never}"


def test_mr_routing_names_the_three_channels_and_both_gitlab_hosts():
    mr = _read(MR_FORMAT)
    for cid in (
        "19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2",
        "19:f4b2e5764ffd4762b1f05697045eb35f@thread.tacv2",
        "19:8c31731328ee49e09e055dba5f9055a7@thread.tacv2",
    ):
        assert cid in mr, f"routing table lost {cid}"
    # Both hosts are live and the split is load-bearing; losing one silently
    # sends people to the wrong GitLab.
    assert "git.sia.partners" in mr
    assert "git.sia-partners.com" in mr


def test_engine_voice_spec_keeps_its_load_bearing_details():
    """The Engine MR voice was derived from his 9 real posts and approved on a
    live preview. These are the details that make it sound like him rather than
    like the channel -- a reword that drops one is a regression, not a cleanup.
    """
    text = _read(SKILL)
    for needle, why in [
        ("Hello [Run] Engine merge requests !", "greeting + space before the !"),
        ("Related linear ticket : ", "his exact Linear lead-in, space before colon"),
        ("Little MR to", "his casual scope-downplaying opener"),
        ("lowercase component", "his subject tag is lowercase, unlike the channel"),
        ("no emoji", "he never signs off; the channel does"),
        ("<p>&nbsp;</p>", "the spacer plain-text mode would silently drop"),
        ("<<'EOF'", "quoted heredoc -- unquoted would eat &nbsp; and the URLs"),
        ("attachments[].url", "where the MR link comes from, so it is never invented"),
    ]:
        assert needle in text, f"Engine voice spec lost {why!r} ({needle!r})"

    # The channel-majority format must stay demoted to a recognition aid.
    i_his = text.index("### Writing in [Run] Engine merge requests")
    i_norm = text.index("The channel majority writes")
    assert i_his < i_norm, "channel-majority format must come after his own style"


def test_settings_allowlist_never_reaches_a_mutating_command():
    """A prefix rule like `teams chat:*` would also match `teams chat-send`."""
    import json
    settings = os.path.join(os.path.dirname(SKILL_DIR), "..", "settings.json")
    with open(os.path.normpath(settings), encoding="utf-8") as fh:
        allow = json.load(fh)["permissions"]["allow"]
    mutating = [
        "send", "chat-send", "reply", "react", "unreact", "edit", "delete",
        "forward", "send-file", "group-chat", "mark-read", "set-status",
        "schedule", "schedule-cancel", "schedule-run", "login",
    ]
    for rule in allow:
        m = re.fullmatch(r"Bash\(teams ([\w\-]+):\*\)", rule)
        assert m, f"unexpected allow rule shape: {rule}"
        prefix = m.group(1)
        for cmd in mutating:
            assert not cmd.startswith(prefix), (
                f"allow rule {rule!r} is a prefix of mutating command 'teams {cmd}'"
            )
