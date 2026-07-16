import base64
from email.message import EmailMessage
import os
from pathlib import Path
from urllib.error import URLError

from career_agent.sources.news import (
    IMPACTALPHA_SENDER,
    ImpactAlphaNewsletterConfig,
    NewsFeedConfig,
    NewsSourcePack,
    RSSNewsSource,
    RSSNewsSourceConfig,
    check_source_pack_health,
    classify_capital_signal,
    load_news_source_pack,
    parse_impactalpha_gmail_payload,
    parse_impactalpha_newsletter_eml,
    parse_impactalpha_newsletter_html,
    signals_from_rss_xml,
)


def test_load_impact_capital_signal_source_pack():
    source_pack = load_news_source_pack(Path("examples/source_packs/impact_capital_signals.yaml"))

    assert source_pack.name == "impact_capital_signals"
    assert "impact_investing" in source_pack.verticals
    assert len(source_pack.rss_feeds) == 4
    assert all(feed.name != "ImpactAlpha" for feed in source_pack.rss_feeds)
    assert any(source["name"] == "SEC Form D" for source in source_pack.regulatory_sources)


def test_signals_from_rss_xml_enriches_capital_signal():
    xml = """
    <rss>
      <channel>
        <item>
          <title>Example Impact Fund closes new climate vehicle</title>
          <link>https://example.org/fund-close</link>
          <description>Fresh capital for climate finance.</description>
          <pubDate>Thu, 18 Jun 2026 07:04:32 -0400</pubDate>
        </item>
      </channel>
    </rss>
    """

    signals = signals_from_rss_xml(
        xml,
        NewsFeedConfig(
            name="Example Feed",
            url="https://example.org/feed",
            category="climate_finance",
            vertical="climate_finance",
        ),
    )

    assert len(signals) == 1
    assert signals[0].source == "Example Feed"
    assert signals[0].signal_subtype == "fund_close"
    assert signals[0].suggested_action == "rescan_org_jobs"
    assert signals[0].metadata["vertical"] == "climate_finance"


def test_check_source_pack_health_parses_rss_and_checks_metadata_urls(monkeypatch):
    source_pack = NewsSourcePack(
        name="demo",
        verticals=("impact_investing",),
        rss_feeds=(
            NewsFeedConfig(name="Demo RSS", url="https://example.org/feed.xml"),
        ),
        web_sources=({"name": "Demo Web", "url": "https://example.org"},),
        regulatory_sources=({"name": "Demo SEC", "url": "https://sec.example.org"},),
    )
    xml = """
    <rss>
      <channel>
        <item>
          <title>Fund closes new vehicle</title>
          <link>https://example.org/item</link>
        </item>
      </channel>
    </rss>
    """

    def fake_fetch(url, *, timeout_seconds, user_agent, max_bytes=None):
        if url.endswith("feed.xml"):
            return xml, 200
        return "<html>ok</html>", 200

    monkeypatch.setattr("career_agent.sources.news.fetch_text_url", fake_fetch)

    results = check_source_pack_health(source_pack)

    assert len(results) == 3
    assert all(result.ok for result in results)
    assert results[0].source_group == "rss_feeds"
    assert results[0].item_count == 1


def test_rss_source_isolates_feed_failures_and_reports_health(monkeypatch):
    feeds = (
        NewsFeedConfig(name="Working Feed", url="https://example.org/working.xml"),
        NewsFeedConfig(name="Blocked Feed", url="https://example.org/blocked.xml"),
    )
    xml = """
    <rss><channel><item>
      <title>Fund closes new vehicle</title>
      <link>https://example.org/item</link>
    </item></channel></rss>
    """

    def fake_fetch(url, *, timeout_seconds, user_agent, max_bytes=None):
        if url.endswith("blocked.xml"):
            raise URLError("blocked by source")
        return xml, 200

    monkeypatch.setattr("career_agent.sources.news.fetch_text_url", fake_fetch)

    result = RSSNewsSource(RSSNewsSourceConfig(feeds=feeds)).fetch_with_health()

    assert len(result.signals) == 1
    assert [health.ok for health in result.health_results] == [True, False]
    assert result.health_results[0].item_count == 1
    assert result.health_results[1].error == "blocked by source"


