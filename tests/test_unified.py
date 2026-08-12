"""Tests for soic.unified_scorer."""

from soic.unified_scorer import compute_unified_score, format_unified_report


class TestUnifiedScorer:
    def test_perfect_coherence(self):
        score = compute_unified_score(
            osiris_score=8.0, osiris_grade="Conforme",
            soic_mu=8.0, soic_pass_rate=0.8,
        )
        assert score.coherence == 1.0

    def test_zero_coherence(self):
        score = compute_unified_score(
            osiris_score=0.0, osiris_grade="Critique",
            soic_mu=10.0, soic_pass_rate=1.0,
        )
        assert score.coherence == 0.0

    def test_partial_coherence(self):
        score = compute_unified_score(
            osiris_score=8.0, osiris_grade="Conforme",
            soic_mu=5.0, soic_pass_rate=0.5,
        )
        assert 0.6 < score.coherence < 0.8  # delta=3, coherence=0.7

    def test_to_dict(self):
        score = compute_unified_score(
            osiris_score=7.5, osiris_grade="Conforme",
            soic_mu=8.33, soic_pass_rate=0.833,
        )
        d = score.to_dict()
        assert "osiris_score" in d
        assert "soic_mu" in d
        assert "coherence" in d

    def test_format_report(self):
        score = compute_unified_score(
            osiris_score=7.5, osiris_grade="Conforme",
            soic_mu=8.33, soic_pass_rate=0.833,
        )
        report = format_unified_report(score)
        assert "Unified Score" in report
        assert "7.5" in report
        assert "8.33" in report

    def test_low_coherence_warning(self):
        score = compute_unified_score(
            osiris_score=2.0, osiris_grade="Critique",
            soic_mu=9.0, soic_pass_rate=0.9,
        )
        report = format_unified_report(score)
        assert "Low coherence" in report
