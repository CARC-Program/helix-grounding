"""
helix-grounding — deterministic verification of factual values in
generated text.

The problem: a language model states a number that does not appear in
its source data. In anything touching money, specifications, dosages or
deadlines, that is not a quality issue, it is a liability.

The usual answer is to check the output with another model — LLM-as-
judge, semantic entailment, embedding similarity. All three are
probabilistic, all three cost an inference call, and all three can
themselves be wrong.

This library does not do that. It extracts every currency amount,
measurement, identifier, quantity and percentage from the text and
checks each one against a set of values computed from the source data.
For that class of claim the answer is decidable: a value is in the set
or it is not. No model call, no judgement, no confidence score.

    from helix_grounding import Verifier, GroundTruth, ClaimKind

    truth = GroundTruth().allow_many(ClaimKind.CURRENCY, [18.00, 22.00, 40.00])
    report = Verifier().verify(model_output, truth)

    if not report.is_grounded:
        print(report.summary())
        retry_prompt = base_prompt + report.correction_note()

Scope, stated plainly: this verifies *values*, not claims requiring
judgement. It cannot tell you whether advice is good, whether a summary
is complete, or whether a conclusion follows. Those need a different
layer. What it can tell you is that no figure reached your customer
that you did not put in front of the model — and unlike a faithfulness
score, that is something you can prove.
"""

from .claims import Claim, ClaimKind, GroundingReport
from .extractors import (
    DEFAULT_KNOWN_VOCABULARY,
    CurrencyExtractor,
    DateExtractor,
    Extractor,
    IdentifierExtractor,
    MeasurementExtractor,
    PercentageExtractor,
    QuantityExtractor,
    default_extractors,
)
from .truth import DEFAULT_TOLERANCES, TOKEN_KINDS, GroundTruth
from .verifier import DEFAULT_FALLBACK, ValidatedGeneration, Verifier

# Kept in step with pyproject.toml by test_ops_facts.py. These drifted apart
# once already: the package shipped as 0.1.1 while this said 0.1.0, so anyone
# reading it programmatically got the wrong answer.
__version__ = "0.1.1"

__all__ = [
    "Claim",
    "ClaimKind",
    "GroundingReport",
    "GroundTruth",
    "Verifier",
    "ValidatedGeneration",
    "Extractor",
    "CurrencyExtractor",
    "DateExtractor",
    "MeasurementExtractor",
    "IdentifierExtractor",
    "QuantityExtractor",
    "PercentageExtractor",
    "default_extractors",
    "DEFAULT_KNOWN_VOCABULARY",
    "DEFAULT_TOLERANCES",
    "TOKEN_KINDS",
    "DEFAULT_FALLBACK",
    "__version__",
]
