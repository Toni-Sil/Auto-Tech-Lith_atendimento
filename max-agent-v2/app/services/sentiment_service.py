"""
Service for Sentiment Analysis using OpenAI
Antigravity Skill: prompt-engineering
"""
from typing import Dict, Any
import json
from openai import AsyncOpenAI
from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class SentimentService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyzes the sentiment of a given text.
        
        Returns:
            Dict containing:
            - score (float): -1.0 to 1.0
            - label (str): V. NEGATIVE, NEGATIVE, NEUTRAL, POSITIVE, V. POSITIVE
            - reasoning (str): Brief explanation
        """
        prompt = f"""
        Analyze the sentiment of the following message from a customer.
        
        Message: "{text}"
        
        Return a JSON object with:
        - "score": A float between -1.0 (Very Negative) and 1.0 (Very Positive).
        - "label": One of ["VERY_NEGATIVE", "NEGATIVE", "NEUTRAL", "POSITIVE", "VERY_POSITIVE"].
        - "reasoning": A short explanation (max 1 sentence).
        """

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise sentiment analysis engine using JSON output."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")
                
            result = json.loads(content)
            logger.info(f"Sentiment Analysis: {result['label']} ({result['score']}) for text: {text[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            # Fallback to neutral
            return {"score": 0.0, "label": "NEUTRAL", "reasoning": "Error in analysis"}
