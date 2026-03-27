"""OpenAI embedding implementation."""

import logging
from typing import List

from openai import OpenAI

from mind.config.schema import EmbeddingConfig
from mind.embeddings.base import BaseEmbedding

logger = logging.getLogger(__name__)


class OpenAIEmbedding(BaseEmbedding):
    """OpenAI-backed embeddings."""

    def __init__(self, config: EmbeddingConfig, **kwargs) -> None:
        self.config = config
        sdk_base = config.base_url.rstrip("/") + config.sdk_base
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=sdk_base,
        )

    def _embed(self, text: str) -> List[float]:
        response = self.client.embeddings.create(model=self.config.model, input=text)
        return response.data[0].embedding
