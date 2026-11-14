from unittest.mock import Mock

from app.schemas.chat import Claim, GeneratedAnswer
from app.services.comparison_evidence import ComparisonEvidence, finding_sentence


def test_threshold_condition_is_distinct_from_reported_outcome():
    assert finding_sentence(
        "When the threshold was lowered, measured recall increased from 60% to 72%."
    )
    assert finding_sentence("Recall increased from 60% to 72% after the threshold was lowered.")
    assert not finding_sentence(
        "When the threshold was lowered, the target was an accuracy of 95%."
    )
    assert not finding_sentence("When the threshold is lowered, recall could improve.")


def test_target_and_prior_comparison_are_classified_by_the_current_claim():
    assert not finding_sentence("An accuracy of 95% was specified as the acceptance threshold.")
    assert finding_sentence(
        "Unlike previous studies, our model achieved 95% accuracy on the held-out dataset."
    )
    assert not finding_sentence("Previous studies achieved 95% accuracy on the held-out dataset.")


def test_methods_and_configuration_are_not_findings():
    model = Mock()
    result = ComparisonEvidence(model, "findings").generate(
        "Findings?",
        [
            {"source": 1, "text": "We combine two search methods. The fusion constant is 60."},
            {"source": 2, "text": "We expect improved accuracy in future experiments."},
        ],
    )
    assert result.insufficient_evidence and not result.claims
    model.generate.assert_not_called()


def test_preserve_actual_outcome_and_reject_reversed_negation():
    quote = "Recall increased from 60% to 72%."
    model = Mock()
    model.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False,
        claims=[
            Claim(text=quote, sources=[1]),
            Claim(text="Measured yield increased.", sources=[2]),
        ],
    )
    result = ComparisonEvidence(model, "findings").generate(
        "Findings?",
        [
            {"source": 1, "text": quote},
            {"source": 2, "text": "There was no measured yield improvement."},
        ],
    )
    assert result.claims == [
        Claim(text=quote, sources=[1]),
        Claim(text="There was no measured yield improvement.", sources=[2]),
    ]


def test_only_current_measurements_reach_selector_with_qualifications_intact():
    supported = [
        "Our model achieved 91% accuracy, which could reduce annotation costs.",
        "The median error fell from 12 mm to 4 mm.",
    ]
    model = Mock()
    model.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text="selected", sources=[1, 2])]
    )
    result = ComparisonEvidence(model, "findings").generate(
        "Findings?",
        [
            {"source": 1, "text": "Prior work does not report measured results."},
            {"source": 2, "section": "Related Work", "text": "The method achieved 98% accuracy."},
            {"source": 3, "text": "Lee et al. observed a reduction in error."},
            {"source": 4, "text": "We plan to test whether accuracy improved after training."},
            {"source": 5, "text": " ".join(supported)},
        ],
    )
    assert [p["text"] for p in model.generate.call_args.args[1]] == supported
    assert result.claims == [Claim(text=s, sources=[5]) for s in supported]
