"""Use complete source sentences for methods and findings comparison cells."""

import re

from app.schemas.chat import Claim, GeneratedAnswer
from app.services.chat import AnswerProvider

# Conservative admission rule for the findings row. Numeric parameters, sample
# sizes and future evaluation plans alone are not evidence of an outcome.
OUTCOME = re.compile(
    r"\b(?:observed|found that|revealed|outperformed|achieved|attained|"
    r"showed|demonstrated|increased|decreased|improved|was associated|"
    r"were associated|no significant|no measured|no validated|"
    r"did not (?:differ|improve)|(?:accuracy|recall|precision|latency|yield|"
    r"sensitivity|specificity) (?:was|were|of|reached)|"
    r"(?:did not|does not|do not) report (?:any )?(?:measured )?results)\b",
    re.I,
)
PROSPECTIVE = re.compile(
    r"\b(?:could|may|might|would|will|if|whether|hypothesiz\w*|expect\w*|"
    r"(?:plans?|planned|aims?|aimed|intends?|intended|proposes?|proposed) to|future work)\b",
    re.I,
)
OTHER_WORK = re.compile(
    r"\b(?:(?:prior|previous|earlier|other|past) (?:work|stud(?:y|ies)|research|authors?)"
    r"|et al|according to|related work|literature review)\b",
    re.I,
)
EXCLUDED_SECTION = re.compile(
    r"\b(?:related work|literature review|future work|references|bibliography)\b", re.I
)
MEASURED_CHANGE = re.compile(
    r"\b(?:fell|rose|dropped|declined|grew|climbed|shrank)\s+"
    r"(?:from|by|to)\s+[<>~≈]?\s*[-+]?\d",
    re.I,
)
OWN_NONREPORT = re.compile(
    r"^(?:we|(?:this|our|the present) (?:paper|study|experiment|demonstration|trial)) "
    r"(?:reports? no (?:measured|validated)|(?:did not|does not|do not) report "
    r"(?:any )?(?:measured )?results)\b",
    re.I,
)
NUMERIC_BRACKETS = re.compile(r"\[(\s*\d+(?:\s*[,;\-–]\s*\d+)*\s*)\]")
COMPARATIVE_PREFIX = re.compile(
    r"^(?:unlike|in contrast to|compared (?:with|to))\s+[^,;]+,\s*"
    r"(?=(?:we|our\b|this (?:study|paper|experiment))\b)",
    re.I,
)
TARGET_DEFINITION = re.compile(
    r"\b(?:specified|defined|set|chosen|designated|used|selected)\s+(?:as|at|to be)\s+"
    r"(?:an? |the |our )?(?:(?:acceptance|success|performance|minimum|decision) )?"
    r"(?:threshold|target|goal|criterion|requirement)\b|"
    r"\b(?:threshold|target|goal|criterion|requirement)\s+(?:was|is|of|for)\b",
    re.I,
)


def finding_sentence(sentence: str) -> bool:
    # Evaluate the asserted result separately from a trailing interpretation,
    # but keep the original sentence (including its qualifications) for display.
    assertion = re.split(
        r",\s*(?:which|suggesting|indicating)\b|;\s*", sentence, maxsplit=1, flags=re.I
    )[0]
    assertion = COMPARATIVE_PREFIX.sub("", assertion)
    # A temporal adjunct describes experimental conditions, not the result.
    # Validate the main clause on its own; keep attribution and modality checks
    # on the full assertion and return the original sentence as evidence.
    main_clause = re.sub(r"^(?:when|after|before|once)\b[^,;]+,\s*", "", assertion, flags=re.I)
    main_clause = re.split(
        r"\s+(?:when|after|before|once)\s+", main_clause, maxsplit=1, flags=re.I
    )[0]
    return bool(
        not OTHER_WORK.search(assertion)
        and not TARGET_DEFINITION.search(main_clause)
        and not PROSPECTIVE.search(assertion)
        and (OUTCOME.search(main_clause) or MEASURED_CHANGE.search(main_clause))
    )


def source_claim(sentence: str, source: int) -> Claim:
    # Numeric brackets in copied PDF text belong to the paper. Reserve ASCII
    # [n] for application citations, leaving the authoritative snippet untouched.
    return Claim(text=NUMERIC_BRACKETS.sub(r"〔\1〕", sentence), sources=[source])


class ComparisonEvidence:
    def __init__(self, provider: AnswerProvider, dimension: str):
        self.provider = provider
        self.dimension = dimension

    def generate(self, question: str, evidence: list[dict]) -> GeneratedAnswer:
        abstention = GeneratedAnswer(insufficient_evidence=True, claims=[])
        # Prefer methods sections when present, but support papers without headings.
        if self.dimension == "methodology":
            labeled = [
                item
                for item in evidence
                if re.search(
                    r"\b(?:methods?|methodology|procedures?)\b", item.get("section") or "", re.I
                )
            ]
            evidence = labeled or evidence
        passages = []
        origins = {}
        for item in evidence:
            sentences = re.split(
                r"(?<!et al\.)(?<=[.!?])\s+", " ".join(item["text"].split()), flags=re.I
            )
            if self.dimension == "findings":
                if EXCLUDED_SECTION.search(item.get("section") or ""):
                    continue
                sentences = [s for s in sentences if finding_sentence(s)]
            for sentence in sentences[:4]:
                if len(sentence) > 2000 or len(passages) == 12:
                    continue
                source = len(passages) + 1
                passages.append({**item, "source": source, "text": sentence})
                origins[source] = (item["source"], sentence)
        if not passages:
            return abstention
        result = self.provider.generate(
            question + " Each source is one sentence. Select only the one or two most "
            "informative source sentences that directly answer the question. If none directly "
            "answers it, return insufficient evidence.",
            passages,
        )
        claims = []
        seen = set()
        if not result.insufficient_evidence:
            for claim in result.claims:
                for selected in claim.sources:
                    if selected not in origins:
                        continue
                    source, sentence = origins[selected]
                    if sentence not in seen:
                        claims.append(source_claim(sentence, source))
                        seen.add(sentence)
                    if len(claims) == 2:
                        break
                if len(claims) == 2:
                    break
        if not claims and self.dimension == "findings":
            # A paper explicitly reporting no measurements still answers the row.
            # Quote its statement; never infer a negative result from silence.
            for source, sentence in origins.values():
                if OWN_NONREPORT.search(sentence):
                    claims.append(source_claim(sentence, source))
                    break
        return GeneratedAnswer(insufficient_evidence=not claims, claims=claims)
