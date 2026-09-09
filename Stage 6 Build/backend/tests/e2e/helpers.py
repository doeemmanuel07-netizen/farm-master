"""
Shared Playwright helpers for the E2E layer. Every frontend flow file uses
the exact same login/OTP boilerplate (see the Stage 6 Style Guide's shared
chrome), so this is the one real place that pattern is encoded, rather
than 23 copies of the same three clicks.
"""

SEED_PASSWORD = "password123"


def login_and_verify_otp(page, base_url, flow_path, email, password=SEED_PASSWORD):
    """
    Navigates to a flow page and drives its real two-step login -- a
    genuine JWT, real OTP round trip, not a shortcut.

    Waits for #otpBtn to actually leave the DOM (`state="detached"`), not
    merely for #canvas to exist. #canvas is a static, always-present div
    in every flow file's HTML skeleton, so waiting on it resolves
    immediately on page load -- it proves nothing about whether OTP
    verification's own async data fetch (`state.token = ...; state.X =
    await apiGet(...); render();`) has actually finished. Every flow's
    render() unconditionally replaces #canvas's innerHTML for the new
    step, which necessarily removes the OTP step's own #otpBtn -- so its
    detachment is a reliable, universal signal that the post-login screen
    is actually populated with real data, not just present as an empty
    shell. Found the hard way (8/9 Sep 2026): three separate E2E tests
    intermittently asserted against real content before this fetch
    finished and failed as if the screen were empty.
    """
    page.goto(f"{base_url}{flow_path}")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#loginBtn")
    page.wait_for_selector("#otpBtn", timeout=10000)
    page.click("#otpBtn")
    page.wait_for_selector("#otpBtn", state="detached", timeout=10000)


def click_flow_step(page, label_substring):
    """Clicks a step in the shared flow-rail by its visible label text."""
    page.locator(".flow-step", has_text=label_substring).first.click()


def measure_overflow_and_touch_targets(page):
    """
    The same live-DOM-measurement check performed manually throughout
    Stage 6 (scrollWidth vs clientWidth for horizontal overflow;
    getBoundingClientRect() on every interactive element for the 44px
    touch-target minimum, PRD Section 5.1) -- now automated instead of a
    manual step to remember.
    """
    return page.evaluate(
        """
        () => {
            const docEl = document.documentElement;
            const smallTargets = [];
            document.querySelectorAll('button, input, select, a, [role=button]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && (r.height < 44 || r.width < 24)) {
                    smallTargets.push({tag: el.tagName, text: (el.textContent || el.value || '').slice(0, 30), w: Math.round(r.width), h: Math.round(r.height)});
                }
            });
            return {
                docWidth: docEl.clientWidth,
                scrollWidth: docEl.scrollWidth,
                hasHorizontalOverflow: docEl.scrollWidth > docEl.clientWidth,
                smallTargets,
            };
        }
        """
    )


def assert_responsive_clean(page, context_label=""):
    result = measure_overflow_and_touch_targets(page)
    assert not result["hasHorizontalOverflow"], (
        f"{context_label}: horizontal overflow at {page.viewport_size} "
        f"(scrollWidth={result['scrollWidth']} > clientWidth={result['docWidth']})"
    )
    assert result["smallTargets"] == [], (
        f"{context_label}: sub-44px touch target(s) at {page.viewport_size}: {result['smallTargets']}"
    )