def test_parse_impactalpha_newsletter_html_extracts_content_links():
    html = """
    <html>
      <body>
        <a href="https://example.com/preferences">Manage preferences</a>
        <a href="https://track.example.com/c/abc">New GP launches climate adaptation fund</a>
        <a href="https://track.example.com/c/def">Read more</a>
      </body>
    </html>
    """

    signals = parse_impactalpha_newsletter_html(
        html,
        subject="The Brief: Sharing AI power along with wealth",
        date="Thu, 18 Jun 2026 07:04:32 -0400",
    )

    assert len(signals) == 1
    assert signals[0].source == "ImpactAlpha"
    assert signals[0].title == "New GP launches climate adaptation fund"
    assert signals[0].signal_subtype == "fund_launch"
    assert signals[0].metadata["source_detail"] == "impactalpha_html"


def test_parse_impactalpha_newsletter_eml_prefers_html():
    message = EmailMessage()
    message["From"] = f"ImpactAlpha <{IMPACTALPHA_SENDER}>"
    message["Subject"] = "The Brief: Sharing AI power along with wealth"
    message["Date"] = "Thu, 18 Jun 2026 07:04:32 -0400"
    message.set_content(
        """
        Impact fund closes new vehicle
        https://track.example.com/text
        """
    )
    message.add_alternative(
        """
        <html><body>
          <a href="https://track.example.com/html">LP commits to community finance fund</a>
        </body></html>
        """,
        subtype="html",
    )

    signals = parse_impactalpha_newsletter_eml(message.as_bytes())

    assert len(signals) == 1
    assert signals[0].title == "LP commits to community finance fund"
    assert signals[0].signal_subtype == "lp_commitment"


def test_parse_impactalpha_gmail_payload_decodes_html_body():
    html = """
    <html><body>
      <a href="https://track.example.com/deal">DFI invests in affordable housing platform</a>
    </body></html>
    """
    encoded_body = base64.urlsafe_b64encode(html.encode("utf-8")).decode("utf-8").rstrip("=")
    payload = {
        "payload": {
            "headers": [
                {"name": "Subject", "value": "The Brief: Development finance moves"},
                {"name": "Date", "value": "Thu, 18 Jun 2026 07:04:32 -0400"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded_body},
                }
            ],
        }
    }

    signals = parse_impactalpha_gmail_payload(payload)

    assert len(signals) == 1
    assert signals[0].signal_subtype == "transaction"


def test_impactalpha_config_builds_sender_query():
    config = ImpactAlphaNewsletterConfig(hours_back=12)

    assert config.gmail_query("2026/06/18") == "from:editor@impactalpha.com after:2026/06/18"


def test_impactalpha_config_supports_query_template():
    config = ImpactAlphaNewsletterConfig(
        sender="newsletter@example.com",
        query='from:{sender} subject:"The Brief" after:{after_date}',
    )

    assert config.gmail_query("2026/06/18") == (
        'from:newsletter@example.com subject:"The Brief" after:2026/06/18'
    )


def test_classify_capital_signal_programs():
    assert classify_capital_signal("new accelerator program for climate founders") == (
        "program_or_grant"
    )


def test_local_impactalpha_eml_smoke_if_configured():
    """Optional private smoke test for a maintainer-provided `.eml` file."""
    sample_path = os.environ.get("IMPACTALPHA_SAMPLE_EML")
    if not sample_path:
        return

    path = Path(sample_path)
    if not path.exists():
        return

    signals = parse_impactalpha_newsletter_eml(path.read_bytes())

    assert signals
    assert all(signal.source == "ImpactAlpha" for signal in signals)
