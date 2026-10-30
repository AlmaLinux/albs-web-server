import uuid
from types import SimpleNamespace

from alws.constants import ErrataReleaseStatus
from scripts.fix_errata_text_discrepancies import (
    apply_fix,
    pick_canonical,
    plan_fixes,
    plan_status_fixes,
)

RECORD_ID = 'ALSA-2024:1822'
CLEAN = 'The kernel packages contain the Linux kernel.\n\nSecurity Fix(es):'
SPACED = (
    'The kernel packages contain the Linux kernel.  \n\nSecurity Fix(es):  '
)
TITLE = 'Moderate: kernel security update'


def albs_record(
    platform: str,
    description: str,
    original: str = None,
    severity: str = 'moderate',
    status: ErrataReleaseStatus = ErrataReleaseStatus.RELEASED,
):
    return SimpleNamespace(
        id=RECORD_ID,
        platform=SimpleNamespace(name=platform),
        release_status=status,
        title=None,
        original_title=TITLE,
        description=None if original is None else description,
        original_description=description if original is None else original,
        severity=severity,
    )


def pulp_record(platform: str, description: str):
    return SimpleNamespace(
        id=RECORD_ID,
        content_ptr_id=uuid.uuid4(),
        collections=[
            SimpleNamespace(
                name=(
                    f'{platform.lower()}-for-x86_64-appstream-'
                    'rpms__9_3_default'
                ),
            )
        ],
        title=TITLE,
        description=description,
    )


def test_pick_canonical_fallback_prefers_least_whitespace():
    assert pick_canonical('description', [SPACED, CLEAN, SPACED]) == (
        CLEAN,
        'fallback',
    )


def test_pick_canonical_prefers_released_copies():
    assert pick_canonical(
        'description', [SPACED, CLEAN], released=[SPACED]
    ) == (SPACED, 'released copies')


def test_pick_canonical_falls_back_when_released_copies_differ():
    assert pick_canonical(
        'description', [SPACED, CLEAN], released=[SPACED, CLEAN]
    ) == (CLEAN, 'fallback, released copies differ')


def test_pick_canonical_respects_preferred_variant():
    assert pick_canonical(
        'description', [SPACED, CLEAN], released=[CLEAN], preferred=SPACED
    ) == (SPACED, 'source platform')


def test_pick_canonical_severity_fallback_is_lowercase():
    assert pick_canonical('severity', ['Moderate', 'moderate']) == (
        'moderate',
        'fallback',
    )


def test_pick_canonical_refuses_real_differences():
    assert (
        pick_canonical('description', [CLEAN, CLEAN + ' Bug Fix(es):'])[0]
        is None
    )
    assert pick_canonical('severity', ['Moderate', 'Important'])[0] is None


def test_plan_fixes_follows_released_record():
    # AL9 release failed in ALBS and its advisory is not in Pulp
    al8 = albs_record('AlmaLinux-8', SPACED)
    al9 = albs_record(
        'AlmaLinux-9',
        CLEAN,
        severity='Moderate',
        status=ErrataReleaseStatus.FAILED,
    )
    al8_pulp = pulp_record('AlmaLinux-8', SPACED)

    fixes, problems = plan_fixes(
        RECORD_ID,
        [al8, al9],
        [al8_pulp],
        ['title', 'description', 'severity'],
    )

    assert problems == []
    assert [(fix.field, fix.canonical, fix.reason) for fix in fixes] == [
        ('description', SPACED, 'released copies'),
        ('severity', 'moderate', 'released copies'),
    ]
    description_fix, severity_fix = fixes
    assert description_fix.albs_records == [al9]
    assert description_fix.pulp_records == []
    assert description_fix.sources == {
        SPACED: ['ALBS AlmaLinux-8 (released)', 'Pulp AlmaLinux-8 x1'],
        CLEAN: ['ALBS AlmaLinux-9 (failed)'],
    }
    assert severity_fix.pulp_records == []

    for fix in fixes:
        apply_fix(fix)
    assert al9.description == SPACED
    assert al9.original_description == CLEAN
    assert al9.severity == 'moderate'


def test_plan_fixes_treats_published_in_pulp_as_released():
    al8 = albs_record('AlmaLinux-8', SPACED)
    al9 = albs_record('AlmaLinux-9', CLEAN, status=ErrataReleaseStatus.FAILED)
    al8_pulp = pulp_record('AlmaLinux-8', SPACED)
    al9_pulp = pulp_record('AlmaLinux-9', CLEAN)

    fixes, _ = plan_fixes(
        RECORD_ID,
        [al8, al9],
        [al8_pulp, al9_pulp],
        ['description'],
    )

    # both copies are published, so there is no single released variant
    assert fixes[0].reason == 'fallback, released copies differ'
    assert fixes[0].canonical == CLEAN
    assert fixes[0].albs_records == [al8]
    assert fixes[0].pulp_records == [al8_pulp]


def test_plan_fixes_uses_source_platform():
    al8 = albs_record('AlmaLinux-8', SPACED)
    al9 = albs_record('AlmaLinux-9', CLEAN)
    al8_pulp = pulp_record('AlmaLinux-8', SPACED)
    al9_pulp = pulp_record('AlmaLinux-9', CLEAN)

    fixes, _ = plan_fixes(
        RECORD_ID,
        [al8, al9],
        [al8_pulp, al9_pulp],
        ['description'],
        source_platform='AlmaLinux-8',
    )

    assert fixes[0].canonical == SPACED
    assert fixes[0].pulp_records == [al9_pulp]
    apply_fix(fixes[0])
    assert al9.description == SPACED
    assert al9_pulp.description == SPACED


def test_plan_fixes_clears_override_matching_original():
    # the override is the broken text, the original one is fine
    al9 = albs_record('AlmaLinux-9', SPACED, original=CLEAN)
    al8 = albs_record('AlmaLinux-8', CLEAN)

    fixes, _ = plan_fixes(
        RECORD_ID,
        [al8, al9],
        [],
        ['description'],
        source_platform='AlmaLinux-8',
    )

    apply_fix(fixes[0])
    assert al9.description is None
    assert al9.original_description == CLEAN


def test_plan_fixes_reports_real_differences():
    al8 = albs_record('AlmaLinux-8', CLEAN)
    al9 = albs_record('AlmaLinux-9', CLEAN + ' Bug Fix(es):')

    fixes, problems = plan_fixes(RECORD_ID, [al8, al9], [], ['description'])

    assert fixes == []
    assert problems == [
        f'{RECORD_ID}: description differs not only cosmetically, skipping'
    ]


def test_plan_status_fixes_marks_published_records():
    al8 = albs_record('AlmaLinux-8', SPACED)
    al9 = albs_record('AlmaLinux-9', CLEAN, status=ErrataReleaseStatus.FAILED)
    kitten = albs_record(
        'AlmaLinux-Kitten-10', CLEAN, status=ErrataReleaseStatus.FAILED
    )

    assert plan_status_fixes(
        [al8, al9, kitten], ['AlmaLinux-8', 'AlmaLinux-9']
    ) == [al9]
