from trulens.providers.openai import OpenAI  # type: ignore
import logging

from kavach.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    GROUNDEDNESS,
)
from kavach.domain.evaluation_dataset import (
    EvaluationDataset,
)
from kavach.providers.trulens import (
    TruLensProvider,
)
from kavach.config import OPENAI_API_KEY, OPENAI_DEFAULT_JUDGE_MODEL

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)


def test_answer_relevance():
    judge_model = OPENAI_DEFAULT_JUDGE_MODEL

    provider = TruLensProvider(
        OpenAI(
            model_engine=judge_model,
            api_key=OPENAI_API_KEY,
            max_retries=0,
        ),
        judge_model=judge_model,
    )

    dataset = EvaluationDataset(
        execution_id="exec-1",
        input_text="What is the capital of France?",
        context_text="""
        France is a country in Europe.
        Paris is the capital and largest city of France.
        """,
        output_text="The capital of France is Paris.",
        metadata=provider.provider_metadata,
    )

    result = provider.evaluate(dataset)

    assert len(result.metrics) == 3

    metric_names = {metric.metric_name for metric in result.metrics}

    assert ANSWER_RELEVANCE in metric_names
    assert CONTEXT_RELEVANCE in metric_names
    assert GROUNDEDNESS in metric_names
