"""
LLM client for interacting with GPT-5 (OpenAI API).
"""

import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI


class LLMClient:
    """Client for GPT-5 API interactions."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5"):
        """
        Initialize LLM client.
        
        Args:
            api_key: OpenAI API key (if None, reads from OPENAI_API_KEY env var)
            model: Model name (default: gpt-5)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. "
                "Set OPENAI_API_KEY environment variable or pass api_key parameter."
            )
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
    
    def query(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send a query to LLM.
        
        Args:
            system_prompt: System instructions
            user_prompt: User message/question
            temperature: Sampling temperature (0.0-2.0, lower = more deterministic)
            max_tokens: Maximum tokens in response
            response_format: Optional format specification (e.g., {"type": "json_object"})
        
        Returns:
            Model's response text
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # Add response_format if specified (for JSON mode)
            if response_format:
                kwargs["response_format"] = response_format
            
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            print(f"Error querying LLM: {e}")
            raise
    
    def query_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Query LLM and parse response as JSON.
        
        Args:
            system_prompt: System instructions
            user_prompt: User message/question
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        
        Returns:
            Parsed JSON response
        """
        # Force JSON output format
        response_format = {"type": "json_object"}
        
        response_text = self.query(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Response text: {response_text[:500]}...")
            raise
