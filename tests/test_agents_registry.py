"""The agent registry: 300 specialized agents over 30 domains and 10 specializations."""

from __future__ import annotations

from osv1.agents.domains import DOMAINS
from osv1.agents.registry import AGENTS, REGISTRY
from osv1.agents.specializations import SPECIALIZATIONS


def test_there_are_exactly_three_hundred_agents() -> None:
    assert len(AGENTS) == 300
    assert len(REGISTRY) == 300


def test_thirty_domains_and_ten_specializations() -> None:
    assert len(DOMAINS) == 30
    assert len(SPECIALIZATIONS) == 10
    assert len(REGISTRY.by_domain(DOMAINS[0].key)) == 10
    assert len(REGISTRY.by_specialization(SPECIALIZATIONS[0].key)) == 30


def test_every_agent_id_is_unique() -> None:
    ids = [agent.id for agent in AGENTS]
    assert len(set(ids)) == 300
    assert ids[0] == "A001"
    assert ids[-1] == "A300"


def test_every_agent_has_tools_and_verification_rules() -> None:
    for agent in AGENTS:
        assert agent.capabilities, f"{agent.id} has no capabilities"
        assert agent.verify_rules, f"{agent.id} has no verification rules"
        assert agent.plan_template, f"{agent.id} has no plan template"
        assert agent.focus, f"{agent.id} has no focus"


def test_every_domain_and_specialization_pair_exists() -> None:
    pairs = {(agent.domain.key, agent.specialization.key) for agent in AGENTS}
    assert len(pairs) == 300


def test_agents_of_the_same_specialization_share_the_deliverable() -> None:
    for specialization in SPECIALIZATIONS:
        agents = REGISTRY.by_specialization(specialization.key)
        assert len({agent.specialization.deliverable for agent in agents}) == 1


def test_routing_picks_the_review_agent_for_a_security_review() -> None:
    agent, info = REGISTRY.route("review the python code for a security vulnerability")
    assert agent is not None
    assert agent.specialization.key == "review"
    assert agent.domain.key == "security-engineering"


def test_routing_does_not_match_a_keyword_inside_another_word() -> None:
    agent, _ = REGISTRY.route("please review the report")
    assert agent is not None
    assert agent.domain.key != "databases"


def test_routing_finds_the_documentation_agent() -> None:
    agent, _ = REGISTRY.route("write the readme documentation for the project")
    assert agent is not None
    assert agent.domain.key == "technical-writing"
    assert agent.specialization.key == "documentation"


def test_routing_finds_the_dashboard_agent() -> None:
    agent, _ = REGISTRY.route("build an interactive dashboard from the csv sheet")
    assert agent is not None
    assert agent.domain.key in ("data-engineering", "media-visualization")


def test_search_finds_agents_by_id() -> None:
    found = REGISTRY.search("A001")
    assert found and found[0][0].id == "A001"


def test_catalog_reports_real_counts() -> None:
    catalog = REGISTRY.catalog()
    assert catalog["total"] == 300
    assert catalog["domains"] == 30
    assert catalog["specializations"] == 10
    assert sum(catalog["by_domain"].values()) == 300
    assert sum(catalog["by_specialization"].values()) == 300


def test_every_domain_and_specialization_carries_arabic_vocabulary() -> None:
    """An Arabic request has to reach the right agent, not a random one."""
    from osv1.agents.domains import DOMAINS as DOMAIN_LIST
    from osv1.agents.specializations import SPECIALIZATIONS as SPEC_LIST

    def has_arabic(words: tuple[str, ...]) -> bool:
        return any(any("\u0600" <= char <= "\u06ff" for char in word) for word in words)

    assert all(has_arabic(domain.keywords) for domain in DOMAIN_LIST)
    assert all(has_arabic(specialization.keywords) for specialization in SPEC_LIST)


def test_an_arabic_request_reaches_the_right_agent() -> None:
    agent, _ = REGISTRY.route("راجع الكود بحثاً عن ثغرات أمنية")
    assert agent is not None
    assert agent.domain.key == "security-engineering"
    assert agent.specialization.key == "review"


def test_an_arabic_stem_matches_its_inflections() -> None:
    """مراجعة، راجع — the same stem has to reach both, and the hamza needs its own entry."""
    from osv1.agents.registry import _word_present

    assert _word_present("راجع", "راج")
    assert _word_present("مراجعة", "راج")
    assert _word_present("ثغرة", "ثغر")
    assert _word_present("ثغرات", "ثغر")
    # The hamza is a different character, so both spellings are listed.
    assert _word_present("أمن", "أمن")
    assert _word_present("امن", "امن")
    assert not _word_present("أمن", "امن")
